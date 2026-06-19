import os
import re
import time
import logging
from collections import Counter
from pathlib import Path

import dateparser as dp
import pytesseract
import spacy
from langdetect import detect, LangDetectException
from PIL import Image
from pdf2image import convert_from_path
from docx import Document

logger = logging.getLogger(__name__)

nlp = spacy.load("en_core_web_sm")

LOW_OCR_THRESHOLD = 60.0

# ── Patterns ──────────────────────────────────────────────────────────────────

_AGE_RE = re.compile(
    r'(?:Age[:\s]+(\d{1,3})'
    r'|(\d{1,3})\s*(?:year|yr)s?(?:\s*old)?'
    r'|\b(\d{1,3})\s*[Yy][/\-]?[Oo]\b)'
)
_DOSAGE_RE = re.compile(r'\d+(?:\.\d+)?\s*(?:mg|mcg|IU|ml|g|mEq|mmol|units?)\b(?:/(?:day|dose|kg))?', re.IGNORECASE)
_FREQ_RE = re.compile(r'\b(?:once|twice|thrice|three times|four times)\s*(?:daily|a day|per day)|\b(?:OD|BD|TDS|QID|PRN|SOS)\b', re.IGNORECASE)
_ICD10_RE = re.compile(r'\b([A-Z]\d{2}(?:\.\d{1,4})?)\b')
_DR_RE = re.compile(r'\bDr\.?\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*)')
_DIAG_RE = re.compile(r'(?:Diagnosis|Diagnoses|Assessment|Impression|Dx)[:\s]+([^\n\.]{5,200})', re.IGNORECASE)

_BP_RE = re.compile(r'\bB\.?P\.?\s*[:\-]?\s*(\d{2,3}[/\\]\d{2,3})\s*(?:mm\s*Hg)?', re.IGNORECASE)
_HR_RE = re.compile(r'\b(?:HR|Heart\s*Rate|Pulse)\s*[:\-]?\s*(\d{2,3})\s*(?:bpm|/min)?', re.IGNORECASE)
_TEMP_RE = re.compile(r'\bTemp(?:erature)?\s*[:\-]?\s*(\d{2,3}(?:\.\d)?)\s*(?:°?[CcFf])?', re.IGNORECASE)
_SPO2_RE = re.compile(r'\b(?:SpO2|O2\s*Sat(?:uration)?|Oxygen\s*Sat)\s*[:\-]?\s*(\d{2,3})\s*%?', re.IGNORECASE)
_BMI_RE = re.compile(r'\bBMI\s*[:\-]?\s*(\d{2,3}(?:\.\d)?)', re.IGNORECASE)

_GENDER_FIELD_RE = re.compile(r'\b(?:Gender|Sex)\s*[:\-]\s*([MF](?:ale|emale)?)\b', re.IGNORECASE)
_GENDER_INLINE_RE = re.compile(r'\b(Male|Female)\b', re.IGNORECASE)

_PATIENT_LABEL_RE = re.compile(r'(?:Full\s*Name\s*:|Patient\s*Name\s*:|Patient\s*:)\s*', re.IGNORECASE)
_PROPER_NAME_RE = re.compile(r'([A-Z][a-zA-Z\.\-\']+(?:\.?\s+[A-Z][a-zA-Z\.\-\']+){0,3})')
_NAME_STOPPER_RE = re.compile(
    r'\b(?:Age|Date|DOB|D\.O\.B|ID|Gender|Sex|Contact|Phone|Address|Insurance'
    r'|Blood|Type|Reason|Report|Name|Information|Full|Patient|Doctor|Visit'
    r'|Clinic|Hospital|Years?|Yrs?)\b',
    re.IGNORECASE,
)

_DOC_TYPE_PATTERNS = {
    "lab_report": [
        r'\b(?:CBC|complete blood count|lipid panel|metabolic panel|blood panel'
        r'|WBC|RBC|hemoglobin|hematocrit|platelet|glucose|creatinine|HbA1c'
        r'|electrolytes|urinalysis|lab(?:oratory)?\s+report|test results|reference range)\b',
    ],
    "patient_report": [
        r'\b(?:chief complaint|presenting complaint|history of present illness'
        r'|HPI|assessment and plan|SOAP note|progress note|consultation report)\b',
    ],
    "prescription": [
        r'\bR[xX]\b',
        r'\b(?:prescri(?:be|bed|ption)|dispense|sig:|refills?|tablet|capsule'
        r'|twice daily|once daily|three times daily)\b',
    ],
    "discharge_summary": [
        r'\b(?:discharge summary|date of discharge|discharge diagnosis'
        r'|hospital course|length of stay|admitted on)\b',
    ],
}


