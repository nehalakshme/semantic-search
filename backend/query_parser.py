import re
import logging
from typing import Any

import dateparser
import spacy

logger = logging.getLogger(__name__)

nlp = spacy.load("en_core_web_sm")

_STOPWORDS = [
    "mentioning", "mentioned", "about", "from", "on", "in", "the", "a", "an",
    "with", "by", "for", "of", "and", "or", "to", "at", "containing",
    "includes", "including", "find", "show", "get", "patients?", "documents?",
    "files?", "records?", "results?",
]

_DOC_TYPE_MAP = {
    "lab_report": [r'\b(?:lab(?:oratory)?|blood test|blood panel|cbc|lipid|metabolic|urinalysis|test results)\b'],
    "patient_report": [r'\b(?:patient report|clinical note|consultation|progress note|chief complaint)\b'],
    "prescription": [r'\b(?:prescription|prescri(?:be|bed)|rx)\b'],
    "discharge_summary": [r'\bdischarge\b'],
}

_AGE_PATTERNS = [
    (re.compile(r'\b(?:between\s+)?(\d+)\s*(?:and|-|to)\s*(\d+)\s*(?:years?|yrs?)?\b', re.I), "range"),
    (re.compile(r'\b(?:above|over|older than|more than|greater than|aged?\s+over)\s+(\d+)\b', re.I), "gte"),
    (re.compile(r'\b(?:under|below|younger than|less than|aged?\s+under)\s+(\d+)\b', re.I), "lte"),
    (re.compile(r'\baged?\s+(\d+)\b', re.I), "exact"),
]

_DR_RE = re.compile(r'\bDr\.?\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*)', re.IGNORECASE)
_ABNORMAL_RE = re.compile(r'\b(?:abnormal|critical|flagged?|high results?|low results?|out of range)\b', re.I)
_ICD10_RE = re.compile(r'\b([A-Z]\d{2}(?:\.\d{1,4})?)\b')
_GENDER_RE = re.compile(r'\b(male|female|man|woman)\b(?:\s+(?:patients?|documents?|records?))?', re.I)
_LOW_OCR_RE = re.compile(r'\b(?:low quality|blurry|poor ocr|unreadable)\b', re.I)

SYNONYMS: dict[str, list[str]] = {
    r'\bheart attack\b': ['myocardial infarction', 'STEMI', 'MI', 'cardiac arrest'],
    r'\bstroke\b': ['CVA', 'cerebrovascular accident', 'TIA'],
    r'\bsugar\b': ['diabetes', 'glucose', 'hyperglycemia', 'DM'],
    r'\bBP\b': ['blood pressure', 'hypertension', 'HTN'],
    r'\bhigh blood pressure\b': ['hypertension', 'HTN'],
    r'\bfever\b': ['pyrexia', 'hyperthermia', 'elevated temperature'],
    r'\bcough\b': ['coughing', 'respiratory infection', 'bronchitis'],
    r'\bdiabetes\b': ['DM', 'diabetes mellitus', 'hyperglycemia', 'HbA1c'],
}


def _normalize_date(text: str) -> str | None:
    parsed = dateparser.parse(text, settings={"RETURN_AS_TIMEZONE_AWARE": False})
    return parsed.strftime("%Y-%m-%d") if parsed else None


def _detect_age_filter(query: str) -> dict | None:
    for pattern, kind in _AGE_PATTERNS:
        m = pattern.search(query)
        if not m:
            continue
        if kind == "range":
            a, b = int(m.group(1)), int(m.group(2))
            if 0 < a < 130 and 0 < b < 130:
                return {"gte": min(a, b), "lte": max(a, b)}
        elif kind == "gte":
            return {"gte": int(m.group(1))}
        elif kind == "lte":
            return {"lte": int(m.group(1))}
        elif kind == "exact":
            age = int(m.group(1))
            return {"gte": max(0, age - 1), "lte": age + 1}
    return None


def _expand_synonyms(text: str) -> str:
    extra = []
    for pattern, synonyms in SYNONYMS.items():
        if re.search(pattern, text, re.I):
            extra.extend(synonyms)
    if extra:
        return text + " " + " ".join(extra)
    return text


def _detect_doc_types(query: str) -> list[str]:
    found = []
    for dtype, patterns in _DOC_TYPE_MAP.items():
        for pat in patterns:
            if re.search(pat, query, re.I):
                found.append(dtype)
                break
    return found


