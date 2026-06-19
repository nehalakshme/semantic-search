import logging
import os
import re
import tempfile
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

from fastapi import Depends, FastAPI, File, HTTPException, Query, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response
from pydantic import BaseModel

import numpy as np

import activity
import folders
import org
from auth import create_access_token, decode_token, get_current_user
from db import MIME_TYPES, delete_file, get_file, init_db, store_file
from es_client import ES_INDEX, MAPPING, create_index, get_es_client
from models import (answer, embed, generate_answer, is_ready, llm_ready,
                    load_embed_model, load_llm, load_qa_model, qa_ready)
from ocr import process_file
from query_parser import nlp as _qp_nlp, parse_query


RRF_K = 60  # Reciprocal Rank Fusion constant

# Folder suggestion thresholds (cosine of doc vs folder centroid).
# >= CONFIDENT  -> shown as a strong "Looks like X" recommendation
# >= SHOW       -> still surfaced as a softer "Closest match" hint
# In an all-medical corpus every doc is somewhat similar, so we also require the
# top folder to beat the runner-up by FOLDER_MARGIN — otherwise the match is
# ambiguous (e.g. a discharge summary ~equally close to every folder) and we
# suggest nothing.
# Calibrated against real data: genuine matches score >= 0.64, while an unrelated
# (but still medical) doc tops out around 0.50 — so the floor sits in that gap.
FOLDER_CONFIDENT_SCORE = float(os.getenv("FOLDER_SUGGEST_MIN_SCORE", "0.6"))
FOLDER_SHOW_SCORE = float(os.getenv("FOLDER_SHOW_MIN_SCORE", "0.55"))
FOLDER_MARGIN = float(os.getenv("FOLDER_MARGIN", "0.1"))

# Minimum semantic similarity to count as a match. Elasticsearch's cosine knn
# score is (1 + cosine)/2, so 0.5 = unrelated, 1.0 = identical. A floor here
# drops weak "filler" matches so semantic search only returns genuinely-close
# documents (no padding to a fixed count). Tune via the SEMANTIC_MIN_SCORE env var.
SEMANTIC_MIN_SCORE = float(os.getenv("SEMANTIC_MIN_SCORE", "0.6"))

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="DocuSearch API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

UPLOAD_MAX_BYTES = int(os.getenv("UPLOAD_MAX_SIZE_MB", "50")) * 1024 * 1024
ALLOWED_EXTENSIONS = {".pdf", ".png", ".jpg", ".jpeg", ".docx"}

MAGIC_BYTES: dict[bytes, set[str]] = {
    b"%PDF": {".pdf"},
    b"\x89PNG": {".png"},
    b"\xff\xd8\xff": {".jpg", ".jpeg"},
    b"PK\x03\x04": {".docx"},
}

_SEARCH_AGGS = {
    "by_document_type": {"terms": {"field": "document_type", "size": 10, "missing": "general"}},
    "by_gender": {"terms": {"field": "patient_gender", "size": 3}},
    "by_language": {"terms": {"field": "language", "size": 10}},
}


def _check_magic_bytes(content: bytes, ext: str) -> bool:
    for magic, valid_exts in MAGIC_BYTES.items():
        if content.startswith(magic):
            return ext in valid_exts
    return False


def _access_filter(user: dict) -> list[dict]:
    """ES filter restricting results to documents whose owner_node is in the
    user's subtree (across any hierarchy). Org roots see everything."""
    node = user.get("node")
    if org.is_root(node):
        return []
    if not node:
        return [{"terms": {"owner_node": []}}]  # no node => deny by default
    return [{"terms": {"owner_node": list(org.get_subtree(node))}}]


def _can_access(es, user: dict, doc_id: str) -> bool:
    """Whether `user` may view/download/delete the given document."""
    node = user.get("node")
    if org.is_root(node):
        return True
    if not node:
        return False
    try:
        src = es.get(index=ES_INDEX, id=doc_id, _source_includes=["owner_node"]).get("_source", {})
    except Exception:
        return False
    owner_node = src.get("owner_node")
    return owner_node is not None and owner_node in org.get_subtree(node)


async def require_admin(user: dict = Depends(get_current_user)) -> dict:
    if not org.is_root(user.get("node")):
        raise HTTPException(status_code=403, detail="Admin (org root) access required")
    return user


