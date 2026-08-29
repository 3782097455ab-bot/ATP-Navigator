"""ATP-Navigator Phase 18A local research workspace.

Run from the repository root with:
    streamlit run app.py
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import altair as alt
import pandas as pd
import streamlit as st
from rdkit import Chem
from rdkit.Chem import Draw

PROJECT = Path(__file__).resolve().parent
SRC = PROJECT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from app.data_adapter import ProjectData  # noqa: E402
from app.export_service import csv_bytes, markdown_bytes  # noqa: E402
from app.query_router import EXAMPLES, ResearchQueryRouter  # noqa: E402
from app.phase18b_views import (  # noqa: E402
    activity_timeline as phase18b_activity_timeline,
    dbtl_loop as phase18b_dbtl_loop,
    embedded_pose,
    presentation_mode as phase18b_presentation_mode,
    research_console as phase18b_research_console,
    structural_workspace as phase18b_structural_workspace,
    team_review_board as phase18b_team_review_board,
)


st.set_page_config(page_title="ATP-Navigator", page_icon="🧭", layout="wide", initial_sidebar_state="expanded")
st.markdown("""
<style>
  .block-container {padding-top: 1.1rem; padding-bottom: 3rem; max-width: 1540px;}
  [data-testid="stMetric"] {border: 1px solid #dfe7e5; border-radius: 8px; padding: 0.65rem; background: #fbfdfc;}
  .status-chip {display:inline-block; padding:.18rem .48rem; margin-right:.35rem; border-radius:999px;
    background:#e8f3ef; color:#174c3d; font-size:.78rem; border:1px solid #bfd6ce;}
  .warning-chip {background:#fff4db; color:#704b00; border-color:#eed392;}
  .unknown {color:#6a7470; font-style:italic;}
  .small-note {font-size:.82rem; color:#52605b;}
  h1 {font-size:1.62rem !important; margin-bottom:.1rem !important;}
  h2 {font-size:1.28rem !important;}
  h3 {font-size:1.05rem !important;}
</style>
""", unsafe_allow_html=True)


@st.cache_resource
def project_data() -> ProjectData:
    return ProjectData(PROJECT)


@st.cache_data(ttl=120, show_spinner=False)
def cached_frame(name: str) -> pd.DataFrame:
    data = project_data()
    return {
        "master": data.candidate_master,
        "evidence": data.evidence_matrix,
        "jobs": data.jobs,
        "capabilities": data.capabilities,
        "generated": data.generated_registry,
        "timeline": data.timeline,
    }[name]().copy()


@st.cache_data(ttl=120, show_spinner=False)
def cached_metrics() -> dict:
    return project_data().dashboard_metrics()


def paged(frame: pd.DataFrame, key: str, page_size: int = 50, height: int = 520):
    if frame.empty:
        st.info("没有可显示的登记记录。")
        return
    pages = max(1, (len(frame) + page_size - 1) // page_size)
    page = st.number_input("页码", 1, pages, 1, key=f"page_{key}")
    start = (int(page) - 1) * page_size
    st.caption(f"显示 {start + 1}–{min(start + page_size, len(frame))} / {len(frame)}")
    st.dataframe(frame.iloc[start:start + page_size], width="stretch", hide_index=True, height=height)


def title(text: str, subtitle: str):
    st.title(text)
    st.caption(subtitle)
    st.markdown('<span class="status-chip">模型冻结 v0–v4-alpha</span><span class="status-chip">真实 Registry 数据</span><span class="status-chip warning-chip">实验活性未推断</span>', unsafe_allow_html=True)


def dashboard():
    title("ATP-Navigator 研究工作区", "ATP合酶虚拟筛选后的 AI 辅助候选优先级决策系统")
    metrics = cached_metrics()
    cols = st.columns(5)
    cols[0].metric("HTVS 候选", metrics["historical_candidates"])
    cols[1].metric("生成结构", metrics["generated_candidates"])
    cols[2].metric("真实 Vina 证据", metrics["historical_vina_evidence"] + metrics["generated_vina_evidence"])
    cols[3].metric("Phase15 获取面板", metrics["acquisition_panel"])
    cols[4].metric("活动计算任务", metrics["active_jobs"])
    st.markdown("### 当前决策链")
    st.code("候选结构 → 证据登记 → 协议比较 → 冻结模型/多目标决策 → 预算感知证据获取 → 实验反馈入口", language=None)
    left, right = st.columns([1.35, 1])
    with left:
        st.markdown("### Evidence Registry 概览")
        matrix = cached_frame("evidence")
        summaries = []
        for col in ["structure", "glide", "vina", "mmgbsa", "admet", "literature_prior", "lineage", "experiment"]:
            if col in matrix:
                counts = matrix[col].value_counts().to_dict()
                summaries.append({"evidence_group": col, **counts})
        st.dataframe(pd.DataFrame(summaries).fillna(0), width="stretch", hide_index=True)
        st.warning("unknown、missing、not_applicable 分开保留；任何一项都不会自动当作 0。")
    with right:
        st.markdown("### 运行能力")
        caps = cached_frame("capabilities")
        if not caps.empty:
            st.dataframe(caps[[c for c in ["tool_id", "status", "version", "reason"] if c in caps]].head(18), width="stretch", hide_index=True)
        st.markdown("### 实验反馈")
        st.json(project_data().feedback_status(), expanded=False)


def overview():
    title("项目总览", "从真实计算化学项目到可追溯候选决策工作流")
    timeline = cached_frame("timeline")
    st.markdown("### 可核查开发时间线")
    paged(timeline, "timeline", page_size=20, height=430)
    st.markdown("### 科学边界")
    st.info("系统位于虚拟筛选之后、实验验证之前。它整合计算证据并给出实验优先级，不声称发现有效药物，不产生MIC、ATP酶抑制或毒性实验结果。")
    st.markdown("### 当前资产层")
    metrics = cached_metrics()
    st.json({**metrics, "scope": "pre-experimental candidate prioritization", "clinical_scope": "not_applicable", "biosafety_scope": "not_applicable"})


def candidate_explorer():
    title("候选浏览器", "统一查看 HTVS 1633、内部候选与 Phase16 生成结构；身份关系不靠名称猜测")
    frame = cached_frame("master")
    c1, c2, c3 = st.columns([2, 1, 1])
    query = c1.text_input("搜索 compound ID / alias / SMILES", placeholder="例如 Hit13 或 HTVS...")
    sources = c2.multiselect("来源", sorted(frame["candidate_source"].dropna().unique()), default=[])
    identity = c3.multiselect("身份状态", sorted(frame["identity_status"].astype(str).dropna().unique()), default=[])
    filtered = frame.copy()
    if query:
        mask = filtered[["compound_id", "display_name", "canonical_smiles"]].astype(str).apply(lambda s: s.str.contains(query, case=False, regex=False)).any(axis=1)
        filtered = filtered.loc[mask]
    if sources:
        filtered = filtered.loc[filtered["candidate_source"].isin(sources)]
    if identity:
        filtered = filtered.loc[filtered["identity_status"].astype(str).isin(identity)]
    show = [c for c in ["compound_id", "display_name", "candidate_source", "identity_status", "vina_affinity", "global_rank", "docking_score", "mmgbsa_score", "scaffold"] if c in filtered]
    paged(filtered[show], "candidate", page_size=40, height=390)
    if filtered.empty:
        return
    selected = st.selectbox("查看候选详情", filtered["compound_id"].tolist(), format_func=lambda cid: f"{filtered.loc[filtered.compound_id.eq(cid), 'display_name'].iloc[0]} · {cid}")
    detail = project_data().candidate_detail(selected)
    left, right = st.columns([1, 2.2])
    with left:
        mol = Chem.MolFromSmiles(str(detail.get("canonical_smiles", "")))
        if mol:
            st.image(Draw.MolToImage(mol, size=(420, 300)), caption="由登记 SMILES 实时绘制")
        else:
            st.warning("登记结构无法绘制。")
    with right:
        st.json(detail)
        matrix = cached_frame("evidence").loc[lambda x: x.compound_id.eq(str(selected))]
        st.dataframe(matrix, width="stretch", hide_index=True)
    with st.expander("Evidence provenance / 证据来源"):
        provenance = project_data().provenance(selected)
        st.dataframe(provenance, width="stretch", hide_index=True)
    with st.expander("View in 3D", expanded=False):
        embedded_pose(PROJECT, str(selected), height=540)


def evidence_matrix_page():
    title("证据矩阵", "不同证据组保持语义隔离；available、missing、unknown、not_applicable 不混淆")
    matrix = cached_frame("evidence")
    source = st.multiselect("候选来源", sorted(matrix["source"].unique()), default=[])
    evidence = st.selectbox("聚焦证据组", ["all", "structure", "glide", "vina", "mmgbsa", "admet", "literature_prior", "lineage", "experiment"])
    filtered = matrix.loc[matrix["source"].isin(source)] if source else matrix
    if evidence != "all":
        values = st.multiselect("状态", sorted(filtered[evidence].astype(str).unique()), default=[])
        if values:
            filtered = filtered.loc[filtered[evidence].astype(str).isin(values)]
    paged(filtered, "evidence", page_size=50)
    st.warning("这里的数据审计属于数据语义一致性、target annotation、endpoint segregation 和 provenance QC，不称为 biosafety。")


def protocol_comparison_page():
    title("协议比较", "Vina 与历史 Glide 的协议一致性审计；协议共识不等于生物活性")
    frame, metrics = project_data().protocol_comparison()
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Matched", metrics.get("matched_candidates", metrics.get("matched_subset", metrics.get("matched", len(frame)))))
    m2.metric("Spearman", f"{metrics.get('spearman', metrics.get('spearman_correlation', float('nan'))):.3f}")
    m3.metric("Kendall", f"{metrics.get('kendall_tau', metrics.get('kendall', float('nan'))):.3f}")
    m4.metric("Top10 overlap", metrics.get("top10_overlap", metrics.get("top_10_overlap", "unknown")))
    if not frame.empty:
        sample = frame if len(frame) <= 2500 else frame.sample(2500, random_state=17)
        chart = alt.Chart(sample).mark_circle(size=35, opacity=.45).encode(
            x=alt.X("glide_rank:Q", title="Glide rank"), y=alt.Y("vina_rank:Q", title="Vina rank"),
            color=alt.Color("abs_rank_delta:Q", scale=alt.Scale(scheme="viridis"), title="|rank delta|"),
            tooltip=[c for c in ["canonical_id", "glide_rank", "vina_rank", "rank_delta", "scaffold"] if c in sample]
        ).properties(height=520)
        st.altair_chart(chart, width="stretch")
        st.markdown("### 最大协议分歧")
        st.dataframe(frame.sort_values("abs_rank_delta", ascending=False).head(30), width="stretch", hide_index=True)
    st.warning("两个 docking 协议均属于计算证据；相关性或Top-k重叠不构成实验验证。")


def decision_workspace():
    title("决策工作区", "读取冻结的 Phase10 决策输出；切换研究目标，不重新训练或改写评分公式")
    profiles = ["balanced", "binding_focused", "atp_mechanism_focused", "experimental_validation_focused"]
    profile = st.selectbox("研究目标模式", profiles)
    ranking = project_data().decision_ranking(profile)
    if ranking.empty:
        st.error("冻结决策结果不可用。")
        return
    cols = [c for c in ["rank", "candidate", "historical_alias", "compound_id", "binding_score", "ATP_score", "antibacterial_score", "drug_score", "risk", "final_score", "decision_confidence", "evidence_coverage"] if c in ranking]
    st.dataframe(ranking[cols], width="stretch", hide_index=True, height=520)
    st.markdown("### Top 候选分量")
    top = ranking.head(10)
    components = [c for c in ["binding_score", "ATP_score", "antibacterial_score", "drug_score"] if c in top]
    if components:
        long = top.melt(id_vars="compound_id", value_vars=components, var_name="component", value_name="score")
        st.altair_chart(alt.Chart(long).mark_bar().encode(x="compound_id:N", y="score:Q", color="component:N", tooltip=list(long.columns)).properties(height=360), width="stretch")
    st.info("当前页面只读取已版本化输出。切换 profile 表示研究目标权重不同，不代表模型性能提升。")


def acquisition_workspace():
    title("证据获取工作区", "回答预算有限时下一份高成本证据应该获取在哪个候选上")
    labels = {"ATP-Navigator Hybrid": "ATP_Navigator_hybrid", "Vina Top": "vina_top", "Glide Top": "glide_top",
              "Consensus Top": "consensus_top", "Diversity-aware": "diversity_aware", "Disagreement-aware": "disagreement_aware",
              "Uncertainty-aware": "uncertainty_aware", "Evidence gap": "evidence_gap", "Random baseline": "random"}
    c1, c2 = st.columns(2)
    label = c1.selectbox("获取策略", list(labels))
    budget = c2.select_slider("高成本证据预算", [10, 20, 40, 60, 100], value=20)
    with st.spinner("读取冻结 Phase15 特征与策略顺序…"):
        selected = project_data().acquisition_recommendations(labels[label], budget)
    m1, m2, m3 = st.columns(3)
    m1.metric("候选数", len(selected))
    m2.metric("不同 scaffold", selected["scaffold"].nunique(dropna=True))
    m3.metric("平均协议不确定性", f"{selected['protocol_uncertainty'].mean():.3f}")
    st.dataframe(selected, width="stretch", hide_index=True, height=520)
    simulation = pd.read_csv(PROJECT / "results/phase15/budget_simulation.csv")
    st.markdown("### 已冻结预算模拟")
    st.dataframe(simulation.loc[simulation["budget"].eq(budget)] if "budget" in simulation else simulation, width="stretch", hide_index=True)
    st.warning("VOI 是证据获取启发式，不是真实经济价值；acquisition score 不是生物活性概率。")


def molecule_generation():
    title("分子扩展工作区", "查看 Phase16 真实生成结构和谱系；不可用生成后端不会伪造输出")
    registry = cached_frame("generated")
    caps = cached_frame("capabilities")
    generator_caps = caps.loc[caps["tool_id"].astype(str).str.startswith("generator:")] if not caps.empty else caps
    if not generator_caps.empty:
        st.dataframe(generator_caps, width="stretch", hide_index=True)
    parents = sorted(registry["parent_id"].astype(str).unique()) if "parent_id" in registry and not registry.empty else []
    parent = st.selectbox("种子候选", ["all", *parents])
    subset = registry if parent == "all" else registry.loc[registry["parent_id"].astype(str).eq(parent)]
    show = [c for c in ["compound_id", "parent_id", "parent_alias", "canonical_smiles", "murcko_scaffold", "MW", "cLogP", "TPSA", "sa_like_proxy", "structural_warnings", "provenance_hash"] if c in subset]
    paged(subset[show], "generated", page_size=40)
    st.markdown("### 新扩展请求（安全预览）")
    n = st.number_input("期望生成数量", 1, 500, 30)
    preserve = st.checkbox("保留 scaffold", value=True)
    preview = {"action": "molecule_expansion_request", "backend": "rdkit_rgroup_enumeration", "seed": parent,
               "requested_count": int(n), "preserve_scaffold": preserve, "scientific_output_created": False,
               "reason": "Phase18A only previews a versioned request; existing Phase16 outputs remain frozen"}
    st.json(preview)
    confirmed = st.checkbox("我确认这只是任务请求预览，不会生成或覆盖 Phase16 结果", key="gen_confirm")
    if st.button("保存版本化请求", disabled=not confirmed):
        request_dir = PROJECT / "workspace_local/phase18a/requests"
        request_dir.mkdir(parents=True, exist_ok=True)
        target = request_dir / f"generation_{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}.json"
        target.write_text(json.dumps({**preview, "created_at": datetime.now(timezone.utc).isoformat()}, ensure_ascii=False, indent=2), encoding="utf-8")
        st.success(f"已保存请求：{target.relative_to(PROJECT)}。未执行计算。")


def execution_jobs():
    title("执行任务", "共享 Calculation Job Registry；终态任务不会被界面自动重启")
    jobs = cached_frame("jobs")
    if jobs.empty:
        st.info("当前没有登记任务。")
        return
    statuses = st.multiselect("状态", sorted(jobs["status"].astype(str).unique()), default=[])
    filtered = jobs.loc[jobs["status"].astype(str).isin(statuses)] if statuses else jobs
    show = [c for c in ["job_id", "candidate_id", "tool_id", "protocol_id", "status", "created_at", "started_at", "completed_at", "return_code", "failure_reason"] if c in filtered]
    paged(filtered[show], "jobs", page_size=50)
    selected = st.selectbox("检查任务", filtered["job_id"].astype(str).head(500).tolist())
    record = filtered.loc[filtered["job_id"].astype(str).eq(selected)].iloc[0].to_dict()
    st.json(record)
    terminal = str(record.get("status")) in {"completed", "failed", "blocked", "cancelled"}
    c1, c2, c3 = st.columns(3)
    c1.button("暂停", disabled=str(record.get("status")) != "running", help="仅运行中任务可暂停；本界面不伪造 supervisor 状态。")
    c2.button("恢复", disabled=True, help="需要由原 workflow supervisor 按 checkpoint 恢复。")
    c3.button("重试失败", disabled=not (str(record.get("status")) == "failed" and False), help="Phase18A 不自动重启冻结历史任务。")
    if terminal:
        st.info("这是终态记录。Phase18A 默认只读，避免重复执行或改变冻结协议。")


def tool_capability():
    title("工具能力", "实际能力探测结果；不可用与未授权明确区分")
    caps = cached_frame("capabilities")
    status = st.multiselect("状态", sorted(caps["status"].astype(str).unique()), default=[])
    if status:
        caps = caps.loc[caps["status"].astype(str).isin(status)]
    st.dataframe(caps, width="stretch", hide_index=True, height=620)
    st.warning("OpenMM 包可导入不代表 protein–ligand MM/GBSA 工具链可用。Phase17 已按科学能力门控停止；本阶段不启动 WSL。")


def research_dialogue():
    title("研究对话", "类似研究助手的查询层，但所有回答必须来自 Registry 和冻结分析")
    st.caption("示例：" + " ｜ ".join(EXAMPLES))
    if "messages" not in st.session_state:
        st.session_state.messages = []
    for message in st.session_state.messages:
        with st.chat_message(message["role"]):
            st.markdown(message["content"])
            if message.get("records"):
                st.dataframe(pd.DataFrame(message["records"]), width="stretch", hide_index=True)
            if message.get("provenance"):
                with st.expander("Provenance"):
                    st.json(message["provenance"])
    question = st.chat_input("询问候选证据、预算、协议分歧或工具能力")
    if question:
        st.session_state.messages.append({"role": "user", "content": question})
        answer = ResearchQueryRouter(project_data()).answer(question)
        content = answer["answer"] + (f"\n\n⚠️ {answer['warning']}" if answer.get("warning") else "")
        st.session_state.messages.append({"role": "assistant", "content": content, "records": answer.get("records", []), "provenance": answer.get("provenance", [])})
        st.rerun()


def experiment_feedback():
    title("实验反馈", "为未来真实湿实验结果保留 QC、人工审查、独立版本和前瞻比较接口")
    status = project_data().feedback_status()
    st.json(status)
    if not status.get("latest_snapshot"):
        st.info("当前没有经人工审查的实验反馈。feedback status = empty；prospective metrics = not_available。")
    uploaded = st.file_uploader("预览反馈 CSV 表头（不会自动导入）", type=["csv"])
    if uploaded:
        try:
            frame = pd.read_csv(uploaded, nrows=30)
            required = set(__import__("experimental_feedback").FIELDS)
            missing = sorted(required - set(frame.columns))
            st.dataframe(frame, width="stretch", hide_index=True)
            if missing:
                st.error(f"缺少字段：{missing}")
            else:
                st.success("表头通过第一层检查。正式导入仍要求证据文件路径、hash和人工审查。")
        except Exception as error:
            st.error(f"无法读取：{error}")
    st.warning("本页面不会把上传数据直接加入训练，也不会自动替换历史模型。")


def export_page():
    title("导出", "导出当前已登记结果，并附加项目、commit、模型范围和时间元数据")
    choices = {"候选总表": cached_frame("master"), "证据矩阵": cached_frame("evidence"),
               "计算任务": cached_frame("jobs"), "工具能力": cached_frame("capabilities"),
               "Decision balanced": project_data().decision_ranking("balanced"),
               "Phase15 acquisition panel": pd.read_csv(PROJECT / "results/phase15/acquisition_panel_v1.csv")}
    name = st.selectbox("导出内容", list(choices))
    frame = choices[name]
    st.dataframe(frame.head(100), width="stretch", hide_index=True)
    c1, c2 = st.columns(2)
    c1.download_button("下载 CSV", csv_bytes(frame, name, project_data()), file_name=f"ATP_Navigator_{name.replace(' ', '_')}.csv", mime="text/csv")
    c2.download_button("下载 Markdown 摘要", markdown_bytes(name, frame, name, project_data()), file_name=f"ATP_Navigator_{name.replace(' ', '_')}.md", mime="text/markdown")


PAGES = {
    "AI Research Console": lambda: phase18b_research_console(PROJECT, title),
    "Dashboard": dashboard,
    "Project Overview": overview,
    "Candidate Explorer": candidate_explorer,
    "Evidence Matrix": evidence_matrix_page,
    "Protocol Comparison": protocol_comparison_page,
    "Decision Workspace": decision_workspace,
    "Acquisition Workspace": acquisition_workspace,
    "Molecule Generation": molecule_generation,
    "Execution Jobs": execution_jobs,
    "Tool Capability": tool_capability,
    "Research Dialogue": research_dialogue,
    "3D Structural Workspace": lambda: phase18b_structural_workspace(PROJECT, title, project_data()),
    "Team Review Board": lambda: phase18b_team_review_board(PROJECT, title, project_data()),
    "Activity Timeline": lambda: phase18b_activity_timeline(PROJECT, title),
    "DBTL Loop": lambda: phase18b_dbtl_loop(PROJECT, title),
    "Presentation Mode": lambda: phase18b_presentation_mode(PROJECT, title, project_data()),
    "Experiment Feedback": experiment_feedback,
    "Export": export_page,
}

with st.sidebar:
    st.markdown("## ATP-Navigator")
    st.caption("Phase 18B · conversational execution & collaboration")
    selected_page = st.radio("导航", list(PAGES), label_visibility="collapsed")
    st.divider()
    git = project_data().git_state()
    st.caption(f"branch: {git['branch']} · commit: {git['commit']}")
    st.caption("科研边界：实验前计算证据整合与候选优先级辅助决策")

PAGES[selected_page]()
