"""Streamlit views for Phase 18B product-layer integration."""
from __future__ import annotations

import json
import os
from pathlib import Path

import pandas as pd
import streamlit as st
import streamlit.components.v1 as components

from agent.activity import ActivityService
from agent.collaboration import CollaborationStore, DECISIONS, QUEUE_STATES, REVIEW_TYPES, VOTES
from agent.orchestrator import ConversationalOrchestrator
from agent.structure_viewer import PoseRegistry


def _deployment() -> dict:
    mode = os.environ.get("ATP_NAVIGATOR_DEPLOYMENT_MODE", "local_full")
    persistent = mode == "local_full" or os.environ.get("ATP_NAVIGATOR_COLLAB_PERSISTENT") == "1"
    return {
        "mode": mode,
        "can_execute_local_tools": mode == "local_full",
        "collaboration_persistence": "persistent_local_sqlite" if persistent else "ephemeral collaboration storage",
    }


@st.cache_resource
def collaboration(project_text: str) -> CollaborationStore:
    return CollaborationStore(Path(project_text), ephemeral=_deployment()["collaboration_persistence"].startswith("ephemeral"))


@st.cache_resource
def orchestrator(project_text: str) -> ConversationalOrchestrator:
    project = Path(project_text)
    return ConversationalOrchestrator(project, collaboration=collaboration(project_text))


@st.cache_resource
def pose_registry(project_text: str) -> PoseRegistry:
    return PoseRegistry(Path(project_text))


def _session(project: Path) -> str:
    key = "phase18b_research_session"
    if key not in st.session_state:
        st.session_state[key] = orchestrator(str(project)).new_session(
            reviewer=st.session_state.get("phase18b_reviewer", "researcher")
        )
    return st.session_state[key]


def _show_result(result: dict):
    st.markdown(result.get("answer", result.get("reason", result.get("status", "Result"))))
    if result.get("records"):
        st.dataframe(pd.DataFrame(result["records"]), width="stretch", hide_index=True)
    if result.get("warning"):
        st.warning(result["warning"])
    if result.get("provenance"):
        with st.expander("Provenance"):
            st.json(result["provenance"])


def research_console(project: Path, title_fn):
    title_fn("AI Research Console", "自然语言 → 结构化意图 → Plan Preview → 人工确认 → 白名单动作 → Registry结果回到对话")
    deploy = _deployment()
    store = collaboration(str(project))
    engine = orchestrator(str(project))
    session_id = _session(project)
    session = store.session(session_id)

    left, right = st.columns([1.55, 1])
    with right:
        st.markdown("### Current Project")
        st.json({"project_id": session["project_id"], **deploy}, expanded=False)
        context = session["context"]
        st.markdown("### Selected Candidates")
        st.dataframe(pd.DataFrame({"candidate_id": context.get("selected_candidate_set", [])}), width="stretch", hide_index=True)
        st.markdown("### Active Jobs")
        jobs = engine.actions.data.jobs()
        active = jobs.loc[jobs["status"].astype(str).isin(["planned", "ready", "running", "blocked"])] if not jobs.empty else jobs
        st.dataframe(active[[c for c in ["job_id", "candidate_id", "protocol_id", "status"] if c in active]].head(12), width="stretch", hide_index=True)
        linked = engine.linked_jobs(session_id)
        if linked:
            st.markdown("### Plan-linked Jobs")
            st.dataframe(pd.DataFrame(linked)[[c for c in ["job_id", "candidate_id", "tool_id", "protocol_id", "status", "completed_at"] if c in linked[0]]], width="stretch", hide_index=True)
        with st.expander("New metadata-only project"):
            new_id = st.text_input("project_id", key="new_project_id")
            organism = st.text_input("organism", key="new_project_organism")
            target = st.text_input("target", key="new_project_target")
            if st.button("Create metadata-only project", disabled=not new_id or not target):
                store.create_project(project_id=new_id, organism=organism or "unknown", target=target,
                                     receptor="unknown", binding_site="unknown", candidate_library="unknown",
                                     protocols=[], evidence_schema="metadata_only", decision_profile="unvalidated",
                                     scientific_status="engineering-supported_scientifically-unvalidated")
                st.success("Project metadata created. No target-specific scientific model was claimed.")

    with left:
        st.caption("示例：" + " ｜ ".join(engine.presentation_script()[:2]))
        messages = st.session_state.setdefault("phase18b_messages", [])
        for item in messages:
            with st.chat_message(item["role"]):
                if item["role"] == "assistant":
                    _show_result(item["payload"])
                else:
                    st.markdown(item["text"])
        pending = st.session_state.get("phase18b_pending_plan")
        if pending:
            st.markdown("### Plan Preview")
            preview = pending["plan"]
            st.json(
                {
                    "What will happen": preview["what_will_happen"],
                    "Candidate count": preview["candidate_count"],
                    "Tool/backend": preview["tool_backend"],
                    "Protocol": preview["protocol"],
                    "Estimated runtime": preview["estimated_runtime"],
                    "Estimated resource": preview["estimated_resource_level"],
                    "Evidence generated": preview["evidence_generated"],
                    "Files/Registry changes": preview["files_or_records_changed"],
                    "Scientific caveats": preview["scientific_caveats"],
                },
                expanded=True,
            )
            c1, c2 = st.columns(2)
            if not deploy["can_execute_local_tools"]:
                st.info("cloud_viewer is read-only for execution plans; local tools and workers cannot run here.")
            if c1.button("Confirm & Execute", type="primary", disabled=not deploy["can_execute_local_tools"]):
                result = engine.confirm(session_id, preview["plan_id"])
                messages.append({"role": "assistant", "payload": result})
                st.session_state.pop("phase18b_pending_plan", None)
                st.rerun()
            if c2.button("Cancel plan"):
                store.mark_plan(preview["plan_id"], "cancelled", {"reason": "researcher_cancelled"})
                st.session_state.pop("phase18b_pending_plan", None)
                st.rerun()
        question = st.chat_input("询问候选、证据、协议分歧，或创建需要确认的获取/生成/计算计划")
        if question:
            messages.append({"role": "user", "text": question})
            result = engine.handle(session_id, question)
            messages.append({"role": "assistant", "payload": result})
            if result.get("status") == "confirmation_required":
                st.session_state["phase18b_pending_plan"] = result
            st.rerun()


