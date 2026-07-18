"""
utils/db.py

Minimal SQLite persistence so users can see a trend across multiple
uploaded reports on the dashboard. Uses only the Python standard library
(sqlite3) — no extra dependency needed, matching the "MongoDB or SQLite"
option in the project spec.
"""

import sqlite3
import json
import os
from datetime import datetime, timezone

from config import settings

# Absolute path so it doesn't matter what directory the app is launched from.
DB_PATH = (
    settings.db_path
    if os.path.isabs(settings.db_path)
    else os.path.join(os.path.dirname(__file__), "..", settings.db_path)
)


def init_db():
    conn = sqlite3.connect(DB_PATH)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS reports (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            filename TEXT,
            uploaded_at TEXT,
            parameters_json TEXT,
            risks_json TEXT,
            health_score INTEGER
        )
    """)
    conn.commit()
    conn.close()


def save_report(filename: str, parameters: list, risks: list, health_score: int) -> int:
    conn = sqlite3.connect(DB_PATH)
    cur = conn.execute(
        "INSERT INTO reports (filename, uploaded_at, parameters_json, risks_json, health_score) "
        "VALUES (?, ?, ?, ?, ?)",
        (filename, datetime.now(timezone.utc).isoformat(), json.dumps(parameters), json.dumps(risks), health_score),
    )
    conn.commit()
    report_id = cur.lastrowid
    conn.close()
    return report_id


def get_report(report_id: int):
    conn = sqlite3.connect(DB_PATH)
    row = conn.execute(
        "SELECT id, filename, uploaded_at, parameters_json, risks_json, health_score "
        "FROM reports WHERE id = ?",
        (report_id,),
    ).fetchone()
    conn.close()
    if not row:
        return None
    return _row_to_dict(row)


def get_all_reports():
    conn = sqlite3.connect(DB_PATH)
    rows = conn.execute(
        "SELECT id, filename, uploaded_at, parameters_json, risks_json, health_score "
        "FROM reports ORDER BY uploaded_at ASC"
    ).fetchall()
    conn.close()
    return [_row_to_dict(r) for r in rows]


def _row_to_dict(row):
    return {
        "id": row[0],
        "filename": row[1],
        "uploaded_at": row[2],
        "parameters": json.loads(row[3]),
        "risks": json.loads(row[4]),
        "health_score": row[5],
    }
