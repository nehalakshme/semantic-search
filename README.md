# DocuSearch

A full-stack document search system with OCR, NLP metadata extraction, and natural language search. Everything runs locally — no external AI or cloud APIs required.

## Stack

| Layer | Technology |
|---|---|
| Backend | Python FastAPI |
| OCR | Tesseract + pdf2image + Pillow |
| NLP | spaCy `en_core_web_sm` |
| Search | Elasticsearch 8 |
| Frontend | React + Vite + Tailwind CSS |
| Containers | Docker Compose |

## Quick start

```bash
cd docusearch
docker-compose up --build
```

Open **http://localhost:3000** in your browser.

> The first build takes 5–10 minutes: Elasticsearch downloads, Python deps install, and spaCy downloads `en_core_web_sm`. Subsequent starts are fast.

## Example queries

```
invoice from Acme Corporation
reports mentioning John Smith
contract signed 29th May 2026
letter from last week
documents about machine learning
```

## Supported file types

| Type | Processing |
|---|---|
| PDF | Tesseract OCR via pdf2image (per-page) |
| PNG / JPG / JPEG | Tesseract OCR via Pillow |
| DOCX | python-docx text extraction (no OCR needed) |

## API endpoints

| Method | Path | Description |
|---|---|---|
| `POST` | `/api/upload` | Upload a document |
| `GET` | `/api/search?q=...` | Natural language search |
| `GET` | `/api/documents` | List all indexed documents |
| `DELETE` | `/api/documents/{id}` | Delete document + file |
| `GET` | `/api/files/{filename}` | Download original file |

## Ports

| Service | URL |
|---|---|
| Frontend | http://localhost:3000 |
| Backend API | http://localhost:8000 |
| Elasticsearch | http://localhost:9200 |

## Data persistence

Uploaded files are stored in `./data/uploads/` on your host machine and survive container restarts. Elasticsearch data is stored in the `esdata` Docker volume.

## How the NLP query parser works

The `query_parser.py` module uses spaCy NER and dateparser to decompose a free-text query into structured Elasticsearch filters — no external AI:

- **Person names** (spaCy `PERSON`) → filter `persons_mentioned`
- **Organization names** (spaCy `ORG`) → filter `organizations_mentioned`
- **Dates** (spaCy `DATE` + dateparser normalization) → filter `dates_in_document`
- **Doc-type keywords** (report, invoice, letter, contract, form, receipt) → filter `keywords`
- **Remaining text** → full-text `multi_match` on `content` + `filename` with fuzzy matching

## Environment variables

Copy `.env.example` to `.env` to customise:

```
ELASTICSEARCH_URL=http://elasticsearch:9200
UPLOAD_MAX_SIZE_MB=50
DATA_PATH=/data/uploads
```

## Stopping

```bash
docker-compose down          # stop containers, keep volumes
docker-compose down -v       # stop containers AND delete all data
```
