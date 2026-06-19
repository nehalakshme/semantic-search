# DocuSearch

A **local-first medical document intelligence platform**. Upload scans, PDFs, and Word documents — DocuSearch OCRs them, extracts medical entities, makes them searchable by keyword *and* meaning, auto-organizes them into smart folders, enforces an organization's reporting hierarchy for access, streams a live activity feed, and answers questions about your documents with cited sources.

**Everything runs on your machine** — no external AI services, no cloud APIs. All ML models are local and baked into the image.

---

## ✨ Features

- **OCR + medical extraction** — Tesseract OCR (PDF/image) and direct DOCX parsing, then spaCy NER + medical regex pull out patient/doctor names, age, gender, **diagnoses, medications, dosages, ICD-10 codes, lab results (with HIGH/LOW/NORMAL flags), vital signs**, document type, and abnormal-result detection.
- **Hybrid search** — combines classic keyword search (BM25, fuzzy, partial-word) with **semantic vector search** (sentence-transformer embeddings + Elasticsearch kNN), fused via **Reciprocal Rank Fusion**. A toggle switches semantic on/off; each result is badged 🔵 Keyword / 🟣 Semantic / 🟢 Both.
- **Natural-language query parsing** — "patients over 50 with abnormal labs", "Dr. Nair prescriptions", "J18.9" are decomposed into structured filters via spaCy + regex, with medical synonym expansion.
- **Smart folders (auto-classification)** — each folder learns a **centroid** of its documents' embeddings; on upload the system suggests the best-matching folder (nearest-centroid with confidence + margin gating), or you keep it standalone.
- **Hierarchical access control** — users live in an **organization reporting graph** (depth-based levels, "reports-to" edges, **parallel hierarchies** and **matrix/multi-manager** support). You see a document if its owner is in your subtree; org roots are admins. Re-orgs are instant — no re-indexing.
- **Real-time activity feed** — a toggle-able panel shows uploads/removals across your subtree, polled live ("alice uploaded X · view").
- **Nested folder browsing** — browse by uploader → their document folders → documents; search results group matches *into* the folders that contain them.
- **In-browser file preview** — view the actual scan/PDF inline before downloading.
- **Document Q&A (RAG)** — ask a question, get an **extractive answer with cited source documents**, using semantic + keyword retrieval and entity-aware re-ranking. (An optional local-LLM generative path via Ollama is included but disabled by default.)

---

## 🏗️ Architecture

```
                          ┌─────────────────────────────┐
  Browser  ──:3000──►     │  frontend (nginx + React)   │
                          │   proxies /api/ ─────────────┼──► backend:8000
                          └─────────────────────────────┘
                                         │
                 ┌───────────────────────┼────────────────────────┐
                 ▼                        ▼                        ▼
        ┌─────────────────┐     ┌──────────────────┐     ┌─────────────────┐
        │  Elasticsearch  │     │   FastAPI backend │     │   PostgreSQL    │
        │  (search +      │     │  OCR · NER ·      │     │  file bytes ·   │
        │   dense_vector) │     │  embeddings · QA  │     │  org · folders  │
        └─────────────────┘     └──────────────────┘     └─────────────────┘
```

**PostgreSQL is the source of truth** (file bytes + structured data); **Elasticsearch is a rebuildable search/vector index**.

### Tech stack
| Layer | Technology |
|---|---|
| Backend | Python 3.11, FastAPI, Uvicorn |
| Search / vectors | Elasticsearch 8.11 (`dense_vector` kNN) |
| Database | PostgreSQL 15 |
| OCR | Tesseract, pdf2image (poppler), python-docx |
| NLP / NER | spaCy `en_core_web_sm` |
| Embeddings | `sentence-transformers` `all-MiniLM-L6-v2` (384-dim) |
| Q&A | `distilbert-base-cased-distilled-squad` (extractive) |
| Auth | JWT (PyJWT, HS256) |
| Frontend | React 18, Vite, Tailwind CSS |
| Orchestration | Docker Compose |

---

## 🚀 Quick start

```bash
cd docusearch
docker-compose up -d --build
```

Open **http://localhost:3000**.