def _recompute_folder(es, folder_id: int) -> None:
    """Recompute a folder's centroid (mean of member vectors) and doc count."""
    try:
        resp = es.search(index=ES_INDEX, body={
            "query": {"term": {"folder_id": folder_id}},
            "size": 10000, "_source": ["text_vector"],
        })
    except Exception as exc:
        logger.warning("Folder recompute query failed for %s: %s", folder_id, exc)
        return
    vecs = [h["_source"]["text_vector"] for h in resp["hits"]["hits"] if h["_source"].get("text_vector")]
    count = resp["hits"]["total"]["value"]
    centroid = np.mean(np.array(vecs, dtype=float), axis=0).tolist() if vecs else None
    folders.set_centroid(folder_id, centroid, count)


def _classify_folder(vec: list[float] | None, owner: str) -> dict | None:
    """Suggest the best-matching folder for a document vector. Returns the top
    match (with a `confident` flag) only if it's reasonably close AND clearly
    ahead of the runner-up folder."""
    if vec is None:
        return None
    candidates = folders.folders_with_centroids(owner)
    if not candidates:
        return None
    v = np.array(vec, dtype=float)
    vn = np.linalg.norm(v)
    scored = []
    for c in candidates:
        cen = np.array(c["centroid"], dtype=float)
        denom = vn * np.linalg.norm(cen)
        if denom == 0:
            continue
        scored.append((float(np.dot(v, cen) / denom), c))
    if not scored:
        return None
    scored.sort(key=lambda x: x[0], reverse=True)
    best_score, best_c = scored[0]
    runner_up = scored[1][0] if len(scored) > 1 else 0.0
    margin = best_score - runner_up

    if best_score < FOLDER_SHOW_SCORE:
        return None
    # With multiple folders, the winner must clearly stand out
    if len(scored) > 1 and margin < FOLDER_MARGIN:
        return None
    return {
        "id": best_c["id"],
        "name": best_c["name"],
        "score": round(best_score, 3),
        "confident": best_score >= FOLDER_CONFIDENT_SCORE,
    }


def _backfill_owner_nodes(es) -> None:
    """Tag any pre-existing documents that lack owner_node: map their owner
    username to a node; legacy ownerless docs go to a root (admin-only)."""
    try:
        resp = es.search(index=ES_INDEX, body={
            "query": {"bool": {"must_not": {"exists": {"field": "owner_node"}}}},
            "size": 10000, "_source": ["owner"],
        })
    except Exception as exc:
        logger.warning("Owner-node backfill query failed: %s", exc)
        return
    hits = resp["hits"]["hits"]
    if not hits:
        return
    roots = sorted(org.get_roots())
    default_node = roots[0] if roots else None
    updated = 0
    for h in hits:
        owner = h["_source"].get("owner")
        node = lvl = None
        if owner:
            u = org.get_user(owner)
            if u:
                node, lvl = u["node"], u["level"]
        if node is None:
            node = default_node
            lvl = org.node_level(node) if node else 1
        if node is None:
            continue
        try:
            es.update(index=ES_INDEX, id=h["_id"], body={"doc": {"owner_node": node, "owner_level": lvl}})
            updated += 1
        except Exception as exc:
            logger.warning("Backfill update failed for %s: %s", h["_id"], exc)
    logger.info("Backfilled owner_node on %d document(s)", updated)


def _backfill_owners(es) -> None:
    """Give legacy documents that have no `owner` a sensible uploader name,
    derived from the user occupying their owner_node (so they stop showing as
    'unknown')."""
    try:
        resp = es.search(index=ES_INDEX, body={
            "query": {"bool": {"must_not": {"exists": {"field": "owner"}}}},
            "size": 10000, "_source": ["owner_node"],
        })
    except Exception as exc:
        logger.warning("Owner backfill query failed: %s", exc)
        return
    updated = 0
    for h in resp["hits"]["hits"]:
        node = h["_source"].get("owner_node")
        uname = org.user_for_node(node) if node else None
        if not uname:
            continue
        try:
            es.update(index=ES_INDEX, id=h["_id"], body={"doc": {"owner": uname}})
            updated += 1
        except Exception as exc:
            logger.warning("Owner backfill update failed for %s: %s", h["_id"], exc)
    if updated:
        logger.info("Backfilled owner on %d document(s)", updated)