def embedded_pose(project: Path, candidate_id: str, height: int = 560):
    html, record = pose_registry(str(project)).html(candidate_id, height=height)
    if html is None:
        st.info(record.get("message", "No registered pose available."))
        st.json(record, expanded=False)
        return
    components.html(html, height=height + 15, scrolling=False)
    st.caption(
        f"{record['candidate_id']} · {record['protocol']} · affinity={record['affinity']} · "
        f"pose QC={record['pose_qc']} · receptor={record['receptor']}"
    )
    with st.expander("Pose provenance"):
        st.json(record)


def structural_workspace(project: Path, title_fn, data):
    title_fn("3D Structural Workspace", "浏览器内查看7P3W、登记的Vina rank-1 pose和5 Å邻近区域；协议pose不混用")
    master = data.candidate_master()
    default = master.loc[master["candidate_source"].eq("HTVS 1633")].sort_values("global_rank").head(30)
    candidate = st.selectbox("Candidate", default["compound_id"].tolist(), key="structural_candidate")
    embedded_pose(project, candidate, height=620)
    st.warning("当前显示的是 Vina pose。它不是 open-MMGBSA trajectory pose，也不代表实验结合构象。")


def team_review_board(project: Path, title_fn, data):
    title_fn("Team Review Board", "AI建议、团队投票和研究者最终决定三层分开保存；人类投票不修改AI分数")
    store = collaboration(str(project))
    service = ActivityService(project, store)
    board = service.team_board()
    filters = st.multiselect(
        "Filter",
        ["AI/team disagreement", "High-priority consensus", "Unresolved discussion", "Proposed experiment"],
    )
    filtered = board.copy()
    if "AI/team disagreement" in filters:
        filtered = filtered.loc[filtered["ai_team_disagreement"]]
    if "High-priority consensus" in filters:
        filtered = filtered.loc[filtered["High Priority"] >= 2]
    if "Unresolved discussion" in filters:
        filtered = filtered.loc[(filtered["comments"] > 0) & filtered["final_status"].eq("")]
    if "Proposed experiment" in filters:
        filtered = filtered.loc[filtered["proposed_action"].str.contains("Experiment", case=False, na=False)]
    st.dataframe(filtered, width="stretch", hide_index=True, height=430)
    candidates = board["compound_id"].astype(str).tolist()
    if not candidates:
        st.info("No decision candidates are registered.")
        return
    candidate = st.selectbox("Review candidate", candidates)
    reviewer = st.text_input("Reviewer", value=st.session_state.get("phase18b_reviewer", "researcher"))
    st.session_state["phase18b_reviewer"] = reviewer
    c1, c2 = st.columns(2)
    with c1:
        review_type = st.selectbox("Review type", sorted(REVIEW_TYPES))
        comment = st.text_area("Comment / rationale", key="review_comment")
        if st.button("Save review", disabled=not reviewer or not comment):
            store.add_review("atp_synthase", candidate, reviewer, review_type, comment)
            st.success("Review saved in CollaborationStore; scientific evidence unchanged.")
        vote = st.radio("Team vote", ["High Priority", "Review", "Low Priority"], horizontal=True)
        if st.button("Save vote", disabled=not reviewer):
            store.vote("atp_synthase", candidate, reviewer, vote)
            st.success("Vote saved. AI score was not modified.")
    with c2:
        decision = st.selectbox("Final human decision", ["Approve", "Reject", "Hold"])
        rationale = st.text_area("Decision rationale", key="decision_rationale")
        if st.button("Record final decision", disabled=not reviewer or not rationale):
            ranking = data.decision_ranking("balanced")
            ai = ranking.loc[ranking["compound_id"].astype(str).eq(candidate)].to_dict("records")
            snapshot = orchestrator(str(project)).evidence_snapshot_hash(candidate)
            store.final_decision("atp_synthase", candidate, decision, reviewer, rationale, ai, snapshot)
            st.success("Final human decision stored with evidence snapshot hash.")
        queue_state = st.selectbox("Make/Test queue state", ["Planned", "Proposed"])
        proposed_action = st.text_input("Proposed action", value="Review for future experimental validation")
        if st.button("Add to Make/Test queue", disabled=not reviewer):
            store.queue("atp_synthase", candidate, queue_state, proposed_action, reviewer)
            st.success("Planning state saved. No calculation, synthesis or experimental result was generated.")


