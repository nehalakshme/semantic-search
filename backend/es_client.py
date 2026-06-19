import os
import logging
from elasticsearch import Elasticsearch

logger = logging.getLogger(__name__)

ES_INDEX = "documents"
ES_URL = os.getenv("ELASTICSEARCH_URL", "http://localhost:9200")

MAPPING = {
    "properties": {
        "owner": {"type": "keyword"},
        "owner_node": {"type": "keyword"},
        "owner_level": {"type": "integer"},
        "folder_id": {"type": "integer"},
        "folder_name": {"type": "keyword"},
        "content": {"type": "text"},
        "filename": {"type": "keyword"},
        "stored_filename": {"type": "keyword"},
        "file_type": {"type": "keyword"},
        "file_path": {"type": "keyword"},
        "persons_mentioned": {"type": "keyword"},
        "dates_in_document": {"type": "keyword"},
        "organizations_mentioned": {"type": "keyword"},
        "keywords": {"type": "keyword"},
        "language": {"type": "keyword"},
        "uploaded_at": {"type": "date"},
        "word_count": {"type": "integer"},
        "page_count": {"type": "integer"},
        "confidence_score": {"type": "float"},
        "low_ocr_quality": {"type": "boolean"},
        "processing_time_seconds": {"type": "float"},
        "patient_name": {
            "type": "text",
            "fields": {"keyword": {"type": "keyword", "ignore_above": 256}},
        },
        "patient_age": {"type": "integer"},
        "patient_gender": {"type": "keyword"},
        "doctor_name": {
            "type": "text",
            "fields": {"keyword": {"type": "keyword", "ignore_above": 256}},
        },
        "diagnoses": {
            "type": "text",
            "fields": {"keyword": {"type": "keyword", "ignore_above": 512}},
        },
        "medications": {
            "type": "text",
            "fields": {"keyword": {"type": "keyword", "ignore_above": 256}},
        },
        "dosage_mentioned": {"type": "keyword"},
        "icd10_codes": {"type": "keyword"},
        "lab_tests": {
            "type": "nested",
            "properties": {
                "name": {"type": "keyword"},
                "result": {"type": "keyword"},
                "flag": {"type": "keyword"},
            },
        },
        "document_type": {"type": "keyword"},
        "has_abnormal_results": {"type": "boolean"},
        "critical_flags_count": {"type": "integer"},
        "vital_blood_pressure": {"type": "keyword"},
        "vital_heart_rate": {"type": "keyword"},
        "vital_temperature": {"type": "keyword"},
        "vital_spo2": {"type": "keyword"},
        "vital_bmi": {"type": "keyword"},
        "text_vector": {
            "type": "dense_vector",
            "dims": 384,
            "index": True,
            "similarity": "cosine",
        },
    }
}

_NEW_FIELDS = {
    k: v for k, v in MAPPING["properties"].items()
    if k not in {
        "content", "filename", "stored_filename", "file_type", "file_path",
        "persons_mentioned", "dates_in_document", "organizations_mentioned",
        "keywords", "language", "uploaded_at", "word_count", "page_count",
        "confidence_score",
        # fields added in v2 upgrade — skip if already exist
        "patient_name", "patient_age", "doctor_name", "diagnoses", "medications",
        "lab_tests", "document_type", "has_abnormal_results", "critical_flags_count",
        # text_vector is handled by a dedicated recreate+reindex migration
        "text_vector",
    }
}


def get_es_client() -> Elasticsearch:
    return Elasticsearch(ES_URL)


def create_index(es: Elasticsearch) -> None:
    if es.indices.exists(index=ES_INDEX):
        try:
            es.indices.put_mapping(index=ES_INDEX, properties=_NEW_FIELDS)
            logger.info("Updated index '%s' mapping", ES_INDEX)
        except Exception as exc:
            logger.warning("Mapping update skipped (may already exist): %s", exc)
    else:
        es.indices.create(index=ES_INDEX, mappings=MAPPING)
        logger.info("Created Elasticsearch index '%s'", ES_INDEX)