def _migrate_vector_index(es) -> None:
    """If the index exists but predates the text_vector field, recreate it with
    the new mapping and re-index existing docs (regenerating their embeddings),
    so nothing currently searchable is lost."""
    if not es.indices.exists(index=ES_INDEX):
        return  # create_index will build it fresh with the full mapping
    try:
        props = es.indices.get_mapping(index=ES_INDEX)[ES_INDEX]["mappings"].get("properties", {})
    except Exception as exc:
        logger.warning("Could not read index mapping: %s", exc)
        return
    if "text_vector" in props:
        return  # already migrated

    logger.info("Migrating index to add text_vector — reading existing docs...")
    try:
        existing = es.search(index=ES_INDEX, body={"query": {"match_all": {}}, "size": 10000})
        docs = existing["hits"]["hits"]
    except Exception as exc:
        logger.warning("Could not read existing docs for migration: %s", exc)
        docs = []

    es.indices.delete(index=ES_INDEX)
    es.indices.create(index=ES_INDEX, mappings=MAPPING)
    logger.info("Recreated index with text_vector mapping; re-indexing %d docs", len(docs))

    reindexed = with_vec = 0
    for hit in docs:
        src = hit["_source"]
        src.pop("text_vector", None)
        vec = embed(src.get("content", ""))
        if vec is not None:
            src["text_vector"] = vec
            with_vec += 1
        try:
            es.index(index=ES_INDEX, id=hit["_id"], body=src)
            reindexed += 1
        except Exception as exc:
            logger.warning("Re-index failed for %s: %s", hit["_id"], exc)
    logger.info("Migration complete — re-indexed %d/%d docs (%d with embeddings)",
                reindexed, len(docs), with_vec)


@app.on_event("startup")
async def startup() -> None:
    # Load the ML models once (graceful fallback if any fails)
    load_embed_model()
    load_qa_model()
    load_llm()  # local generative LLM via Ollama (pulls the model on first run)

    # Wait for Elasticsearch
    es = get_es_client()
    for attempt in range(20):
        try:
            if es.ping():
                logger.info("Elasticsearch is reachable")
                break
        except Exception as exc:
            logger.warning("Waiting for Elasticsearch (attempt %d/20): %s", attempt + 1, exc)
        time.sleep(5)
    else:
        logger.error("Elasticsearch not reachable after 20 attempts — continuing anyway")
    _migrate_vector_index(es)
    create_index(es)
    logger.info("All models ready" if is_ready() else "Startup complete (semantic search disabled)")

    # Wait for PostgreSQL
    for attempt in range(20):
        try:
            init_db()
            break
        except Exception as exc:
            logger.warning("Waiting for PostgreSQL (attempt %d/20): %s", attempt + 1, exc)
            time.sleep(3)
    else:
        logger.error("PostgreSQL not reachable after 20 attempts — continuing anyway")

    # Org reporting graph: schema, baseline seed, derived levels, then tag any
    # pre-existing documents with an owner_node.
    try:
        org.init_org_schema()
        org.seed_if_empty()
        org.recompute_levels()
        _backfill_owner_nodes(es)
        _backfill_owners(es)
        logger.info("Org graph ready (roots/admins: %s)", ", ".join(sorted(org.get_roots())) or "none")
    except Exception as exc:
        logger.error("Org graph init failed: %s", exc)

    try:
        folders.init_schema()
    except Exception as exc:
        logger.error("Folders init failed: %s", exc)

    try:
        activity.init_schema()
    except Exception as exc:
        logger.error("Activity init failed: %s", exc)


@app.get("/health")
async def health():
    es = get_es_client()
    es_ok = False
    try:
        es_ok = es.ping()
    except Exception:
        pass

    pg_ok = False
    try:
        from db import get_conn
        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT 1")
        pg_ok = True
    except Exception:
        pass

    status = "ok" if es_ok and pg_ok else "degraded"
    return {
        "status": status,
        "elasticsearch": "connected" if es_ok else "disconnected",
        "postgres": "connected" if pg_ok else "disconnected",
        "semantic_model": "loaded" if is_ready() else "unavailable",
        "qa_model": "loaded" if qa_ready() else "unavailable",
        "llm": "loaded" if llm_ready() else "unavailable",
    }


class LoginRequest(BaseModel):
    username: str
    password: str


