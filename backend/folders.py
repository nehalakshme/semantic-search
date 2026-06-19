"""Document folders with embedding-based auto-classification.

Each folder keeps a `centroid` = the mean of its member documents' text_vectors.
On upload we compare a new document's vector to every folder's centroid (cosine)
to suggest the best-matching folder. Folders are owned per-user.
"""
import json
import logging

from db import get_conn

logger = logging.getLogger(__name__)



def init_schema() -> None:
    conn = get_conn()
    try:
        with conn.cursor() as cur:
            cur.execute("""CREATE TABLE IF NOT EXISTS folders (
                id         SERIAL PRIMARY KEY,
                name       VARCHAR(200) NOT NULL,
                owner      VARCHAR(64)  NOT NULL,
                owner_node VARCHAR(64),
                centroid   JSONB,
                doc_count  INTEGER NOT NULL DEFAULT 0,
                created_at TIMESTAMPTZ DEFAULT NOW(),
                UNIQUE (owner, name))""")
        conn.commit()
    finally:
        conn.close()
    logger.info("Folders schema ready")


def create_folder(name: str, owner: str, owner_node: str | None) -> dict:
    conn = get_conn()
    try:
        with conn.cursor() as cur:
            cur.execute("""INSERT INTO folders (name, owner, owner_node) VALUES (%s, %s, %s)
                           ON CONFLICT (owner, name) DO UPDATE SET name = EXCLUDED.name
                           RETURNING id, name, doc_count""", (name, owner, owner_node))
            row = cur.fetchone()
        conn.commit()
        return {"id": row[0], "name": row[1], "doc_count": row[2]}
    finally:
        conn.close()


def list_folders(owner: str) -> list[dict]:
    conn = get_conn()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT id, name, doc_count FROM folders WHERE owner = %s ORDER BY name", (owner,))
            rows = cur.fetchall()
    finally:
        conn.close()
    return [{"id": r[0], "name": r[1], "doc_count": r[2]} for r in rows]


def get_folder(folder_id: int) -> dict | None:
    conn = get_conn()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT id, name, owner, owner_node FROM folders WHERE id = %s", (folder_id,))
            r = cur.fetchone()
    finally:
        conn.close()
    if not r:
        return None
    return {"id": r[0], "name": r[1], "owner": r[2], "owner_node": r[3]}



def folders_with_centroids(owner: str) -> list[dict]:
    conn = get_conn()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT id, name, centroid FROM folders WHERE owner = %s AND centroid IS NOT NULL", (owner,))
            rows = cur.fetchall()
    finally:
        conn.close()
    return [{"id": r[0], "name": r[1], "centroid": r[2]} for r in rows]


def set_centroid(folder_id: int, centroid: list[float] | None, count: int) -> None:
    conn = get_conn()
    try:
        with conn.cursor() as cur:
            cur.execute("UPDATE folders SET centroid = %s, doc_count = %s WHERE id = %s",
                        (json.dumps(centroid) if centroid is not None else None, count, folder_id))
        conn.commit()
    finally:
        conn.close()


def delete_folder(folder_id: int) -> None:
    conn = get_conn()
    try:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM folders WHERE id = %s", (folder_id,))
        conn.commit()
    finally:
        conn.close()
