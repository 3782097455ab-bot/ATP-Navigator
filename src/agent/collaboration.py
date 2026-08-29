"""Human collaboration state, deliberately separate from scientific evidence."""
from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import tempfile
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


REVIEW_TYPES = {"Recommend", "Concern", "Propose Calculation", "Propose Experiment", "Comment"}
VOTES = {"High Priority", "Review", "Low Priority"}
DECISIONS = {"Approve", "Reject", "Hold"}
QUEUE_STATES = {
    "Planned",
    "Proposed",
    "Approved",
    "Calculation",
    "Ready for Synthesis",
    "Synthesized",
    "ATP Assay",
    "MIC",
    "Toxicity",
    "Completed",
}


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def token(prefix: str) -> str:
    return prefix + "_" + uuid.uuid4().hex[:18]


def encoded(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, allow_nan=False)


def payload_hash(value: Any) -> str:
    return hashlib.sha256(encoded(value).encode()).hexdigest()


def _text(value: Any, name: str, maximum: int = 4000) -> str:
    value = str(value or "").strip()
    if not value or len(value) > maximum:
        raise ValueError(f"Invalid {name}")
    return value


class CollaborationStore:
    """Local SQLite human layer; never mutates Evidence Registry values."""

    def __init__(self, project_root: str | Path, database: str | Path | None = None, ephemeral: bool = False):
        self.project_root = Path(project_root).resolve()
        self.ephemeral = bool(ephemeral)
        if database is not None:
            self.path = Path(database).resolve()
        elif self.ephemeral:
            identity = hashlib.sha256(str(self.project_root).encode()).hexdigest()[:12]
            self.path = Path(tempfile.gettempdir(), f"atpnav_collaboration_{os.getpid()}_{identity}.sqlite3").resolve()
        else:
            self.path = (self.project_root / "workspace_local/collaboration.sqlite3").resolve()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as db:
            db.executescript(
                """
                CREATE TABLE IF NOT EXISTS project_metadata(
                    project_id TEXT PRIMARY KEY, organism TEXT, target TEXT, receptor TEXT,
                    binding_site TEXT, candidate_library TEXT, protocols TEXT,
                    evidence_schema TEXT, decision_profile TEXT, scientific_status TEXT,
                    created_at TEXT, updated_at TEXT);
                CREATE TABLE IF NOT EXISTS research_session_v2(
                    session_id TEXT PRIMARY KEY, project_id TEXT NOT NULL, reviewer TEXT NOT NULL,
                    context TEXT NOT NULL, created_at TEXT NOT NULL, updated_at TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS execution_plan_v2(
                    plan_id TEXT PRIMARY KEY, session_id TEXT NOT NULL, project_id TEXT NOT NULL,
                    action_id TEXT NOT NULL, intent TEXT NOT NULL, preview TEXT NOT NULL,
                    status TEXT NOT NULL, result TEXT, created_at TEXT NOT NULL,
                    confirmed_at TEXT, completed_at TEXT);
                CREATE TABLE IF NOT EXISTS collaboration_event(
                    event_id INTEGER PRIMARY KEY AUTOINCREMENT, project_id TEXT NOT NULL,
                    session_id TEXT, candidate_id TEXT, event_type TEXT NOT NULL,
                    payload TEXT NOT NULL, created_at TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS candidate_review(
                    review_id TEXT PRIMARY KEY, project_id TEXT NOT NULL, candidate_id TEXT NOT NULL,
                    reviewer TEXT NOT NULL, review_type TEXT NOT NULL, comment TEXT NOT NULL,
                    related_decision_run TEXT, created_at TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS candidate_vote(
                    vote_id TEXT PRIMARY KEY, project_id TEXT NOT NULL, candidate_id TEXT NOT NULL,
                    reviewer TEXT NOT NULL, vote TEXT NOT NULL, created_at TEXT NOT NULL,
                    UNIQUE(project_id,candidate_id,reviewer));
                CREATE TABLE IF NOT EXISTS final_human_decision(
                    decision_id TEXT PRIMARY KEY, project_id TEXT NOT NULL, candidate_id TEXT NOT NULL,
                    decision TEXT NOT NULL, researcher TEXT NOT NULL, rationale TEXT NOT NULL,
                    ai_recommendation TEXT NOT NULL, evidence_snapshot_hash TEXT NOT NULL,
                    created_at TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS make_test_queue(
                    queue_id TEXT PRIMARY KEY, project_id TEXT NOT NULL, candidate_id TEXT NOT NULL,
                    state TEXT NOT NULL, proposed_action TEXT NOT NULL, researcher TEXT NOT NULL,
                    source_plan_id TEXT, created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
                    experimental_result_status TEXT NOT NULL);
                CREATE INDEX IF NOT EXISTS collab_event_project ON collaboration_event(project_id,created_at);
                CREATE INDEX IF NOT EXISTS collab_event_candidate ON collaboration_event(project_id,candidate_id,created_at);
                """
            )
        self.ensure_default_project()

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.path, timeout=30)
        db.row_factory = sqlite3.Row
        try:
            with db:
                yield db
        finally:
            db.close()

    def ensure_default_project(self) -> None:
        self.create_project(
            project_id="atp_synthase",
            organism="Acinetobacter baumannii",
            target="F1F0 ATP synthase",
            receptor="7P3W subunits e/g",
            binding_site="frozen vina_7p3w_v1 box",
            candidate_library="HTVS 1633 + internal candidates + generated candidates",
            protocols=["historical Glide", "vina_7p3w_v1", "open_mmgbsa_7p3w_v2"],
            evidence_schema="ATP-Navigator shared Evidence Registry",
            decision_profile="balanced",
            scientific_status="scientifically-supported-current-project",
        )

    def create_project(self, **record: Any) -> str:
        project_id = _text(record.get("project_id"), "project_id", 100)
        if not all(char.isalnum() or char in "_-" for char in project_id):
            raise ValueError("Invalid project_id")
        timestamp = now()
        values = (
            project_id,
            str(record.get("organism", "unknown")),
            str(record.get("target", "unknown")),
            str(record.get("receptor", "unknown")),
            str(record.get("binding_site", "unknown")),
            str(record.get("candidate_library", "unknown")),
            encoded(record.get("protocols", [])),
            str(record.get("evidence_schema", "metadata_only")),
            str(record.get("decision_profile", "unvalidated")),
            str(record.get("scientific_status", "engineering-supported_scientifically-unvalidated")),
            timestamp,
            timestamp,
        )
        with self.connect() as db:
            existing = db.execute("SELECT project_id FROM project_metadata WHERE project_id=?", (project_id,)).fetchone()
            if not existing:
                db.execute("INSERT INTO project_metadata VALUES (?,?,?,?,?,?,?,?,?,?,?,?)", values)
        return project_id

    def projects(self) -> list[dict[str, Any]]:
        with self.connect() as db:
            rows = [dict(row) for row in db.execute("SELECT * FROM project_metadata ORDER BY created_at")]
        for row in rows:
            row["protocols"] = json.loads(row["protocols"])
        return rows

    def create_session(self, project_id: str = "atp_synthase", reviewer: str = "researcher") -> str:
        reviewer = _text(reviewer, "reviewer", 120)
        with self.connect() as db:
            if not db.execute("SELECT 1 FROM project_metadata WHERE project_id=?", (project_id,)).fetchone():
                raise ValueError("Unknown project")
            session_id = token("research")
            context = {
                "current_project": project_id,
                "selected_candidate_set": [],
                "current_profile": "balanced",
                "current_budget": None,
                "last_intent": None,
                "last_result_summary": None,
            }
            timestamp = now()
            db.execute(
                "INSERT INTO research_session_v2 VALUES (?,?,?,?,?,?)",
                (session_id, project_id, reviewer, encoded(context), timestamp, timestamp),
            )
            self._event(db, project_id, session_id, None, "research_session_created", context)
        return session_id

    def session(self, session_id: str) -> dict[str, Any]:
        with self.connect() as db:
            row = db.execute("SELECT * FROM research_session_v2 WHERE session_id=?", (session_id,)).fetchone()
        if not row:
            raise ValueError("Unknown research session")
        result = dict(row)
        result["context"] = json.loads(result["context"])
        return result

    def update_context(self, session_id: str, **changes: Any) -> dict[str, Any]:
        session = self.session(session_id)
        context = session["context"]
        allowed = {
            "selected_candidate_set",
            "current_project",
            "current_profile",
            "current_budget",
            "last_intent",
            "last_result_summary",
        }
        if set(changes) - allowed:
            raise ValueError("Unsupported context field")
        context.update(changes)
        with self.connect() as db:
            db.execute(
                "UPDATE research_session_v2 SET context=?,updated_at=? WHERE session_id=?",
                (encoded(context), now(), session_id),
            )
        return context

    def _event(self, db, project_id: str, session_id: str | None, candidate_id: str | None,
               event_type: str, payload: Any) -> None:
        db.execute(
            "INSERT INTO collaboration_event(project_id,session_id,candidate_id,event_type,payload,created_at) VALUES (?,?,?,?,?,?)",
            (project_id, session_id, candidate_id, event_type, encoded(payload), now()),
        )

    def event(self, project_id: str, event_type: str, payload: Any,
              session_id: str | None = None, candidate_id: str | None = None) -> None:
        with self.connect() as db:
            self._event(db, project_id, session_id, candidate_id, event_type, payload)

    def save_plan(self, plan: dict[str, Any]) -> None:
        with self.connect() as db:
            db.execute(
                "INSERT INTO execution_plan_v2 VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                (
                    plan["plan_id"],
                    plan["session_id"],
                    plan["project_id"],
                    plan["action_id"],
                    encoded(plan["intent"]),
                    encoded(plan),
                    "pending_confirmation",
                    None,
                    now(),
                    None,
                    None,
                ),
            )
            self._event(db, plan["project_id"], plan["session_id"], None, "execution_plan_created", plan)

    def plan(self, plan_id: str) -> dict[str, Any]:
        with self.connect() as db:
            row = db.execute("SELECT * FROM execution_plan_v2 WHERE plan_id=?", (plan_id,)).fetchone()
        if not row:
            raise ValueError("Unknown execution plan")
        value = dict(row)
        value["intent"] = json.loads(value["intent"])
        value["preview"] = json.loads(value["preview"])
        value["result"] = json.loads(value["result"]) if value["result"] else None
        return value

    def mark_plan(self, plan_id: str, status: str, result: Any = None) -> None:
        if status not in {"confirmed", "completed", "blocked", "failed", "cancelled"}:
            raise ValueError("Invalid plan status")
        plan = self.plan(plan_id)
        timestamp = now()
        confirmed = timestamp if status == "confirmed" else plan.get("confirmed_at")
        completed = timestamp if status in {"completed", "blocked", "failed", "cancelled"} else None
        with self.connect() as db:
            db.execute(
                "UPDATE execution_plan_v2 SET status=?,result=?,confirmed_at=COALESCE(confirmed_at,?),completed_at=? WHERE plan_id=?",
                (status, encoded(result) if result is not None else None, confirmed, completed, plan_id),
            )
            self._event(
                db,
                plan["project_id"],
                plan["session_id"],
                None,
                "execution_plan_" + status,
                {"plan_id": plan_id, "result": result},
            )

    def add_review(self, project_id: str, candidate_id: str, reviewer: str, review_type: str,
                   comment: str, related_decision_run: str = "") -> str:
        if review_type not in REVIEW_TYPES:
            raise ValueError("Unknown review type")
        review_id = token("review")
        with self.connect() as db:
            db.execute(
                "INSERT INTO candidate_review VALUES (?,?,?,?,?,?,?,?)",
                (review_id, project_id, _text(candidate_id, "candidate_id"), _text(reviewer, "reviewer", 120),
                 review_type, _text(comment, "comment"), related_decision_run, now()),
            )
            self._event(db, project_id, None, candidate_id, "human_review", {"review_id": review_id, "review_type": review_type, "reviewer": reviewer})
        return review_id

    def vote(self, project_id: str, candidate_id: str, reviewer: str, vote: str) -> str:
        if vote not in VOTES:
            raise ValueError("Unknown vote")
        vote_id = token("vote")
        timestamp = now()
        with self.connect() as db:
            old = db.execute(
                "SELECT vote_id FROM candidate_vote WHERE project_id=? AND candidate_id=? AND reviewer=?",
                (project_id, candidate_id, reviewer),
            ).fetchone()
            if old:
                vote_id = old[0]
                db.execute("UPDATE candidate_vote SET vote=?,created_at=? WHERE vote_id=?", (vote, timestamp, vote_id))
            else:
                db.execute(
                    "INSERT INTO candidate_vote VALUES (?,?,?,?,?,?)",
                    (vote_id, project_id, candidate_id, _text(reviewer, "reviewer", 120), vote, timestamp),
                )
            self._event(db, project_id, None, candidate_id, "human_vote", {"vote_id": vote_id, "vote": vote, "reviewer": reviewer})
        return vote_id

    def final_decision(self, project_id: str, candidate_id: str, decision: str, researcher: str,
                       rationale: str, ai_recommendation: Any, evidence_snapshot_hash: str) -> str:
        if decision not in DECISIONS:
            raise ValueError("Unknown final decision")
        decision_id = token("human_decision")
        with self.connect() as db:
            db.execute(
                "INSERT INTO final_human_decision VALUES (?,?,?,?,?,?,?,?,?)",
                (decision_id, project_id, candidate_id, decision, _text(researcher, "researcher", 120),
                 _text(rationale, "rationale"), encoded(ai_recommendation), evidence_snapshot_hash, now()),
            )
            self._event(db, project_id, None, candidate_id, "final_human_decision", {"decision_id": decision_id, "decision": decision, "researcher": researcher, "evidence_snapshot_hash": evidence_snapshot_hash})
        return decision_id

    def queue(self, project_id: str, candidate_id: str, state: str, proposed_action: str,
              researcher: str, source_plan_id: str = "") -> str:
        if state not in QUEUE_STATES:
            raise ValueError("Unknown queue state")
        # No reviewed wet-lab result exists in the current project.  The queue is
        # therefore a proposal/planning surface only; later states require a
        # separately reviewed evidence transition rather than a UI assertion.
        if state not in {"Planned", "Proposed"}:
            raise ValueError("Current evidence permits only planned/proposed queue states")
        queue_id = token("queue")
        timestamp = now()
        with self.connect() as db:
            db.execute(
                "INSERT INTO make_test_queue VALUES (?,?,?,?,?,?,?,?,?,?)",
                (queue_id, project_id, candidate_id, state, _text(proposed_action, "proposed_action"),
                 _text(researcher, "researcher", 120), source_plan_id, timestamp, timestamp, "unknown"),
            )
            self._event(db, project_id, None, candidate_id, "make_test_queue", {"queue_id": queue_id, "state": state, "proposed_action": proposed_action})
        return queue_id

    def board(self, project_id: str) -> dict[str, list[dict[str, Any]]]:
        with self.connect() as db:
            reviews = [dict(row) for row in db.execute("SELECT * FROM candidate_review WHERE project_id=? ORDER BY created_at DESC", (project_id,))]
            votes = [dict(row) for row in db.execute("SELECT * FROM candidate_vote WHERE project_id=? ORDER BY created_at DESC", (project_id,))]
            decisions = [dict(row) for row in db.execute("SELECT * FROM final_human_decision WHERE project_id=? ORDER BY created_at DESC", (project_id,))]
            queue = [dict(row) for row in db.execute("SELECT * FROM make_test_queue WHERE project_id=? ORDER BY updated_at DESC", (project_id,))]
        for row in decisions:
            row["ai_recommendation"] = json.loads(row["ai_recommendation"])
        return {"reviews": reviews, "votes": votes, "decisions": decisions, "queue": queue}

    def timeline(self, project_id: str, candidate_id: str | None = None) -> list[dict[str, Any]]:
        query = "SELECT * FROM collaboration_event WHERE project_id=?"
        values: list[Any] = [project_id]
        if candidate_id:
            query += " AND candidate_id=?"
            values.append(candidate_id)
        query += " ORDER BY created_at DESC,event_id DESC"
        with self.connect() as db:
            rows = [dict(row) for row in db.execute(query, values)]
        for row in rows:
            row["payload"] = json.loads(row["payload"])
            row["source"] = "CollaborationStore"
        return rows

    def plans(self, session_id: str) -> list[dict[str, Any]]:
        with self.connect() as db:
            rows = [dict(row) for row in db.execute("SELECT * FROM execution_plan_v2 WHERE session_id=? ORDER BY created_at DESC", (session_id,))]
        return rows