@app.post("/token")
async def login(creds: LoginRequest):
    u = org.get_user(creds.username)
    if not u or u["password"] != creds.password:
        raise HTTPException(
            status_code=401,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    token = create_access_token({
        "sub": u["username"], "node": u["node"], "label": u["label"], "level": u["level"],
    })
    return {
        "access_token": token,
        "token_type": "bearer",
        "username": u["username"],
        "node": u["node"],
        "label": u["label"],
        "level": u["level"],
        "is_admin": org.is_root(u["node"]),
    }


@app.get("/me")
async def me(user: dict = Depends(get_current_user)):
    return {
        "username": user["username"],
        "node": user.get("node"),
        "label": user.get("label"),
        "level": user.get("level"),
        "is_admin": org.is_root(user.get("node")),
    }


@app.post("/upload")
async def upload_file(file: UploadFile = File(...), user: dict = Depends(get_current_user)):
    ext = Path(file.filename).suffix.lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file type '{ext}'. Allowed: {', '.join(sorted(ALLOWED_EXTENSIONS))}",
        )

    content = await file.read()

    if len(content) > UPLOAD_MAX_BYTES:
        raise HTTPException(
            status_code=400,
            detail=f"File is {len(content) // (1024 * 1024)} MB — exceeds the {UPLOAD_MAX_BYTES // (1024 * 1024)} MB limit.",
        )

    if not _check_magic_bytes(content, ext):
        raise HTTPException(
            status_code=400,
            detail=f"File content does not match extension '{ext}'. Please upload a genuine {ext.upper()} file.",
        )

    # Write to temp file for OCR (deleted immediately after)
    tmp_fd, tmp_path = tempfile.mkstemp(suffix=ext)
    try:
        with os.fdopen(tmp_fd, "wb") as f:
            f.write(content)
        metadata = process_file(tmp_path, file.filename)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    except Exception as exc:
        logger.exception("Processing failed for %s", file.filename)
        raise HTTPException(status_code=500, detail=f"Processing failed: {exc}")
    finally:
        if os.path.exists(tmp_path):
            os.unlink(tmp_path)

    file_id = str(uuid.uuid4())
    mime_type = MIME_TYPES.get(ext, "application/octet-stream")

    # Tag the document with its uploader's identity and org node for
    # hierarchy-based access control
    metadata["owner"] = user["username"]
    metadata["owner_node"] = user.get("node")
    metadata["owner_level"] = user.get("level")

    # Store binary + metadata in PostgreSQL (no embedding vector — kept lean)
    store_file(file_id, file.filename, content, mime_type, metadata)

    # Index metadata in Elasticsearch, adding the semantic embedding vector
    metadata["uploaded_at"] = datetime.now(timezone.utc).isoformat()
    es_doc = dict(metadata)
    vec = embed(metadata.get("content", ""))
    if vec is not None:
        es_doc["text_vector"] = vec
    es = get_es_client()
    es.index(index=ES_INDEX, id=file_id, body=es_doc)

    logger.info(
        "Stored %s in PostgreSQL | id=%s | size=%.1fKB | ocr=%.1f%% | time=%.2fs",
        file.filename, file_id,
        len(content) / 1024,
        metadata.get("confidence_score", 0),
        metadata.get("processing_time_seconds", 0),
    )

    activity.log(user["username"], "uploaded", file_id, file.filename, user.get("node"))

    # Suggest a folder by comparing this doc's vector to each folder's centroid
    suggestion = _classify_folder(vec, user["username"])

    return {
        "id": file_id,
        "metadata": metadata,
        "folder_suggestion": suggestion,
        "folders": folders.list_folders(user["username"]),
    }


@app.get("/files/{doc_id}")
async def serve_file(doc_id: str, request: Request, token: str | None = Query(None),
                     inline: bool = Query(False)):
    # Accept the token either from the Authorization header or a ?token= query
    # param so plain <a download> links work in the browser.
    auth_header = request.headers.get("Authorization", "")
    raw = token or (auth_header[7:] if auth_header.startswith("Bearer ") else None)
    user = decode_token(raw)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")

    es = get_es_client()
    if not _can_access(es, user, doc_id):
        raise HTTPException(status_code=403, detail="You do not have access to this document")

    row = get_file(doc_id)
    if not row:
        raise HTTPException(status_code=404, detail="File not found")
    filename, content, mime_type = row
    # inline => render in the browser (preview); otherwise force a download
    disposition = "inline" if inline else "attachment"
    return Response(
        content=bytes(content),
        media_type=mime_type or "application/octet-stream",
        headers={"Content-Disposition": f'{disposition}; filename="{filename}"'},
    )


def _hit_to_doc(hit: dict, match_type: str, score: float | None = None) -> dict:
    doc = dict(hit["_source"])
    doc.pop("text_vector", None)  # never ship the raw vector to the client
    doc["id"] = hit["_id"]
    doc["score"] = score if score is not None else hit.get("_score")
    doc["highlight"] = hit.get("highlight", {})
    doc["match_type"] = match_type
    return doc


