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


def deployment_info(project: Path | None = None) -> dict:
    """Resolve a fail-closed execution mode for local and hosted viewers."""
    explicit = os.environ.get("ATP_NAVIGATOR_DEPLOYMENT_MODE", "").strip()
    project = Path(project).resolve() if project else None
    streamlit_cloud = bool(
        os.environ.get("STREAMLIT_SHARING_MODE")
        or os.environ.get("STREAMLIT_CLOUD")
        or (project and str(project).replace("\\", "/").startswith("/mount/src/"))
    )
    local_registry = bool(project and (project / "workspace_local/workspace.sqlite3").is_file())
    mode = explicit or ("cloud_viewer" if streamlit_cloud or (project and not local_registry) else "local_full")
    persistent = mode == "local_full" or os.environ.get("ATP_NAVIGATOR_COLLAB_PERSISTENT") == "1"
    return {
        "mode": mode,
        "can_execute_local_tools": mode == "local_full",
        "collaboration_persistence": "persistent_local_sqlite" if persistent else "ephemeral collaboration storage",
    }


@st.cache_resource
def collaboration(project_text: str) -> CollaborationStore:
    project = Path(project_text)
    return CollaborationStore(project, ephemeral=deployment_info(project)["collaboration_persistence"].startswith("ephemeral"))


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
    st.markdown(result.get("answer", result.get("reason", result.get("status", "处理结果"))))
    if result.get("records"):
        st.dataframe(pd.DataFrame(result["records"]), width="stretch", hide_index=True)
    if result.get("warning"):
        st.warning(result["warning"])
    if result.get("provenance"):
        with st.expander("证据溯源"):
            st.json(result["provenance"])


def research_console(project: Path, title_fn):
    title_fn("智能研究助手", "自然语言提问 → 结构化研究意图 → 计划预览 → 人工确认 → 登记结果回到对话")
    deploy = deployment_info(project)
    store = collaboration(str(project))
    engine = orchestrator(str(project))
    session_id = _session(project)
    session = store.session(session_id)

    left, right = st.columns([1.55, 1])
    with right:
        st.markdown("### 当前研究项目")
        st.json(
            {
                "项目编号": session["project_id"],
                "运行模式": "本地完整模式" if deploy["mode"] == "local_full" else "云端只读模式",
                "本地工具执行": "可用" if deploy["can_execute_local_tools"] else "不可用",
                "协作记录": "本地持久化" if deploy["collaboration_persistence"].startswith("persistent") else "临时会话",
            },
            expanded=False,
        )
        context = session["context"]
        st.markdown("### 已选候选")
        st.dataframe(pd.DataFrame({"候选编号": context.get("selected_candidate_set", [])}), width="stretch", hide_index=True)
        st.markdown("### 活动任务")
        jobs = engine.actions.data.jobs()
        active = jobs.loc[jobs["status"].astype(str).isin(["planned", "ready", "running", "blocked"])] if not jobs.empty else jobs
        st.dataframe(active[[c for c in ["job_id", "candidate_id", "protocol_id", "status"] if c in active]].head(12), width="stretch", hide_index=True)
        linked = engine.linked_jobs(session_id)
        if linked:
            st.markdown("### 当前计划关联任务")
            st.dataframe(pd.DataFrame(linked)[[c for c in ["job_id", "candidate_id", "tool_id", "protocol_id", "status", "completed_at"] if c in linked[0]]], width="stretch", hide_index=True)
        with st.expander("新建仅含元数据的项目"):
            new_id = st.text_input("项目编号", key="new_project_id")
            organism = st.text_input("研究物种", key="new_project_organism")
            target = st.text_input("研究靶点", key="new_project_target")
            if st.button("创建项目元数据", disabled=not new_id or not target):
                store.create_project(project_id=new_id, organism=organism or "unknown", target=target,
                                     receptor="unknown", binding_site="unknown", candidate_library="unknown",
                                     protocols=[], evidence_schema="metadata_only", decision_profile="unvalidated",
                                     scientific_status="engineering-supported_scientifically-unvalidated")
                st.success("项目元数据已创建；系统没有据此声称存在靶点专项模型。")

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
            st.markdown("### 研究计划预览")
            preview = pending["plan"]
            st.json(
                {
                    "将要执行": preview["what_will_happen"],
                    "候选数量": preview["candidate_count"],
                    "工具或后端": preview["tool_backend"],
                    "计算协议": preview["protocol"],
                    "预计耗时": preview["estimated_runtime"],
                    "预计资源": preview["estimated_resource_level"],
                    "新增证据": preview["evidence_generated"],
                    "文件或登记变化": preview["files_or_records_changed"],
                    "科学注意事项": preview["scientific_caveats"],
                },
                expanded=True,
            )
            c1, c2 = st.columns(2)
            if not deploy["can_execute_local_tools"]:
                st.info("云端只读模式无法调用本地计算后端。计划仍可检查，但不会启动工具或后台任务。")
            if c1.button("确认并执行", type="primary", disabled=not deploy["can_execute_local_tools"]):
                result = engine.confirm(session_id, preview["plan_id"])
                messages.append({"role": "assistant", "payload": result})
                st.session_state.pop("phase18b_pending_plan", None)
                st.rerun()
            if c2.button("取消计划"):
                store.mark_plan(preview["plan_id"], "cancelled", {"reason": "researcher_cancelled"})
                st.session_state.pop("phase18b_pending_plan", None)
                st.rerun()
        # Streamlit's voice-enabled chat_input currently emits a browser
        # wavesurfer error after rapid multipage reruns on Community Cloud.
        # A regular form keeps the same typed conversation contract without
        # requesting microphone state or changing any scientific behavior.
        with st.form("phase18b_console_input", clear_on_submit=True):
            question = st.text_input(
                "询问候选、证据、协议分歧，或创建需要确认的获取/生成/计算计划"
            )
            submitted = st.form_submit_button("发送")
        if submitted and question.strip():
            question = question.strip()
            messages.append({"role": "user", "text": question})
            result = engine.handle(session_id, question)
            messages.append({"role": "assistant", "payload": result})
            if result.get("status") == "confirmation_required":
                st.session_state["phase18b_pending_plan"] = result
            st.rerun()


