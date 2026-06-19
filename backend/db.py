import os
import logging
import psycopg2
import psycopg2.extras

logger = logging.getLogger(__name__)

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://docusearch:docusearch@postgres:5432/docusearch")

MIME_TYPES = {
    ".pdf": "application/pdf",
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
}


def get_conn():
    return psycopg2.connect(DATABASE_URL)


def init_db() -> None:
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                CREATE TABLE IF NOT EXISTS document_files (
                    id          VARCHAR(36)  PRIMARY KEY,
                    filename    VARCHAR(500) NOT NULL,
                    content     BYTEA        NOT NULL,
                    mime_type   VARCHAR(100),
                    file_size   INTEGER,
                    metadata    JSONB,
                    uploaded_at TIMESTAMPTZ  DEFAULT NOW()
                )
            """)
            # Add metadata column if upgrading from older schema
            cur.execute("""
                ALTER TABLE document_files
                ADD COLUMN IF NOT EXISTS metadata JSONB
            """)
        conn.commit()
    logger.info("PostgreSQL table ready")


def store_file(doc_id: str, filename: str, content: bytes, mime_type: str, metadata: dict | None = None) -> None:
    import json
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO document_files (id, filename, content, mime_type, file_size, metadata)
                VALUES (%s, %s, %s, %s, %s, %s)
                ON CONFLICT (id) DO UPDATE
                    SET content   = EXCLUDED.content,
                        mime_type = EXCLUDED.mime_type,
                        file_size = EXCLUDED.file_size,
                        metadata  = EXCLUDED.metadata
                """,
                (doc_id, filename, psycopg2.Binary(content), mime_type, len(content),
                 json.dumps(metadata) if metadata else None),
            )
        conn.commit()


def get_file(doc_id: str) -> tuple | None:
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT filename, content, mime_type FROM document_files WHERE id = %s",
                (doc_id,),
            )
            return cur.fetchone()


def get_file_owner(doc_id: str) -> str | None:
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT metadata->>'owner' FROM document_files WHERE id = %s",
                (doc_id,),
            )
            row = cur.fetchone()
            return row[0] if row else None


def delete_file(doc_id: str) -> None:
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM document_files WHERE id = %s", (doc_id,))
        conn.commit()