def _rrf_merge(kw_hits: list, sem_hits: list, k: int = RRF_K, limit: int = 10) -> list[dict]:
    """Reciprocal Rank Fusion: 1/(rank+k) summed across both result lists."""
    scores: dict[str, float] = {}
    info: dict[str, dict] = {}

    def register(hit, list_key):
        _id = hit["_id"]
        slot = info.get(_id)
        if slot is None:
            info[_id] = {"hit": hit, "kw": False, "sem": False}
        elif list_key == "kw":
            slot["hit"] = hit  # prefer the keyword hit — it carries highlights
        info[_id][list_key] = True

    for rank, hit in enumerate(kw_hits, start=1):
        scores[hit["_id"]] = scores.get(hit["_id"], 0.0) + 1.0 / (rank + k)
        register(hit, "kw")
    for rank, hit in enumerate(sem_hits, start=1):
        scores[hit["_id"]] = scores.get(hit["_id"], 0.0) + 1.0 / (rank + k)
        register(hit, "sem")

    ordered = sorted(scores.items(), key=lambda kv: kv[1], reverse=True)
    results = []
    for _id, score in ordered[:limit]:
        slot = info[_id]
        match_type = "both" if slot["kw"] and slot["sem"] else ("keyword" if slot["kw"] else "semantic")
        results.append(_hit_to_doc(slot["hit"], match_type, score))
    return results


@app.get("/search")
async def search(
    q: str = Query(..., min_length=1),
    semantic: bool = Query(True),
    user: dict = Depends(get_current_user),
):
    es = get_es_client()
    owner_filter = _access_filter(user)

    # ── Query 1: existing keyword bool query (filters, NER fields, fuzzy) ──
    kw_body = parse_query(q)
    include_aggs = kw_body.pop("_aggs", False)
    if owner_filter:
        kw_body["query"] = {"bool": {"must": [kw_body["query"]], "filter": owner_filter}}
    if include_aggs:
        kw_body["aggs"] = _SEARCH_AGGS
    kw_body["_source"] = {"excludes": ["text_vector"]}
    try:
        kw_resp = es.search(index=ES_INDEX, body=kw_body)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))
    kw_hits = kw_resp["hits"]["hits"]

    # ── Query 2: semantic knn search (only when toggled on and model ready) ──
    use_semantic = semantic and is_ready()
    sem_hits = []
    if use_semantic:
        qvec = embed(q)
        if qvec is None:
            use_semantic = False
        else:
            knn = {"field": "text_vector", "query_vector": qvec, "k": 10, "num_candidates": 50}
            if owner_filter:
                knn["filter"] = {"bool": {"filter": owner_filter}}
            try:
                sem_resp = es.search(
                    index=ES_INDEX,
                    body={"knn": knn, "size": 10, "_source": {"excludes": ["text_vector"]}},
                )
                # Keep only genuinely-close matches; weak ones are dropped entirely
                sem_hits = [h for h in sem_resp["hits"]["hits"]
                            if h.get("_score", 0) >= SEMANTIC_MIN_SCORE]
            except Exception as exc:
                logger.warning("Semantic search failed, falling back to keyword: %s", exc)
                use_semantic = False

    # ── Merge ──
    if use_semantic:
        results = _rrf_merge(kw_hits, sem_hits, limit=10)
    else:
        results = [_hit_to_doc(hit, "keyword") for hit in kw_hits]

    aggs_raw = kw_resp.get("aggregations", {})
    aggregations = {
        key: {b["key"]: b["doc_count"] for b in aggs_raw.get(key, {}).get("buckets", [])}
        for key in _SEARCH_AGGS
    }

    no_match_hint = None
    if not results:
        no_match_hint = (
            f'No results for "{q}". '
            "Try patient name, doctor name, ICD-10 code, or diagnosis. "
            'Example: "Dr. Smith lab report" or "J18.9".'
        )

    return {
        "results": results,
        "total": len(results),
        "semantic": use_semantic,
        "aggregations": aggregations,
        "no_match_hint": no_match_hint,
    }


def _persons_in_question(text: str) -> list[str]:
    """Person names mentioned in the question (via spaCy NER)."""
    if _qp_nlp is None:
        return []
    try:
        return [e.text.strip() for e in _qp_nlp(text).ents
                if e.label_ == "PERSON" and len(e.text.strip()) > 1]
    except Exception:
        return []