def embedded_pose(project: Path, candidate_id: str, height: int = 560):
    html, record = pose_registry(str(project)).html(candidate_id, height=height)
    if html is None:
        message = record.get("message", "当前候选没有已登记的三维构象。")
        if message == "No registered pose available.":
            message = "当前候选没有已登记的三维构象。"
        st.info(message)
        st.json(record, expanded=False)
        return
    components.html(html, height=height + 15, scrolling=False)
    st.caption(
        f"{record['candidate_id']} · {record['protocol']} · affinity={record['affinity']} · "
        f"pose QC={record['pose_qc']} · receptor={record['receptor']}"
    )
    with st.expander("构象证据溯源"):
        st.json(record)


def structural_workspace(project: Path, title_fn, data):
    title_fn("三维结构工作区", "交互查看7P3W、已登记的Vina第一构象和5 Å邻近残基；不同协议构象不会混用")
    master = data.candidate_master()
    default = master.loc[master["candidate_source"].eq("HTVS 1633")].sort_values("global_rank").head(30)
    candidate = st.selectbox("选择候选", default["compound_id"].tolist(), key="structural_candidate")
    embedded_pose(project, candidate, height=620)
    st.warning("当前显示的是 Vina pose。它不是 open-MMGBSA trajectory pose，也不代表实验结合构象。")


