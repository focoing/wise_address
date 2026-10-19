from __future__ import annotations

import json
import sqlite3
from fastapi import HTTPE
import uuid
from datetime import datetime, timezone
from pathlib import Path
xception

from app.models import (
    AgentResponse,
    AnalysisRequest,
    AnalysisResponse,
    HistorySessionDetail,
    HistorySessionSummary,
    HistoryTurn,
)
from app.services.analysis import MODULE_NAMES


DATA_DIR = Path(__file__).resolve().parents[2] / "data"
DB_PATH = DATA_DIR / "shangshu_history.db"


def init_history_db() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    with _connect() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS sessions (
                id TEXT PRIMARY KEY,
                title TEXT NOT NULL,
                module TEXT NOT NULL,
                lng REAL NOT NULL,
                lat REAL NOT NULL,
                location_key TEXT NOT NULL,
                address TEXT NOT NULL,
                district TEXT,
                latest_question TEXT NOT NULL,
                latest_score INTEGER,
                turn_count INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS turns (
                id TEXT PRIMARY KEY,
                session_id TEXT NOT NULL,
                question TEXT NOT NULL,
                answer TEXT NOT NULL,
                request_json TEXT NOT NULL,
                analysis_json TEXT NOT NULL,
                used_model TEXT NOT NULL,
                fallback INTEGER NOT NULL,
                created_at TEXT NOT NULL,
                FOREIGN KEY(session_id) REFERENCES sessions(id) ON DELETE CASCADE
            )
            """
        )
        conn.execute("CREATE INDEX IF NOT EXISTS idx_sessions_context ON sessions(module, location_key)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_turns_session ON turns(session_id, created_at)")


def save_agent_history(
    request: AnalysisRequest,
    analysis: AnalysisResponse,
    response: AgentResponse,
) -> tuple[str, str]:
    init_history_db()
    now = _now()
    location_key = _location_key(request)
    title = _title(request)
    with _connect() as conn:
        session = conn.execute(
            """
            SELECT id FROM sessions
            WHERE module = ? AND location_key = ?
            ORDER BY updated_at DESC
            LIMIT 1
            """,
            (request.module.value, location_key),
        ).fetchone()
        session_id = str(session["id"]) if session else uuid.uuid4().hex
        turn_id = uuid.uuid4().hex

        if session:
            conn.execute(
                """
                UPDATE sessions
                SET title = ?, address = ?, district = ?, latest_question = ?, latest_score = ?,
                    turn_count = turn_count + 1, updated_at = ?
                WHERE id = ?
                """,
                (
                    title,
                    request.location.address or "",
                    request.location.district,
                    request.question,
                    analysis.score,
                    now,
                    session_id,
                ),
            )
        else:
            conn.execute(
                """
                INSERT INTO sessions (
                    id, title, module, lng, lat, location_key, address, district,
                    latest_question, latest_score, turn_count, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    session_id,
                    title,
                    request.module.value,
                    request.location.lng,
                    request.location.lat,
                    location_key,
                    request.location.address or "",
                    request.location.district,
                    request.question,
                    analysis.score,
                    1,
                    now,
                    now,
                ),
            )

        conn.execute(
            """
            INSERT INTO turns (
                id, session_id, question, answer, request_json, analysis_json,
                used_model, fallback, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                turn_id,
                session_id,
                request.question,
                response.answer,
                request.model_dump_json(),
                analysis.model_dump_json(),
                response.usedModel,
                1 if response.fallback else 0,
                now,
            ),
        )
    return session_id, turn_id


def list_sessions() -> list[HistorySessionSummary]:
    init_history_db()
    with _connect() as conn:
        rows = conn.execute(
            """
            SELECT * FROM sessions
            ORDER BY updated_at DESC
            """
        ).fetchall()
    return [_session_summary(row) for row in rows]


def get_session_detail(session_id: str) -> HistorySessionDetail:
    init_history_db()
    with _connect() as conn:
        session = conn.execute("SELECT * FROM sessions WHERE id = ?", (session_id,)).fetchone()
        if not session:
            raise HTTPException(status_code=404, detail="历史会话不存在")
        turns = conn.execute(
            "SELECT * FROM turns WHERE session_id = ? ORDER BY created_at ASC",
            (session_id,),
        ).fetchall()
    return HistorySessionDetail(
        session=_session_summary(session),
        turns=[_turn(row) for row in turns],
    )


def delete_session(session_id: str) -> dict[str, str]:
    init_history_db()
    with _connect() as conn:
        exists = conn.execute("SELECT id FROM sessions WHERE id = ?", (session_id,)).fetchone()
        if not exists:
            raise HTTPException(status_code=404, detail="历史会话不存在")
        conn.execute("DELETE FROM sessions WHERE id = ?", (session_id,))
    return {"status": "deleted", "id": session_id}


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def _session_summary(row: sqlite3.Row) -> HistorySessionSummary:
    return HistorySessionSummary(
        id=row["id"],
        title=row["title"],
        module=row["module"],
        address=row["address"],
        district=row["district"],
        lng=row["lng"],
        lat=row["lat"],
        latestQuestion=row["latest_question"],
        latestScore=row["latest_score"],
        turnCount=row["turn_count"],
        createdAt=row["created_at"],
        updatedAt=row["updated_at"],
    )


def _turn(row: sqlite3.Row) -> HistoryTurn:
    return HistoryTurn(
        id=row["id"],
        sessionId=row["session_id"],
        question=row["question"],
        answer=row["answer"],
        request=AnalysisRequest.model_validate(json.loads(row["request_json"])),
        analysis=AnalysisResponse.model_validate(json.loads(row["analysis_json"])),
        usedModel=row["used_model"],
        fallback=bool(row["fallback"]),
        createdAt=row["created_at"],
    )


def _location_key(request: AnalysisRequest) -> str:
    return f"{request.location.lng:.5f},{request.location.lat:.5f}"


def _title(request: AnalysisRequest) -> str:
    module_name = MODULE_NAMES[request.module]
    address = request.location.address or _location_key(request)
    question = request.question.strip()
    summary = question[:24] + ("..." if len(question) > 24 else "")
    return f"{module_name} · {address} · {summary}"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()