class AskRequest(BaseModel):
    question: str


@app.post("/ask")
async def ask(body: AskRequest, user: dict = Depends(get_current_user)):
    """Retrieval-augmented Q&A: semantically retrieve the user's most relevant
    documents, extract the best answer span, and cite the sources."""
    q = body.question.strip()
    if not q:
        raise HTTPException(status_code=400, detail="Question is required")
    es = get_es_client()
    owner_filter = _access_filter(user)

    # ── Retrieve candidate documents: hybrid (semantic + keyword) so both
    # meaning-based and entity-specific questions surface the right docs ──
    hits, seen = [], set()

    def _add(hit_list):
        for h in hit_list:
            if h["_id"] not in seen:
                seen.add(h["_id"])
                hits.append(h)

    qvec = embed(q)
    if qvec is not None:
        knn = {"field": "text_vector", "query_vector": qvec, "k": 5, "num_candidates": 50}
        if owner_filter:
            knn["filter"] = {"bool": {"filter": owner_filter}}
        try:
            _add(es.search(index=ES_INDEX, body={
                "knn": knn, "size": 5, "_source": {"excludes": ["text_vector"]}})["hits"]["hits"])
        except Exception as exc:
            logger.warning("Ask retrieval (knn) failed: %s", exc)
    try:
        _add(es.search(index=ES_INDEX, body={
            "query": {"bool": {"must": [{"match": {"content": q}}], "filter": owner_filter}},
            "size": 5, "_source": {"excludes": ["text_vector"]}})["hits"]["hits"])
    except Exception as exc:
        logger.warning("Ask retrieval (keyword) failed: %s", exc)
    hits = hits[:6]

    # ── Entity-aware re-ranking: if the question names a person, only answer
    # from documents that actually mention them (fixes "diagnosis for Robert") ──
    persons = _persons_in_question(q)
    if persons:
        def _mentions(h):
            src = h["_source"]
            hay = " ".join([
                src.get("content", "") or "",
                src.get("patient_name") or "",
                src.get("doctor_name") or "",
                " ".join(src.get("persons_mentioned") or []),
            ]).lower()
            return any(p.lower() in hay for p in persons)
        focused = [h for h in hits if _mentions(h)]
        if focused:
            hits = focused

    sources = [{
        "id": h["_id"],
        "filename": h["_source"].get("filename"),
        "patient_name": h["_source"].get("patient_name"),
        "folder_name": h["_source"].get("folder_name"),
        "snippet": (h["_source"].get("content", "") or "")[:220].strip(),
    } for h in hits[:4]]

    # ── Generate the answer: local LLM (RAG) if available, else extractive QA ──
    if llm_ready() and hits:
        context = "\n\n".join(
            f"[Document: {h['_source'].get('filename')}]\n{(h['_source'].get('content', '') or '')[:1500]}"
            for h in hits[:4]
        )
        gen = generate_answer(q, context)
        if gen:
            return {"answer": gen, "mode": "generative", "sources": sources}

    # Fallback: extractive span across the retrieved docs
    best = None
    for h in hits:
        a = answer(q, h["_source"].get("content", ""))
        if a and a["answer"] and (best is None or a["score"] > best["score"]):
            best = {**a, "doc_id": h["_id"], "filename": h["_source"].get("filename")}

    if best and best["score"] >= 0.1:
        return {
            "answer": best["answer"],
            "mode": "extractive",
            "score": round(best["score"], 3),
            "answer_doc_id": best["doc_id"],
            "answer_filename": best["filename"],
            "sources": sources,
        }
    return {
        "answer": None,
        "mode": None,
        "score": 0,
        "sources": sources,
        "message": "I couldn't find a confident answer, but here are the most relevant documents.",
    }


