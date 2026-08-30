"""Unified read model for collaboration, jobs, evidence and DBTL state."""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

import pandas as pd

from app.data_adapter import ProjectData

from .collaboration import CollaborationStore


class ActivityService:
    def __init__(self, project: str | Path, collaboration: CollaborationStore | None = None):
        self.project = Path(project).resolve()
        self.data = ProjectData(self.project)
        self.collaboration = collaboration or CollaborationStore(self.project)

    def timeline(self, project_id: str = "atp_synthase", candidate_id: str | None = None) -> pd.DataFrame:
        records: list[dict[str, Any]] = []
        for row in self.collaboration.timeline(project_id, candidate_id):
            records.append(
                {
                    "timestamp": row["created_at"],
                    "candidate_id": row.get("candidate_id") or "",
                    "event_type": row["event_type"],
                    "summary": json.dumps(row["payload"], ensure_ascii=False, default=str)[:700],
                    "source": "CollaborationStore",
                    "record_id": f"collab_event_{row['event_id']}",
                }
            )
        database = self.project / "workspace_local/workspace.sqlite3"
        if database.is_file():
            with sqlite3.connect(database) as db:
                db.row_factory = sqlite3.Row
                for row in db.execute(
                    "SELECT job_id,candidate_id,status,created_at,started_at,completed_at,protocol_id FROM calculation_job WHERE project_id=?",
                    (project_id,),
                ):
                    if candidate_id and row["candidate_id"] != candidate_id:
                        continue
                    timestamp = row["completed_at"] or row["started_at"] or row["created_at"]
                    records.append(
                        {
                            "timestamp": timestamp,
                            "candidate_id": row["candidate_id"],
                            "event_type": "calculation_job_" + row["status"],
                            "summary": f"{row['job_id']} · {row['protocol_id']} · {row['status']}",
                            "source": "Calculation Job Registry",
                            "record_id": row["job_id"],
                        }
                    )
                for row in db.execute(
                    "SELECT evidence_id,compound_id,evidence_type,timestamp,protocol_id,source_job_id FROM evidence WHERE project_id=?",
                    (project_id,),
                ):
                    if candidate_id and row["compound_id"] != candidate_id:
                        continue
                    records.append(
                        {
                            "timestamp": row["timestamp"],
                            "candidate_id": row["compound_id"],
                            "event_type": "evidence_registered",
                            "summary": f"{row['evidence_type']} · {row['protocol_id']} · job {row['source_job_id']}",
                            "source": "Evidence Registry",
                            "record_id": row["evidence_id"],
                        }
                    )
        post = self.project / "results/phase17_1/post_analysis.json"
        if post.is_file() and not candidate_id:
            payload = json.loads(post.read_text(encoding="utf-8"))
            records.append(
                {
                    "timestamp": payload.get("created_at", ""),
                    "candidate_id": "",
                    "event_type": "phase17_1_post_analysis_completed",
                    "summary": (
                        f"three-protocol matched n={payload.get('three_protocol_matched_n', 'unknown')} · "
                        "cached results only · Registry Evidence unchanged"
                    ),
                    "source": "Versioned analysis artifact",
                    "record_id": "phase17_1_post_analysis",
                }
            )
        frame = pd.DataFrame(records)
        if frame.empty:
            return pd.DataFrame(columns=["timestamp", "candidate_id", "event_type", "summary", "source", "record_id"])
        return frame.sort_values(["timestamp", "record_id"], ascending=[False, False]).reset_index(drop=True)

    def team_board(self, project_id: str = "atp_synthase") -> pd.DataFrame:
        ranking = self.data.decision_ranking("balanced").copy()
        if ranking.empty:
            return ranking
        ranking = ranking.rename(columns={"rank": "ai_rank", "final_score": "ai_score"})
        comparison, _ = self.data.protocol_comparison()
        protocol = pd.DataFrame()
        if not comparison.empty:
            protocol = comparison[[c for c in ["canonical_id", "abs_rank_delta"] if c in comparison]].rename(
                columns={"canonical_id": "compound_id", "abs_rank_delta": "protocol_disagreement"}
            )
        evidence = self.data.evidence_matrix()
        evidence_columns = [c for c in ["glide", "vina", "mmgbsa", "admet", "literature_prior", "experiment"] if c in evidence]
        if not evidence.empty:
            evidence = evidence.copy()
            evidence["evidence_complete_count"] = evidence[evidence_columns].eq("available").sum(axis=1)
            evidence = evidence[["compound_id", "evidence_complete_count"]]
        board = ranking.merge(protocol, on="compound_id", how="left").merge(evidence, on="compound_id", how="left")
        human = self.collaboration.board(project_id)
        vote_rows = pd.DataFrame(human["votes"])
        review_rows = pd.DataFrame(human["reviews"])
        decision_rows = pd.DataFrame(human["decisions"])
        queue_rows = pd.DataFrame(human["queue"])
        if not vote_rows.empty:
            counts = vote_rows.pivot_table(index="candidate_id", columns="vote", values="vote_id", aggfunc="count", fill_value=0).reset_index()
            board = board.merge(counts, left_on="compound_id", right_on="candidate_id", how="left").drop(columns=["candidate_id_y"], errors="ignore").rename(columns={"candidate_id_x": "compound_id"})
        if not review_rows.empty:
            comments = review_rows.groupby("candidate_id").agg(comments=("review_id", "count"), proposed_action=("review_type", lambda values: "; ".join(sorted(set(values))))).reset_index()
            board = board.merge(comments, left_on="compound_id", right_on="candidate_id", how="left").drop(columns=["candidate_id_y"], errors="ignore").rename(columns={"candidate_id_x": "compound_id"})
        if not decision_rows.empty:
            latest = decision_rows.sort_values("created_at").groupby("candidate_id").tail(1)[["candidate_id", "decision", "researcher"]]
            board = board.merge(latest, left_on="compound_id", right_on="candidate_id", how="left").drop(columns=["candidate_id_y"], errors="ignore").rename(columns={"candidate_id_x": "compound_id", "decision": "final_status"})
        if not queue_rows.empty:
            latest = queue_rows.sort_values("updated_at").groupby("candidate_id").tail(1)[["candidate_id", "state", "proposed_action"]]
            board = board.merge(latest, left_on="compound_id", right_on="candidate_id", how="left").drop(columns=["candidate_id_y"], errors="ignore").rename(columns={"candidate_id_x": "compound_id", "state": "queue_state"})
        for column in ["High Priority", "Review", "Low Priority", "comments"]:
            if column not in board:
                board[column] = 0
            board[column] = board[column].fillna(0).astype(int)
        for column in ["proposed_action", "final_status", "queue_state"]:
            if column not in board:
                board[column] = ""
            board[column] = board[column].fillna("")
        board["ai_team_disagreement"] = (
            ((board["ai_rank"] <= 5) & (board["Low Priority"] > board["High Priority"]))
            | ((board["ai_rank"] > 5) & (board["High Priority"] > board["Low Priority"]))
        )
        return board.sort_values("ai_rank")

    def dbtl_snapshot(self, project_id: str = "atp_synthase") -> dict[str, Any]:
        jobs = self.data.jobs()
        jobs = jobs.loc[jobs["project_id"].astype(str).eq(project_id)] if not jobs.empty else jobs
        status = jobs.get("status", pd.Series(dtype=str)).astype(str)
        generated = self.data.generated_registry()
        board = self.collaboration.board(project_id)
        feedback = self.data.feedback_status()
        return {
            "cycle_id": "ATP-computational-cycle-1",
            "scope": "computational DBTL / iterative decision loop",
            "design": {"registered_generated_candidates": len(generated), "candidate_selection": "Phase15/Phase18B acquisition"},
            "build": {"calculation_jobs": len(jobs), "future_synthesis": len([row for row in board["queue"] if row["state"] == "Ready for Synthesis"])},
            "test": {"completed_computational_jobs": int(status.eq("completed").sum()), "reviewed_wet_lab_feedback": feedback.get("reviewed_batches", 0)},
            "learn": {"evidence_registry_records": self._evidence_count(project_id), "human_final_decisions": len(board["decisions"])},
            "wet_lab_closed_loop_claim": False,
            "next_actions": ["complete registered calculations", "review candidate evidence", "await real experimental feedback"],
        }

    def _evidence_count(self, project_id: str) -> int:
        path = self.project / "workspace_local/workspace.sqlite3"
        if not path.is_file():
            return 0
        with sqlite3.connect(path) as db:
            return int(db.execute("SELECT count(1) FROM evidence WHERE project_id=?", (project_id,)).fetchone()[0])