def parse_query(query_string: str) -> dict[str, Any]:
    doc = nlp(query_string)

    persons = list(set(e.text.strip() for e in doc.ents if e.label_ == "PERSON" and len(e.text.strip()) > 1))
    orgs = list(set(e.text.strip() for e in doc.ents if e.label_ == "ORG" and len(e.text.strip()) > 1))
    date_ents = list(set(e.text.strip() for e in doc.ents if e.label_ == "DATE"))

    doctor_names = [m.group(0).strip() for m in _DR_RE.finditer(query_string)]
    persons = [p for p in persons if not any(p in d or d.endswith(p) for d in doctor_names)]

    parsed_dates = [d for d in (_normalize_date(t) for t in date_ents) if d]
    doc_types = _detect_doc_types(query_string)
    age_filter = _detect_age_filter(query_string)
    wants_abnormal = bool(_ABNORMAL_RE.search(query_string))
    wants_low_ocr = bool(_LOW_OCR_RE.search(query_string))

    # Gender filter
    gender_m = _GENDER_RE.search(query_string)
    gender_filter = None
    if gender_m:
        g = gender_m.group(1).lower()
        gender_filter = 'male' if g in ('male', 'man') else 'female'

    # ICD-10 codes in query
    icd10_in_query = _ICD10_RE.findall(query_string)

    # Build clean full-text remainder
    remaining = query_string
    for ent in doc.ents:
        remaining = remaining.replace(ent.text, " ")
    for pat, _ in _AGE_PATTERNS:
        remaining = pat.sub(" ", remaining)
    remaining = _ABNORMAL_RE.sub(" ", remaining)
    remaining = _GENDER_RE.sub(" ", remaining)
    remaining = _ICD10_RE.sub(" ", remaining)
    for sw in _STOPWORDS:
        remaining = re.sub(r"\b" + sw + r"\b", " ", remaining, flags=re.IGNORECASE)
    full_text = " ".join(remaining.split()).strip()

    # Synonym expansion
    if full_text:
        full_text = _expand_synonyms(full_text)

    # If entities were stripped but nothing else remains, use person names as full-text
    if not full_text and persons:
        full_text = " ".join(persons)

    must_clauses: list[dict] = []
    filter_clauses: list[dict] = []
    should_clauses: list[dict] = []

    if full_text:
        # A document passes if it satisfies fuzzy multi_match OR prefix match —
        # this handles both complete words and partial words like "hyperten" → "hypertension"
        must_clauses.append({
            "bool": {
                "should": [
                    {
                        "multi_match": {
                            "query": full_text,
                            "fields": ["content^1", "diagnoses^2", "medications^1.5",
                                       "filename^1", "patient_name^3", "doctor_name^2"],
                            "type": "best_fields",
                            "fuzziness": "AUTO",
                        }
                    },
                    {"match_phrase_prefix": {"content": {"query": full_text, "max_expansions": 30}}},
                    {"match_phrase_prefix": {"diagnoses": {"query": full_text, "max_expansions": 10}}},
                ],
                "minimum_should_match": 1,
            }
        })
        should_clauses += [
            {"match_phrase_prefix": {"patient_name": {"query": full_text, "boost": 3}}},
            {"match_phrase_prefix": {"doctor_name": {"query": full_text, "boost": 2}}},
        ]

    if persons:
        # Only use exact terms filter for full names (2+ words) — single words like
        # "thomas" won't match "Thomas Nguyen" on a keyword field
        full_name_persons = [p for p in persons if len(p.split()) >= 2]
        if full_name_persons:
            filter_clauses.append({"terms": {"persons_mentioned": full_name_persons}})
        for p in persons:
            should_clauses.append({"match_phrase_prefix": {"patient_name": {"query": p, "boost": 3}}})

    if doctor_names:
        for dn in doctor_names:
            should_clauses.append({"match_phrase_prefix": {"doctor_name": {"query": dn, "boost": 2}}})

    if orgs:
        filter_clauses.append({"terms": {"organizations_mentioned": orgs}})

    if doc_types:
        filter_clauses.append({"terms": {"document_type": doc_types}})

    if wants_abnormal:
        filter_clauses.append({"term": {"has_abnormal_results": True}})

    if wants_low_ocr:
        filter_clauses.append({"term": {"low_ocr_quality": True}})

    if gender_filter:
        filter_clauses.append({"term": {"patient_gender": gender_filter}})

    if icd10_in_query:
        filter_clauses.append({"terms": {"icd10_codes": icd10_in_query}})

    if age_filter:
        filter_clauses.append({"range": {"patient_age": age_filter}})

    if parsed_dates:
        filter_clauses.append({"terms": {"dates_in_document": parsed_dates}})

    if not must_clauses and not filter_clauses and not should_clauses:
        return {"query": {"match_all": {}}, "size": 50, "_aggs": True}

    bool_q: dict = {"must": must_clauses if must_clauses else [{"match_all": {}}]}
    if filter_clauses:
        bool_q["filter"] = filter_clauses
    if should_clauses:
        bool_q["should"] = should_clauses

    core_query = {"bool": bool_q}

    final_query = {
        "function_score": {
            "query": core_query,
            "functions": [
                {
                    "gauss": {
                        "uploaded_at": {"origin": "now", "scale": "30d", "offset": "7d", "decay": 0.5}
                    },
                    "weight": 1,
                },
                {
                    "field_value_factor": {
                        "field": "confidence_score", "factor": 0.01,
                        "modifier": "log1p", "missing": 50,
                    },
                    "weight": 0.5,
                },
            ],
            "score_mode": "sum",
            "boost_mode": "sum",
        }
    }

    return {
        "query": final_query,
        "min_score": 0.5,
        "highlight": {
            "fields": {
                "content": {
                    "fragment_size": 150,
                    "number_of_fragments": 3,
                    "pre_tags": ["<em>"],
                    "post_tags": ["</em>"],
                }
            }
        },
        "size": 50,
        "_aggs": True,
    }
