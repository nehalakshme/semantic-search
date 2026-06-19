"""Organizational reporting graph + role assignment.

Model
-----
* org_node  — a position. `level` is auto-derived from tree depth (leaf=1, up=2,3...).
* org_edge  — a reporting line "child reports to parent" within a `hierarchy_id`.
              Multiple edges per child (different hierarchies) = matrix / multi-parent.
* org_user  — a person occupying a node.

Access policy (union model): you can see a document whose `owner_node` is anywhere
in YOUR subtree across ANY hierarchy. Roots (top of a tree) are admins and see all.
Parallel hierarchies are isolated by `hierarchy_id` — add edges with a new id and
nothing else changes.
"""
import json
import logging
import os
from collections import defaultdict

from db import get_conn

logger = logging.getLogger(__name__)

SEED_PATH = os.path.join(os.path.dirname(__file__), "org_seed.json")

# In-memory caches (invalidated whenever edges/levels change)
_subtree_cache: dict[str, set[str]] = {}
_roots_cache: set[str] | None = None


# ── low-level query helper (closes the connection — avoids leaks on the hot path) ──
def _run(sql, params=None, fetch=None, commit=False):
    conn = get_conn()
    try:
        with conn.cursor() as cur:
            cur.execute(sql, params or ())
            result = cur.fetchone() if fetch == "one" else cur.fetchall() if fetch == "all" else None
        if commit:
            conn.commit()
        return result
    finally:
        conn.close()


def init_org_schema() -> None:
    conn = get_conn()
    try:
        with conn.cursor() as cur:
            cur.execute("""CREATE TABLE IF NOT EXISTS org_node (
                node_id VARCHAR(64) PRIMARY KEY,
                label   VARCHAR(64) NOT NULL,
                level   INTEGER NOT NULL DEFAULT 1)""")
            cur.execute("""CREATE TABLE IF NOT EXISTS org_edge (
                child_id     VARCHAR(64) NOT NULL,
                parent_id    VARCHAR(64) NOT NULL,
                hierarchy_id VARCHAR(64) NOT NULL DEFAULT 'default',
                PRIMARY KEY (child_id, parent_id, hierarchy_id))""")
            cur.execute("""CREATE TABLE IF NOT EXISTS org_user (
                username VARCHAR(64) PRIMARY KEY,
                password VARCHAR(255) NOT NULL,
                node_id  VARCHAR(64) NOT NULL)""")
        conn.commit()
    finally:
        conn.close()
    logger.info("Org schema ready")


def seed_if_empty() -> None:
    """Load the baseline org from org_seed.json only if no users exist yet."""
    if (_run("SELECT COUNT(*) FROM org_user", fetch="one") or [0])[0] > 0:
        return
    if not os.path.exists(SEED_PATH):
        logger.warning("Org seed file not found: %s", SEED_PATH)
        return
    with open(SEED_PATH, encoding="utf-8") as f:
        data = json.load(f)
    conn = get_conn()
    try:
        with conn.cursor() as cur:
            for n in data.get("nodes", []):
                cur.execute("INSERT INTO org_node (node_id, label, level) VALUES (%s, %s, 1) "
                            "ON CONFLICT (node_id) DO NOTHING", (n["id"], n.get("label", n["id"])))
            for e in data.get("edges", []):
                cur.execute("INSERT INTO org_edge (child_id, parent_id, hierarchy_id) VALUES (%s, %s, %s) "
                            "ON CONFLICT DO NOTHING", (e["child"], e["parent"], e.get("hierarchy", "default")))
            for u in data.get("users", []):
                cur.execute("INSERT INTO org_user (username, password, node_id) VALUES (%s, %s, %s) "
                            "ON CONFLICT (username) DO UPDATE SET node_id = EXCLUDED.node_id",
                            (u["username"], u["password"], u["node"]))
        conn.commit()
    finally:
        conn.close()
    logger.info("Seeded org graph from %s", SEED_PATH)


def recompute_levels() -> None:
    """Derive each node's level from depth (leaf=1, else 1 + max child level),
    unioning children across all hierarchies. Cycle-guarded."""
    nodes = [r[0] for r in (_run("SELECT node_id FROM org_node", fetch="all") or [])]
    edges = _run("SELECT child_id, parent_id FROM org_edge", fetch="all") or []
    children: dict[str, set[str]] = defaultdict(set)
    for child, parent in edges:
        children[parent].add(child)

    memo: dict[str, int] = {}

    def level(n: str, stack: frozenset) -> int:
        if n in memo:
            return memo[n]
        kids = [c for c in children.get(n, ()) if c not in stack and c != n]
        lv = 1 if not kids else 1 + max(level(c, stack | {n}) for c in kids)
        memo[n] = lv
        return lv

    conn = get_conn()
    try:
        with conn.cursor() as cur:
            for n in nodes:
                cur.execute("UPDATE org_node SET level = %s WHERE node_id = %s", (level(n, frozenset()), n))
        conn.commit()
    finally:
        conn.close()
    invalidate_cache()