@app.get("/suggest")
async def suggest(q: str = Query(..., min_length=1), user: dict = Depends(get_current_user)):
    es = get_es_client()
    owner_filter = _access_filter(user)
    suggestions = []
    try:
        # Prefix match on patient/doctor name keyword fields
        for field, label in [
            ("patient_name.keyword", "patient"),
            ("doctor_name.keyword", "doctor"),
        ]:
            res = es.search(
                index=ES_INDEX,
                body={
                    "size": 0,
                    "query": {"bool": {"filter": owner_filter}},
                    "aggs": {
                        "names": {
                            "terms": {
                                "field": field,
                                "size": 5,
                                "include": f"(?i){re.escape(q)}.*",
                            }
                        }
                    },
                },
            )
            for b in res["aggregations"]["names"]["buckets"]:
                if b["key"] and b["key"].strip():
                    suggestions.append({"text": b["key"], "type": label})

        # Substring match on diagnoses using text field (handles partial words)
        res = es.search(
            index=ES_INDEX,
            body={
                "size": 5,
                "_source": ["diagnoses"],
                "query": {
                    "bool": {
                        "must": [{"match_phrase_prefix": {"diagnoses": {"query": q, "max_expansions": 10}}}],
                        "filter": owner_filter,
                    }
                },
            },
        )
        seen: set[str] = set()
        for hit in res["hits"]["hits"]:
            for diag in (hit["_source"].get("diagnoses") or []):
                if q.lower() in diag.lower() and diag not in seen and len(diag) < 80:
                    seen.add(diag)
                    suggestions.append({"text": diag, "type": "diagnosis"})
                    if len(seen) >= 5:
                        break

    except Exception as exc:
        logger.warning("Suggest error: %s", exc)
    return {"suggestions": suggestions}


@app.get("/documents")
async def list_documents(user: dict = Depends(get_current_user)):
    es = get_es_client()
    owner_filter = _access_filter(user)
    query = {"bool": {"filter": owner_filter}} if owner_filter else {"match_all": {}}
    try:
        response = es.search(
            index=ES_INDEX,
            body={
                "query": query,
                "size": 500,
                "sort": [{"uploaded_at": {"order": "desc"}}],
                "_source": {"excludes": ["text_vector"]},
            },
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))

    results = []
    for hit in response["hits"]["hits"]:
        doc = dict(hit["_source"])
        doc["id"] = hit["_id"]
        results.append(doc)
    return {"documents": results}


@app.delete("/documents/{doc_id}")
async def delete_document(doc_id: str, user: dict = Depends(get_current_user)):
    es = get_es_client()
    if not _can_access(es, user, doc_id):
        raise HTTPException(status_code=403, detail="You do not have access to this document")
    # Capture details for the activity feed before the doc is gone
    try:
        src = es.get(index=ES_INDEX, id=doc_id, _source_includes=["filename", "owner_node"]).get("_source", {})
    except Exception:
        src = {}
    delete_file(doc_id)  # remove from PostgreSQL
    try:
        es.delete(index=ES_INDEX, id=doc_id)
    except Exception:
        raise HTTPException(status_code=404, detail="Document not found")
    activity.log(user["username"], "removed", doc_id, src.get("filename", "a document"), src.get("owner_node"))
    return {"deleted": doc_id}


@app.get("/stats")
async def get_stats(user: dict = Depends(get_current_user)):
    es = get_es_client()
    owner_filter = _access_filter(user)
    try:
        response = es.search(
            index=ES_INDEX,
            body={
                "size": 0,
                "query": {"bool": {"filter": owner_filter}},
                "aggs": {
                    "by_document_type": {"terms": {"field": "document_type", "size": 10, "missing": "general"}},
                    "by_file_type": {"terms": {"field": "file_type", "size": 10}},
                    "by_language": {"terms": {"field": "language", "size": 20}},
                    "uploads_per_month": {
                        "date_histogram": {
                            "field": "uploaded_at",
                            "calendar_interval": "month",
                            "format": "yyyy-MM",
                        }
                    },
                },
            },
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))

    aggs = response["aggregations"]
    return {
        "total": response["hits"]["total"]["value"],
        "by_document_type": {b["key"]: b["doc_count"] for b in aggs["by_document_type"]["buckets"]},
        "by_file_type": {b["key"]: b["doc_count"] for b in aggs["by_file_type"]["buckets"]},
        "by_language": {b["key"]: b["doc_count"] for b in aggs["by_language"]["buckets"]},
        "uploads_per_month": {
            b["key_as_string"]: b["doc_count"] for b in aggs["uploads_per_month"]["buckets"]
        },
    }


# ── Org administration (root-only) ──────────────────────────────────────────
class NodeIn(BaseModel):
    node_id: str
    label: str | None = None


class UserIn(BaseModel):
    username: str
    node: str
    password: str | None = None


class EdgeIn(BaseModel):
    child: str
    parent: str
    hierarchy: str = "default"


@app.get("/admin/org")
async def admin_get_org(user: dict = Depends(require_admin)):
    return org.get_org()