def team_review_board(project: Path, title_fn, data):
    title_fn("团队复核工作台", "AI建议、团队意见和研究者最终决定分层保存；人工意见不会改写AI原始分数")
    store = collaboration(str(project))
    service = ActivityService(project, store)
    board = service.team_board()
    filters = st.multiselect(
        "筛选条件",
        ["AI与团队意见不一致", "高优先级共识", "尚未解决的讨论", "已提出实验建议"],
    )
    filtered = board.copy()
    if "AI与团队意见不一致" in filters:
        filtered = filtered.loc[filtered["ai_team_disagreement"]]
    if "高优先级共识" in filters:
        filtered = filtered.loc[filtered["High Priority"] >= 2]
    if "尚未解决的讨论" in filters:
        filtered = filtered.loc[(filtered["comments"] > 0) & filtered["final_status"].eq("")]
    if "已提出实验建议" in filters:
        filtered = filtered.loc[filtered["proposed_action"].str.contains("Experiment", case=False, na=False)]
    st.dataframe(filtered, width="stretch", hide_index=True, height=430)
    candidates = board["compound_id"].astype(str).tolist()
    if not candidates:
        st.info("当前没有已登记的决策候选。")
        return
    candidate = st.selectbox("复核候选", candidates)
    reviewer = st.text_input("复核人", value=st.session_state.get("phase18b_reviewer", "研究者"))
    st.session_state["phase18b_reviewer"] = reviewer
    c1, c2 = st.columns(2)
    with c1:
        review_type = st.selectbox("复核类型", sorted(REVIEW_TYPES))
        comment = st.text_area("意见与依据", key="review_comment")
        if st.button("保存复核意见", disabled=not reviewer or not comment):
            store.add_review("atp_synthase", candidate, reviewer, review_type, comment)
            st.success("复核意见已保存；原始科学证据没有变化。")
        vote_labels = {"高优先级": "High Priority", "继续复核": "Review", "低优先级": "Low Priority"}
        vote_zh = st.radio("团队意见", list(vote_labels), horizontal=True)
        if st.button("保存团队意见", disabled=not reviewer):
            vote = vote_labels[vote_zh]
            store.vote("atp_synthase", candidate, reviewer, vote)
            st.success("团队意见已保存；AI原始分数没有变化。")
    with c2:
        decision_labels = {"通过": "Approve", "不通过": "Reject", "暂缓": "Hold"}
        decision_zh = st.selectbox("研究者最终决定", list(decision_labels))
        decision = decision_labels[decision_zh]
        rationale = st.text_area("决定依据", key="decision_rationale")
        if st.button("记录最终决定", disabled=not reviewer or not rationale):
            ranking = data.decision_ranking("balanced")
            ai = ranking.loc[ranking["compound_id"].astype(str).eq(candidate)].to_dict("records")
            snapshot = orchestrator(str(project)).evidence_snapshot_hash(candidate)
            store.final_decision("atp_synthase", candidate, decision, reviewer, rationale, ai, snapshot)
            st.success("最终决定已连同证据快照哈希保存。")
        queue_labels = {"已计划": "Planned", "已提出": "Proposed"}
        queue_zh = st.selectbox("制备/测试队列状态", list(queue_labels))
        queue_state = queue_labels[queue_zh]
        proposed_action = st.text_input("建议行动", value="纳入后续实验验证复核")
        if st.button("加入制备/测试队列", disabled=not reviewer):
            store.queue("atp_synthase", candidate, queue_state, proposed_action, reviewer)
            st.success("计划状态已保存；没有据此生成计算、合成或实验结果。")


def activity_timeline(project: Path, title_fn):
    title_fn("统一活动记录", "AI查询、研究计划、计算任务、证据、团队复核与最终决定均来自真实登记记录")
    service = ActivityService(project, collaboration(str(project)))
    candidate = st.text_input("按候选编号筛选（可选）", key="timeline_candidate")
    frame = service.timeline(candidate_id=candidate or None)
    st.dataframe(frame, width="stretch", hide_index=True, height=650)
    st.caption("没有事件就不生成事件；没有实验反馈就不会出现实验完成记录。")


def dbtl_loop(project: Path, title_fn):
    title_fn("研究迭代闭环", "当前为计算驱动的设计—构建—验证—学习循环，不声称已经形成完整湿实验闭环")
    snapshot = ActivityService(project, collaboration(str(project))).dbtl_snapshot()
    st.metric("循环编号", snapshot["cycle_id"])
    cols = st.columns(4)
    stage_labels = {"design": "设计", "build": "构建", "test": "验证", "learn": "学习"}
    for column, stage in zip(cols, ["design", "build", "test", "learn"]):
        with column:
            st.markdown(f"### {stage_labels[stage]}")
            st.json(snapshot[stage])
    st.code("设计 → 构建 → 验证 → 学习 ↺", language=None)
    st.warning("当前不声称已形成湿实验闭环；真实实验结果仍需通过反馈质控和人工审查后进入系统。")


def presentation_mode(project: Path, title_fn, data):
    title_fn("演示模式", "集中展示真实登记数据、缓存任务、三维构象和研究者在环决策")
    st.markdown("### 推荐演示流程")
    for index, line in enumerate(orchestrator(str(project)).presentation_script(), 1):
        st.markdown(f"{index}. `{line}`")
    comparison, metrics = data.protocol_comparison()
    top = comparison.sort_values("abs_rank_delta", ascending=False).head(10)
    c1, c2, c3 = st.columns(3)
    c1.metric("真实HTVS候选", len(data.historical_candidates()))
    c2.metric("已登记Vina证据", data.dashboard_metrics()["historical_vina_evidence"])
    c3.metric("Glide/Vina匹配", metrics.get("matched_candidates", metrics.get("matched_subset", len(comparison))))
    st.dataframe(top, width="stretch", hide_index=True)
    if not top.empty:
        candidate = str(top.iloc[0]["canonical_id"])
        st.markdown(f"### 在三维空间查看候选 · `{candidate}`")
        embedded_pose(project, candidate, height=520)
    st.info("演示中的长任务只展示此前已完成并登记的真实缓存结果；系统不会模拟执行或制造数值。")