def activity_timeline(project: Path, title_fn):
    title_fn("Unified Activity Timeline", "AI查询、计划、任务、证据、团队审查与最终决定来自各自真实Registry")
    service = ActivityService(project, collaboration(str(project)))
    candidate = st.text_input("Optional candidate filter", key="timeline_candidate")
    frame = service.timeline(candidate_id=candidate or None)
    st.dataframe(frame, width="stretch", hide_index=True, height=650)
    st.caption("没有事件就不生成事件；没有实验反馈就不会出现实验完成记录。")


def dbtl_loop(project: Path, title_fn):
    title_fn("Iterative Research Loop", "当前为 computational DBTL / iterative decision loop，不宣称完整湿实验闭环")
    snapshot = ActivityService(project, collaboration(str(project))).dbtl_snapshot()
    st.metric("Cycle ID", snapshot["cycle_id"])
    cols = st.columns(4)
    for column, stage in zip(cols, ["design", "build", "test", "learn"]):
        with column:
            st.markdown(f"### {stage.upper()}")
            st.json(snapshot[stage])
    st.code("DESIGN → BUILD → TEST → LEARN ↺", language=None)
    st.warning("wet_lab_closed_loop_claim = false；真实实验结果仍需通过Feedback QC与人工审查进入。")


def presentation_mode(project: Path, title_fn, data):
    title_fn("Presentation Mode", "评委演示：真实已登记数据、缓存任务、结构pose和研究者在环决策")
    st.markdown("### Recommended demo script")
    for index, line in enumerate(orchestrator(str(project)).presentation_script(), 1):
        st.markdown(f"{index}. `{line}`")
    comparison, metrics = data.protocol_comparison()
    top = comparison.sort_values("abs_rank_delta", ascending=False).head(10)
    c1, c2, c3 = st.columns(3)
    c1.metric("Real HTVS candidates", len(data.historical_candidates()))
    c2.metric("Registered Vina evidence", data.dashboard_metrics()["historical_vina_evidence"])
    c3.metric("Glide/Vina matched", metrics.get("matched_candidates", metrics.get("matched_subset", len(comparison))))
    st.dataframe(top, width="stretch", hide_index=True)
    if not top.empty:
        candidate = str(top.iloc[0]["canonical_id"])
        st.markdown(f"### Open candidate in 3D · `{candidate}`")
        embedded_pose(project, candidate, height=520)
    st.info("现场长任务只允许展示 previously completed registered job，并明确标记 cached real result；不会模拟执行。")