@app.post("/admin/nodes")
async def admin_add_node(body: NodeIn, user: dict = Depends(require_admin)):
    org.add_node(body.node_id, body.label)
    org.recompute_levels()
    return {"ok": True, "org": org.get_org()}


@app.post("/admin/users")
async def admin_upsert_user(body: UserIn, user: dict = Depends(require_admin)):
    org.upsert_user(body.username, body.node, body.password)
    return {"ok": True, "users": org.get_org()["users"]}


@app.post("/admin/edges")
async def admin_add_edge(body: EdgeIn, user: dict = Depends(require_admin)):
    org.add_edge(body.child, body.parent, body.hierarchy)
    return {"ok": True, "org": org.get_org()}


@app.delete("/admin/edges")
async def admin_remove_edge(body: EdgeIn, user: dict = Depends(require_admin)):
    org.remove_edge(body.child, body.parent, body.hierarchy)
    return {"ok": True, "org": org.get_org()}


# ── Folders + auto-classification ────────────────────────────────────────────
class FolderIn(BaseModel):
    name: str


class AssignIn(BaseModel):
    folder_id: int | None = None   # assign to existing folder
    new_folder: str | None = None  # or create a new folder by name
    # if both are None => make the document standalone


@app.get("/folders")
async def get_folders(user: dict = Depends(get_current_user)):
    return {"folders": folders.list_folders(user["username"])}


@app.post("/folders")
async def make_folder(body: FolderIn, user: dict = Depends(get_current_user)):
    name = body.name.strip()
    if not name:
        raise HTTPException(status_code=400, detail="Folder name is required")
    return folders.create_folder(name, user["username"], user.get("node"))


@app.delete("/folders/{folder_id}")
async def remove_folder(folder_id: int, user: dict = Depends(get_current_user)):
    f = folders.get_folder(folder_id)
    if not f or f["owner"] != user["username"]:
        raise HTTPException(status_code=404, detail="Folder not found")
    es = get_es_client()
    try:
        es.update_by_query(index=ES_INDEX, refresh=True, body={
            "query": {"term": {"folder_id": folder_id}},
            "script": {"source": "ctx._source.remove('folder_id'); ctx._source.remove('folder_name')"},
        })
    except Exception as exc:
        logger.warning("Failed to detach docs from folder %s: %s", folder_id, exc)
    folders.delete_folder(folder_id)
    return {"deleted": folder_id}


@app.put("/documents/{doc_id}/folder")
async def assign_folder(doc_id: str, body: AssignIn, user: dict = Depends(get_current_user)):
    es = get_es_client()
    if not _can_access(es, user, doc_id):
        raise HTTPException(status_code=403, detail="You do not have access to this document")
    try:
        prev = es.get(index=ES_INDEX, id=doc_id, _source_includes=["folder_id"]).get("_source", {})
    except Exception:
        raise HTTPException(status_code=404, detail="Document not found")
    old_folder = prev.get("folder_id")

    target_id = target_name = None
    if body.new_folder and body.new_folder.strip():
        f = folders.create_folder(body.new_folder.strip(), user["username"], user.get("node"))
        target_id, target_name = f["id"], f["name"]
    elif body.folder_id is not None:
        f = folders.get_folder(body.folder_id)
        if not f or f["owner"] != user["username"]:
            raise HTTPException(status_code=404, detail="Folder not found")
        target_id, target_name = f["id"], f["name"]

    if target_id is None:
        es.update(index=ES_INDEX, id=doc_id, refresh=True, body={
            "script": {"source": "ctx._source.remove('folder_id'); ctx._source.remove('folder_name')"}})
    else:
        es.update(index=ES_INDEX, id=doc_id, refresh=True,
                  body={"doc": {"folder_id": target_id, "folder_name": target_name}})

    # Keep centroids current for both the source and destination folders
    if old_folder and old_folder != target_id:
        _recompute_folder(es, old_folder)
    if target_id:
        _recompute_folder(es, target_id)

    return {"ok": True, "folder_id": target_id, "folder_name": target_name}


# ── Activity feed (subtree-scoped, polled for near-real-time updates) ─────────
@app.get("/activity")
async def get_activity(since: int = Query(0), user: dict = Depends(get_current_user)):
    node = user.get("node")
    # Roots see all activity; others see events within their subtree.
    owner_nodes = None if org.is_root(node) else (list(org.get_subtree(node)) if node else [])
    return {"events": activity.feed(owner_nodes, since_id=since)}
