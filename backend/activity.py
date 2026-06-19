"""Activity feed. Records upload/remove events tagged with the document's
owner_node so a manager can watch activity across their whole subtree.
The frontend polls /activity for a near-real-time stream."""
import logging

from db import get_conn

logger = logging.getLogger(__name__)


def init_schema() -> None:
    conn = get_conn()
    try:
        with conn.cursor() as cur:
            cur.execute("""CREATE TABLE IF NOT EXISTS activity (
                id         SERIAL PRIMARY KEY,
                actor      VARCHAR(64)  NOT NULL,
                action     VARCHAR(32)  NOT NULL,
                doc_id     VARCHAR(36),
                doc_name   VARCHAR(500),
                owner_node VARCHAR(64),
                created_at TIMESTAMPTZ DEFAULT NOW())""")
        conn.commit()
    finally:
        conn.close()
    logger.info("Activity schema ready")


def log(actor: str, action: str, doc_id: str, doc_name: str, owner_node: str | None) -> None:
    try:
        conn = get_conn()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    "INSERT INTO activity (actor, action, doc_id, doc_name, owner_node) "
                    "VALUES (%s, %s, %s, %s, %s)",
                    (actor, action, doc_id, doc_name, owner_node),
                )
            conn.commit()
        finally:
            conn.close()
    except Exception as exc:  # never let activity logging break the main action
        logger.warning("activity.log failed: %s", exc)


def feed(owner_nodes: list[str] | None, since_id: int = 0, limit: int = 50) -> list[dict]:
    """Events whose owner_node is in `owner_nodes` (None = all, for org roots),
    newest first, optionally only those newer than `since_id`."""
    conn = get_conn()
    try:
        with conn.cursor() as cur:
            if owner_nodes is None:
                cur.execute(
                    "SELECT id, actor, action, doc_id, doc_name, owner_node, created_at "
                    "FROM activity WHERE id > %s ORDER BY id DESC LIMIT %s",
                    (since_id, limit),
                )
            else:
                if not owner_nodes:
                    return []
                cur.execute(
                    "SELECT id, actor, action, doc_id, doc_name, owner_node, created_at "
                    "FROM activity WHERE owner_node = ANY(%s) AND id > %s ORDER BY id DESC LIMIT %s",
                    (owner_nodes, since_id, limit),
                )
            rows = cur.fetchall()
    finally:
        conn.close()
    return [{
        "id": r[0], "actor": r[1], "action": r[2], "doc_id": r[3],
        "doc_name": r[4], "owner_node": r[5],
        "created_at": r[6].isoformat() if r[6] else None,
    } for r in rows]