def invalidate_cache() -> None:
    global _subtree_cache, _roots_cache
    _subtree_cache = {}
    _roots_cache = None


def get_subtree(node_id: str) -> set[str]:
    """All node_ids at or below `node_id` across every hierarchy (cached)."""
    if node_id in _subtree_cache:
        return _subtree_cache[node_id]
    rows = _run("""
        WITH RECURSIVE sub AS (
            SELECT %s::varchar AS node_id
            UNION
            SELECT e.child_id FROM org_edge e JOIN sub s ON e.parent_id = s.node_id
        ) SELECT node_id FROM sub
    """, (node_id,), fetch="all") or []
    result = {r[0] for r in rows}
    result.add(node_id)
    _subtree_cache[node_id] = result
    return result


def get_roots() -> set[str]:
    """Nodes that report to no one (tops of trees) — treated as admins."""
    global _roots_cache
    if _roots_cache is None:
        rows = _run("SELECT node_id FROM org_node WHERE node_id NOT IN "
                    "(SELECT child_id FROM org_edge)", fetch="all") or []
        _roots_cache = {r[0] for r in rows}
    return _roots_cache


def is_root(node_id: str | None) -> bool:
    return bool(node_id) and node_id in get_roots()


def user_for_node(node_id: str) -> str | None:
    """A username occupying the given node (first by name), or None."""
    row = _run("SELECT username FROM org_user WHERE node_id = %s ORDER BY username LIMIT 1",
               (node_id,), fetch="one")
    return row[0] if row else None


def node_level(node_id: str) -> int:
    row = _run("SELECT level FROM org_node WHERE node_id = %s", (node_id,), fetch="one")
    return row[0] if row else 1


def get_user(username: str) -> dict | None:
    row = _run("""SELECT u.username, u.password, u.node_id, n.label, n.level
                  FROM org_user u LEFT JOIN org_node n ON u.node_id = n.node_id
                  WHERE u.username = %s""", (username,), fetch="one")
    if not row:
        return None
    return {"username": row[0], "password": row[1], "node": row[2],
            "label": row[3] or row[2], "level": row[4] or 1}


# ── admin mutations (called from /admin endpoints) ──
def add_node(node_id: str, label: str | None = None) -> None:
    _run("INSERT INTO org_node (node_id, label, level) VALUES (%s, %s, 1) "
         "ON CONFLICT (node_id) DO NOTHING", (node_id, label or node_id), commit=True)
    invalidate_cache()


def upsert_user(username: str, node_id: str, password: str | None = None) -> None:
    if password:
        _run("INSERT INTO org_user (username, password, node_id) VALUES (%s, %s, %s) "
             "ON CONFLICT (username) DO UPDATE SET node_id = EXCLUDED.node_id, password = EXCLUDED.password",
             (username, password, node_id), commit=True)
    else:
        _run("INSERT INTO org_user (username, password, node_id) VALUES (%s, '', %s) "
             "ON CONFLICT (username) DO UPDATE SET node_id = EXCLUDED.node_id",
             (username, node_id), commit=True)


def add_edge(child: str, parent: str, hierarchy: str = "default") -> None:
    _run("INSERT INTO org_edge (child_id, parent_id, hierarchy_id) VALUES (%s, %s, %s) "
         "ON CONFLICT DO NOTHING", (child, parent, hierarchy), commit=True)
    recompute_levels()  # also invalidates caches


def remove_edge(child: str, parent: str, hierarchy: str = "default") -> None:
    _run("DELETE FROM org_edge WHERE child_id = %s AND parent_id = %s AND hierarchy_id = %s",
         (child, parent, hierarchy), commit=True)
    recompute_levels()


def get_org() -> dict:
    nodes = [{"id": r[0], "label": r[1], "level": r[2]}
             for r in (_run("SELECT node_id, label, level FROM org_node ORDER BY level DESC, node_id", fetch="all") or [])]
    edges = [{"child": r[0], "parent": r[1], "hierarchy": r[2]}
             for r in (_run("SELECT child_id, parent_id, hierarchy_id FROM org_edge", fetch="all") or [])]
    users = [{"username": r[0], "node": r[1]}
             for r in (_run("SELECT username, node_id FROM org_user ORDER BY username", fetch="all") or [])]
    return {"nodes": nodes, "edges": edges, "users": users}