# ── OCR helpers ───────────────────────────────────────────────────────────────

def _ocr_image(img) -> tuple[str, list[int]]:
    data = pytesseract.image_to_data(img, output_type=pytesseract.Output.DICT)
    text = pytesseract.image_to_string(img)
    confs = [int(c) for c in data["conf"] if str(c).lstrip("-").isdigit() and int(c) >= 0]
    return text, confs


def _process_pdf(file_path: str) -> tuple[str, int, float]:
    images = convert_from_path(file_path, dpi=200)
    texts, all_confs = [], []
    for img in images:
        text, confs = _ocr_image(img)
        texts.append(text)
        all_confs.extend(confs)
    confidence = sum(all_confs) / len(all_confs) if all_confs else 0.0
    return "\n".join(texts), len(images), round(confidence, 2)


def _process_image(file_path: str) -> tuple[str, int, float]:
    img = Image.open(file_path)
    text, confs = _ocr_image(img)
    confidence = sum(confs) / len(confs) if confs else 0.0
    return text, 1, round(confidence, 2)


def _process_docx(file_path: str) -> tuple[str, int, float]:
    doc = Document(file_path)
    paragraphs = [p.text for p in doc.paragraphs if p.text.strip()]
    return "\n".join(paragraphs), max(1, len(paragraphs) // 40), 100.0


# ── NER post-processing ───────────────────────────────────────────────────────

def _clean_entities(entities: list[str]) -> list[str]:
    seen, cleaned = set(), []
    for ent in entities:
        ent = ent.strip('.,;:!?()[]{}"\'-–—')
        if len(ent) < 3:
            continue
        key = ent.lower()
        if key not in seen:
            seen.add(key)
            cleaned.append(ent)
    return cleaned


# ── Medical extraction ────────────────────────────────────────────────────────

def _extract_patient_name(text: str, spacy_doc) -> str | None:
    doctor_names = {m.group(0).strip() for m in _DR_RE.finditer(text)}
    doctor_surnames = {n.split()[-1].rstrip('.') for n in doctor_names}

    for label_m in _PATIENT_LABEL_RE.finditer(text):
        window = text[label_m.end(): label_m.end() + 100]
        name_m = _PROPER_NAME_RE.match(window)
        if not name_m:
            continue
        raw = name_m.group(1)
        stopper = _NAME_STOPPER_RE.search(raw)
        if stopper:
            raw = raw[: stopper.start()]
        name = re.sub(r'\.(?=\s)', ' ', raw).strip().rstrip(',.')
        name = ' '.join(name.split())
        if len(name.split()) < 2:
            continue
        if name.split()[-1].rstrip('.') not in doctor_surnames:
            return name

    patient_positions = [m.start() for m in re.finditer(r'\bpatient\b', text, re.IGNORECASE)]
    if not patient_positions:
        return None
    for ent in spacy_doc.ents:
        if ent.label_ != "PERSON" or len(ent.text.strip()) < 3:
            continue
        name = ent.text.strip()
        words = name.split()
        if not all(w[0].isupper() for w in words if w):
            continue
        if name in doctor_names or name.split()[-1] in doctor_surnames:
            continue
        if any(abs(ent.start_char - pos) < 200 for pos in patient_positions):
            return name
    return None


def _extract_doctor_name(text: str) -> str | None:
    match = _DR_RE.search(text)
    return match.group(0).strip() if match else None


def _extract_patient_age(text: str) -> int | None:
    for match in _AGE_RE.finditer(text):
        val = next((g for g in match.groups() if g is not None), None)
        if val:
            try:
                age = int(val)
                if 0 < age < 130:
                    return age
            except ValueError:
                continue
    return None


def _extract_gender(text: str) -> str | None:
    m = _GENDER_FIELD_RE.search(text)
    if m:
        return 'male' if m.group(1).upper().startswith('M') else 'female'
    m = _GENDER_INLINE_RE.search(text)
    if m:
        return m.group(1).lower()
    male = len(re.findall(r'\b(?:he|his|him)\b', text, re.IGNORECASE))
    female = len(re.findall(r'\b(?:she|her|hers)\b', text, re.IGNORECASE))
    if male > female and male > 2:
        return 'male'
    if female > male and female > 2:
        return 'female'
    return None


def _extract_vital_signs(text: str) -> dict:
    vitals = {}
    m = _BP_RE.search(text)
    if m:
        vitals['blood_pressure'] = m.group(1)
    m = _HR_RE.search(text)
    if m:
        vitals['heart_rate'] = m.group(1) + ' bpm'
    m = _TEMP_RE.search(text)
    if m:
        vitals['temperature'] = m.group(1) + '°'
    m = _SPO2_RE.search(text)
    if m:
        vitals['spo2'] = m.group(1) + '%'
    m = _BMI_RE.search(text)
    if m:
        vitals['bmi'] = m.group(1)
    return vitals


def _extract_dosages(text: str) -> list[str]:
    dosages = [m.group(0).strip() for m in _DOSAGE_RE.finditer(text)]
    dosages += [m.group(0).strip() for m in _FREQ_RE.finditer(text)]
    return list(dict.fromkeys(dosages))[:20]


def _extract_icd10_codes(text: str) -> list[str]:
    codes = list(set(_ICD10_RE.findall(text)))
    return [c for c in codes if len(c) >= 3][:20]


def _extract_diagnoses(text: str) -> list[str]:
    results = []
    for match in _DIAG_RE.finditer(text):
        for part in re.split(r'[,;]', match.group(1)):
            part = part.strip()
            if 3 < len(part) < 150:
                results.append(part[:100])
    for match in _ICD10_RE.finditer(text):
        ctx = text[max(0, match.start() - 5): min(len(text), match.end() + 80)].strip()
        if ctx:
            results.append(ctx[:100])
    return list(dict.fromkeys(results))[:10]


def _extract_medications(text: str, spacy_doc) -> list[str]:
    meds = []
    for match in _DOSAGE_RE.finditer(text):
        start, end = max(0, match.start() - 80), min(len(text), match.end() + 20)
        for chunk in spacy_doc.noun_chunks:
            if start <= chunk.start_char <= end:
                med = chunk.text.strip()
                if 2 < len(med) < 60 and not med.isdigit():
                    meds.append(med)
    rx_re = re.compile(
        r'(?:Tab\.|Cap\.|Inj\.|Syrup|Drops?)\s*([A-Za-z][A-Za-z\s\-]+?)(?=\s+\d|\s*$)',
        re.IGNORECASE,
    )
    for m in rx_re.finditer(text):
        meds.append(m.group(1).strip())
    return list(dict.fromkeys(meds))[:15]


def _extract_lab_tests(text: str) -> list[dict]:
    _LAB_LINE_RE = re.compile(
        r'^([\w][\w\s\(\)/\-]{1,35}?)\s{2,}'
        r'(\d+(?:\.\d+)?)\s*'
        r'([a-zA-Z%/µ]+)?\s*'
        r'(?:[\d.]+\s*[-–]\s*[\d.]+\s*[^\s]*)?\s*'
        r'(H{1,2}|L{1,2}|HIGH|LOW|CRITICAL|ABNORMAL|Normal)?\s*$',
        re.IGNORECASE | re.MULTILINE,
    )
    tests = []
    for match in _LAB_LINE_RE.finditer(text):
        name = match.group(1).strip()
        result = match.group(2)
        unit = (match.group(3) or "").strip()
        flag_raw = (match.group(4) or "").upper()
        if not name or len(name) < 2:
            continue
        flag = "HIGH" if flag_raw in ("H", "HH", "HIGH", "CRITICAL", "ABNORMAL") else \
               "LOW" if flag_raw in ("L", "LL", "LOW") else "NORMAL"
        tests.append({"name": name[:50], "result": result + (" " + unit if unit else ""), "flag": flag})
    return tests[:30]


def _detect_document_type(text: str) -> str:
    sample = text[:5000]
    scores = {dtype: 0 for dtype in _DOC_TYPE_PATTERNS}
    for dtype, patterns in _DOC_TYPE_PATTERNS.items():
        for pattern in patterns:
            if re.search(pattern, sample, re.IGNORECASE):
                scores[dtype] += 1
    best = max(scores, key=scores.get)
    return best if scores[best] > 0 else "general"


def _normalize_dates(raw: list[str]) -> list[str]:
    results = []
    for d in raw:
        parsed = dp.parse(d, settings={"RETURN_AS_TIMEZONE_AWARE": False})
        results.append(parsed.strftime("%Y-%m-%d") if parsed else d)
    return list(set(results))


def _detect_language(text: str) -> str:
    try:
        sample = text.strip()[:2000]
        if sample:
            return detect(sample)
    except LangDetectException:
        pass
    return "unknown"


# ── Entry point ───────────────────────────────────────────────────────────────

def process_file(file_path: str, original_filename: str) -> dict:
    t0 = time.time()
    ext = Path(original_filename).suffix.lower()

    if ext == ".pdf":
        text, page_count, confidence = _process_pdf(file_path)
        file_type = "pdf"
    elif ext in {".png", ".jpg", ".jpeg"}:
        text, page_count, confidence = _process_image(file_path)
        file_type = "image"
    elif ext == ".docx":
        text, page_count, confidence = _process_docx(file_path)
        file_type = "docx"
    else:
        raise ValueError(f"Unsupported file type: {ext}")

    if not text or not text.strip():
        raise ValueError("No text could be extracted from this document — the image may be unreadable.")

    spacy_doc = nlp(text[:500_000])

    # General NER with post-processing
    persons_raw = [e.text.strip() for e in spacy_doc.ents if e.label_ == "PERSON"]
    orgs_raw = [e.text.strip() for e in spacy_doc.ents if e.label_ == "ORG"]
    dates_raw = list(set(e.text.strip() for e in spacy_doc.ents if e.label_ == "DATE"))

    # Separate Dr. entities from general persons
    dr_pattern = re.compile(r'^\s*(?:Dr\.?|Prof\.?)\s+', re.IGNORECASE)
    persons = _clean_entities([p for p in persons_raw if not dr_pattern.match(p)])
    orgs = _clean_entities(orgs_raw)
    noun_chunks = [c.text.lower().strip() for c in spacy_doc.noun_chunks if len(c.text.strip()) > 2]
    keywords = [kw for kw, _ in Counter(noun_chunks).most_common(10)]

    # Medical extractions
    patient_name = _extract_patient_name(text, spacy_doc)
    doctor_name = _extract_doctor_name(text)
    patient_age = _extract_patient_age(text)
    patient_gender = _extract_gender(text)
    diagnoses = _extract_diagnoses(text)
    medications = _extract_medications(text, spacy_doc)
    dosage_mentioned = _extract_dosages(text)
    icd10_codes = _extract_icd10_codes(text)
    vital_signs = _extract_vital_signs(text)
    lab_tests = _extract_lab_tests(text)
    document_type = _detect_document_type(text)
    has_abnormal = any(t.get("flag") in ("HIGH", "LOW") for t in lab_tests)
    critical_count = sum(1 for t in lab_tests if t.get("flag") in ("HIGH", "LOW"))
    low_ocr_quality = confidence < LOW_OCR_THRESHOLD and confidence > 0

    processing_time = round(time.time() - t0, 2)

    logger.info(
        "Processed %s | size=%.1fKB | type=%s | ocr=%.1f%% | low_quality=%s | time=%.2fs",
        original_filename,
        os.path.getsize(file_path) / 1024,
        file_type,
        confidence,
        low_ocr_quality,
        processing_time,
    )

    return {
        "content": text,
        "filename": original_filename,
        "file_type": file_type,
        "page_count": page_count,
        "word_count": len(text.split()),
        "language": _detect_language(text),
        "confidence_score": confidence,
        "low_ocr_quality": low_ocr_quality,
        "processing_time_seconds": processing_time,
        "persons_mentioned": persons,
        "dates_in_document": _normalize_dates(dates_raw),
        "organizations_mentioned": orgs,
        "keywords": keywords,
        "patient_name": patient_name,
        "patient_age": patient_age,
        "patient_gender": patient_gender,
        "doctor_name": doctor_name,
        "diagnoses": diagnoses,
        "medications": medications,
        "dosage_mentioned": dosage_mentioned,
        "icd10_codes": icd10_codes,
        "lab_tests": lab_tests,
        "document_type": document_type,
        "has_abnormal_results": has_abnormal,
        "critical_flags_count": critical_count,
        **{f"vital_{k}": v for k, v in vital_signs.items()},
    }