> The first build downloads Elasticsearch, Python deps, and bakes the ML models (~10–15 min). Subsequent starts are fast. Everything runs offline afterward.

### Demo credentials
All passwords are `123`. Users sit in a 2-hierarchy demo org:

| User | Node | Role |
|---|---|---|
| `admin` | 3a | root — sees everything |
| `alice` | 2a | manager (clinical) |
| `dave` | 2x | manager (admin hierarchy) |
| `bob` | 1a | staff — reports to **both** alice & dave |
| `carol` | 1c | staff |

---

## 🔍 How the key pieces work

**Hybrid search** runs a keyword bool query and a kNN vector query in parallel, then merges them with Reciprocal Rank Fusion (`score = Σ 1/(rank+60)`). A cosine floor drops weak semantic matches.

**Smart folders** store each folder's centroid (mean of member embeddings) in PostgreSQL. On upload, the new document's embedding is compared (cosine) to every folder centroid; it's suggested only if it's both reasonably close *and* clearly ahead of the runner-up — so unrelated documents aren't force-filed.

**Access control** models the org as nodes + reporting edges. A recursive query computes your subtree; an Elasticsearch `terms` filter on `owner_node` restricts every search/list to documents you're allowed to see. Roots see all. Adding a parallel hierarchy is just edges with a new `hierarchy_id`.

**Q&A** retrieves relevant docs (semantic + keyword, access-filtered), restricts to docs mentioning any named person, then extracts the best answer span and cites its sources.

---

## 🔌 Selected API endpoints

| Method | Path | Description |
|---|---|---|
| `POST` | `/api/token` | Log in (JWT) |
| `POST` | `/api/upload` | Upload + OCR + extract + classify |
| `GET` | `/api/search?q=&semantic=` | Hybrid search |
| `POST` | `/api/ask` | Document Q&A with sources |
| `GET` | `/api/documents` · `DELETE /api/documents/{id}` | List / delete |
| `GET` | `/api/files/{id}?inline=` | Download or inline-preview |
| `GET/POST/DELETE` | `/api/folders` · `PUT /api/documents/{id}/folder` | Folders |
| `GET` | `/api/activity?since=` | Subtree activity feed |
| `*` | `/api/admin/{org,nodes,users,edges}` | Org admin (root only) |
| `GET` | `/api/health` | Service + model status |

---

## 📁 Project structure

```
docusearch/
├── docker-compose.yml
├── backend/
│   ├── main.py           # FastAPI app + all endpoints
│   ├── ocr.py            # OCR + medical entity extraction
│   ├── query_parser.py   # NL query → ES filters
│   ├── es_client.py      # Elasticsearch index mapping
│   ├── db.py             # PostgreSQL (file storage)
│   ├── models.py         # embeddings, QA, (optional) LLM
│   ├── auth.py           # JWT
│   ├── org.py            # org graph (RBAC)
│   ├── folders.py        # folders + centroids
│   ├── activity.py       # activity log
│   └── org_seed.json     # initial org / users
└── frontend/
    └── src/
        ├── App.jsx
        ├── api.js
        └── components/   # Header, SearchBar, ResultCard, UploadModal,
                          # FilterSidebar, ActivityPanel, AskModal, … 
```

## 🔧 Ports

| Service | URL |
|---|---|
| Frontend | http://localhost:3000 |
| Backend API | http://localhost:8000 |
| Elasticsearch | http://localhost:9200 |
| PostgreSQL | localhost:5432 |

## 🛑 Stopping

```bash
docker-compose down       # stop, keep data
docker-compose down -v    # stop and delete all data (ES + Postgres volumes)
```

---

## ⚠️ Notes

- **Demo only:** credentials are seeded in plaintext (`org_seed.json`) and `AUTH_SECRET` has a default. For any real deployment, move secrets to environment variables, hash passwords, and don't commit them.
- **Local-only by design:** no document or query data leaves your machine.
- **Optional generative Q&A:** the Ollama LLM path is wired but off by default (it needs ~8 GB Docker RAM); the app falls back to extractive Q&A automatically.

---

*Built as a demonstration of combining OCR, NLP, vector search, and retrieval-augmented Q&A into a single self-hosted application.*
