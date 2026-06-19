"""Local ML models. The sentence-transformers embedding model is loaded once at
startup and reused for every upload/search — never reloaded per request.

If the model fails to load, semantic search is disabled gracefully and the rest
of the app keeps working in keyword-only mode."""
import logging
import os

import requests

logger = logging.getLogger(__name__)

EMBED_MODEL_NAME = "all-MiniLM-L6-v2"
EMBED_DIMS = 384
QA_MODEL_NAME = "distilbert-base-cased-distilled-squad"

OLLAMA_URL = os.getenv("OLLAMA_URL", "http://ollama:11434")
LLM_MODEL = os.getenv("LLM_MODEL", "llama3.2:3b")

_embed_model = None
_qa_model = None
_llm_ready = False


def load_embed_model() -> bool:
    """Load the semantic embedding model into memory. Returns True on success."""
    global _embed_model
    try:
        logger.info("Loading semantic model (%s)...", EMBED_MODEL_NAME)
        from sentence_transformers import SentenceTransformer
        _embed_model = SentenceTransformer(EMBED_MODEL_NAME)
        # Warm up so the first real request isn't slow
        _embed_model.encode("warmup", normalize_embeddings=True)
        logger.info("Semantic model loaded and ready")
        return True
    except Exception as exc:
        logger.error("Failed to load semantic model: %s — semantic search disabled", exc)
        _embed_model = None
        return False


def is_ready() -> bool:
    return _embed_model is not None


def embed(text: str) -> list[float] | None:
    """Return a 384-dim embedding for the text, or None if unavailable/empty."""
    if _embed_model is None or not text or not text.strip():
        return None
    try:
        # Truncate very long text — MiniLM only uses the first ~256 tokens anyway,
        # and this keeps encoding fast.
        vec = _embed_model.encode(text[:5000], normalize_embeddings=True)
        return vec.tolist()
    except Exception as exc:
        logger.warning("Embedding failed: %s", exc)
        return None


def load_qa_model() -> bool:
    """Load the extractive question-answering model. Returns True on success."""
    global _qa_model
    try:
        logger.info("Loading QA model (%s)...", QA_MODEL_NAME)
        from transformers import pipeline
        _qa_model = pipeline("question-answering", model=QA_MODEL_NAME, tokenizer=QA_MODEL_NAME)
        _qa_model(question="warm up?", context="This is a warm up context for the model.")
        logger.info("QA model loaded and ready")
        return True
    except Exception as exc:
        logger.error("Failed to load QA model: %s — Q&A disabled", exc)
        _qa_model = None
        return False


def qa_ready() -> bool:
    return _qa_model is not None


def answer(question: str, context: str) -> dict | None:
    """Extract the best answer span for `question` from `context`. The pipeline
    internally slides over long context. Returns {answer, score} or None."""
    if _qa_model is None or not question or not context or not context.strip():
        return None
    try:
        res = _qa_model(question=question, context=context[:6000], max_answer_len=80)
        return {"answer": res["answer"].strip(), "score": float(res["score"])}
    except Exception as exc:
        logger.warning("QA failed: %s", exc)
        return None


# ── Local generative LLM (Ollama) for RAG ────────────────────────────────────
def load_llm(pull_if_missing: bool = True) -> bool:
    """Check the Ollama server is up and the model is available; pull it if not.
    Sets a readiness flag used by the /ask endpoint."""
    global _llm_ready
    try:
        tags = requests.get(f"{OLLAMA_URL}/api/tags", timeout=5).json()
        have = any(m.get("name", "").startswith(LLM_MODEL.split(":")[0]) for m in tags.get("models", []))
        if not have and pull_if_missing:
            logger.info("Pulling LLM '%s' via Ollama (first run, may take a few minutes)...", LLM_MODEL)
            # streaming pull; block until complete
            with requests.post(f"{OLLAMA_URL}/api/pull", json={"name": LLM_MODEL},
                               stream=True, timeout=3600) as r:
                for _ in r.iter_lines():
                    pass
            have = True
        _llm_ready = bool(have)
        logger.info("LLM ready (%s)" if _llm_ready else "LLM model unavailable", LLM_MODEL)
    except Exception as exc:
        logger.error("Ollama not reachable: %s — generative answers disabled", exc)
        _llm_ready = False
    return _llm_ready


def llm_ready() -> bool:
    return _llm_ready


_RAG_SYSTEM = (
    "You are a careful medical-records assistant. Answer the QUESTION using ONLY the "
    "CONTEXT below, which are excerpts from the user's own documents. Cite the document "
    "name(s) you used. If the answer is not in the context, say "
    "\"I couldn't find that in your documents.\" Be concise and do not invent facts."
)


def generate_answer(question: str, context: str) -> str | None:
    """Generate a grounded answer from the retrieved context via the local LLM."""
    if not _llm_ready or not question:
        return None
    prompt = f"{_RAG_SYSTEM}\n\nCONTEXT:\n{context}\n\nQUESTION: {question}\n\nANSWER:"
    try:
        r = requests.post(
            f"{OLLAMA_URL}/api/generate",
            json={
                "model": LLM_MODEL,
                "prompt": prompt,
                "stream": False,
                "options": {"temperature": 0.2, "num_predict": 300},
            },
            timeout=120,
        )
        r.raise_for_status()
        return (r.json().get("response") or "").strip() or None
    except Exception as exc:
        logger.warning("LLM generation failed: %s", exc)
        return None
