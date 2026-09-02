"""研序智航——面向科研人员的候选优先级决策工作台。

Run from the repository root with:
    streamlit run app.py
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from html import escape
from pathlib import Path

import altair as alt
import pandas as pd
import streamlit as st
from rdkit import Chem

# The core cheminformatics reader works on the headless cloud image even when
# optional X11 drawing libraries are absent.  Keep 2D rendering optional so a
# missing libXrender cannot take down the evidence/decision application.
try:
    from rdkit.Chem import Draw
except ImportError:  # pragma: no cover - depends on the cloud system image
    Draw = None

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
    deployment_info,
)


PRODUCT_NAME = "研序智航"
PRODUCT_TAGLINE = "AI辅助候选优先级决策工作台"
PRODUCT_VERSION = "公测版 0.9"

st.set_page_config(page_title=f"{PRODUCT_NAME}｜{PRODUCT_TAGLINE}", page_icon="🧬", layout="wide", initial_sidebar_state="expanded")
st.markdown("""
<style>
  :root {
    --yx-ink:#17272a; --yx-deep:#233438; --yx-blue:#10a8c8;
    --yx-green:#58b957; --yx-mint:#eaf7f3; --yx-paper:#f6faf9;
    --yx-line:#d9e7e3; --yx-muted:#60716d;
  }
  .stApp {background:linear-gradient(145deg,#f8fbfa 0%,#f2f8f7 50%,#f7fbfd 100%); color:var(--yx-ink);}
  .block-container {padding-top:1rem; padding-bottom:4rem; max-width:1480px;}
  [data-testid="stSidebar"] {background:linear-gradient(180deg,#1f3134 0%,#17272a 100%); border-right:1px solid #30484a;}
  [data-testid="stSidebar"] * {color:#edf8f5;}
  [data-testid="stSidebar"] [role="radiogroup"] label {padding:.42rem .58rem; border-radius:9px; margin:.08rem 0;}
  [data-testid="stSidebar"] [role="radiogroup"] label:hover {background:rgba(16,168,200,.14);}
  [data-testid="stSidebar"] [data-checked="true"] {background:linear-gradient(90deg,rgba(88,185,87,.25),rgba(16,168,200,.20));}
  [data-testid="stHeader"] {background:transparent;}
  [data-testid="stToolbar"], #MainMenu, footer {display:none !important;}
  [data-testid="stMetric"] {border:1px solid var(--yx-line); border-radius:14px; padding:.8rem 1rem; background:rgba(255,255,255,.88); box-shadow:0 7px 24px rgba(35,52,56,.05);}
  [data-testid="stMetricValue"] {color:#173e42;}
  .yx-brand {padding:.55rem .2rem 1rem;}
  .yx-brand-mark {width:38px;height:38px;border-radius:12px;background:linear-gradient(135deg,var(--yx-green),var(--yx-blue));display:inline-flex;align-items:center;justify-content:center;font-weight:800;font-size:19px;box-shadow:0 8px 24px rgba(16,168,200,.22);}
  .yx-brand-name {display:inline-block;margin-left:.65rem;font-size:1.2rem;font-weight:760;vertical-align:middle;letter-spacing:.05em;}
  .yx-brand-sub {font-size:.75rem;color:#a9c5bf !important;margin:.35rem 0 0 3.2rem;}
  .yx-topbar {display:flex;justify-content:space-between;align-items:center;padding:.75rem 1rem;margin-bottom:.9rem;border:1px solid var(--yx-line);border-radius:14px;background:rgba(255,255,255,.82);backdrop-filter:blur(12px);}
  .yx-topbar strong {font-size:.95rem}.yx-topbar span {color:var(--yx-muted);font-size:.8rem;}
  .yx-hero {position:relative;overflow:hidden;padding:1.35rem 1.5rem;margin:.25rem 0 1.15rem;border-radius:18px;background:linear-gradient(120deg,#20363a 0%,#174f58 58%,#0d879f 100%);color:white;box-shadow:0 16px 42px rgba(24,63,70,.18);}
  .yx-hero:after {content:"";position:absolute;right:-70px;top:-110px;width:280px;height:280px;border:42px solid rgba(88,185,87,.30);border-radius:50%;}
  .yx-hero h1 {font-size:1.7rem !important;margin:0 0 .35rem !important;color:white;}
  .yx-hero p {margin:0;color:#d7ece9;max-width:820px;}
  .status-chip {display:inline-block;padding:.22rem .55rem;margin:.6rem .32rem 0 0;border-radius:999px;background:#e9f7f1;color:#14543f;font-size:.76rem;border:1px solid #bfe2d4;}
  .warning-chip {background:#fff4da;color:#725000;border-color:#efd28b;}
  .unknown {color:#6a7470;font-style:italic;}.small-note{font-size:.82rem;color:#52605b;}
  h1 {font-size:1.58rem !important;margin-bottom:.1rem !important;} h2{font-size:1.25rem !important;} h3{font-size:1.02rem !important;}
  .stButton>button {border-radius:10px;border-color:#c9ded9;}
  .stButton>button[kind="primary"] {background:linear-gradient(90deg,var(--yx-green),#2aa990);border:0;color:white;}
  [data-testid="stChatMessage"] {border:1px solid var(--yx-line);border-radius:14px;background:rgba(255,255,255,.78);padding:.25rem .4rem;}
  .yx-footer {margin-top:2rem;padding-top:1rem;border-top:1px solid var(--yx-line);color:var(--yx-muted);font-size:.75rem;text-align:center;}
</style>
""", unsafe_allow_html=True)


@st.cache_resource
def project_data() -> ProjectData:
    return ProjectData(PROJECT)


@st.cache_data(ttl=120, show_spinner=False)
def cached_frame(name: str) -> pd.DataFrame:
    data = project_data()
    return {
        "master": data.candidate_explorer_candidates,
        "evidence": data.evidence_matrix,
        "jobs": data.jobs,
        "capabilities": data.capabilities,
        "generated": data.generated_registry,
        "timeline": data.timeline,
    }[name]().copy()


@st.cache_data(ttl=120, show_spinner=False)
def cached_metrics() -> dict:
    return project_data().dashboard_metrics()


COLUMN_ZH = {
    "compound_id": "候选编号", "canonical_id": "规范编号", "candidate_id": "候选编号",
    "display_name": "显示名称", "candidate_source": "候选来源", "source": "来源",
    "identity_status": "身份状态", "canonical_smiles": "规范SMILES", "scaffold": "骨架",
    "global_rank": "全库排名", "rank": "排名", "docking_score": "Glide评分",
    "vina_affinity": "Vina亲和分数", "mmgbsa_score": "MM/GBSA评分",
    "open_mmgbsa_deltaG": "开放MM/GBSA ΔG", "open_mmgbsa_sd": "MM/GBSA标准差",
    "qc_status": "质控状态", "status": "状态", "reason": "原因", "version": "版本",
    "tool_id": "工具编号", "job_id": "任务编号", "protocol_id": "协议编号",
    "created_at": "创建时间", "started_at": "开始时间", "completed_at": "完成时间",
    "return_code": "返回码", "failure_reason": "失败原因", "evidence_group": "证据组",
    "structure": "结构", "glide": "Glide", "vina": "Vina", "mmgbsa": "MM/GBSA",
    "admet": "ADMET", "literature_prior": "文献先验", "lineage": "谱系", "experiment": "实验",
    "final_score": "综合得分", "decision_confidence": "决策置信度", "evidence_coverage": "证据覆盖度",
    "binding_score": "结合得分", "ATP_score": "ATP相关得分", "antibacterial_score": "抗菌知识得分",
    "drug_score": "成药性得分", "risk": "风险", "parent_id": "母体编号",
    "parent_alias": "母体别名", "murcko_scaffold": "Murcko骨架", "structural_warnings": "结构提示",
    "provenance_hash": "溯源哈希", "reviewer": "复核人", "task": "任务类型",
    "dataset": "数据集", "size": "规模", "input": "输入", "output": "输出",
    "split": "划分", "metric": "指标", "reference": "参考文献", "relevance": "相关性",
    "verification": "核验状态", "execution_status": "执行状态",
}

VALUE_ZH = {
    "available": "可用", "missing": "缺失", "unknown": "未知", "not_applicable": "不适用",
    "completed": "已完成", "running": "运行中", "planned": "已计划", "ready": "待运行",
    "blocked": "受阻", "failed": "失败", "cancelled": "已取消", "pending": "待处理",
    "pass": "通过", "exact": "精确匹配", "unresolved": "待解析", "not_available": "不可用",
}


def zh_frame(frame: pd.DataFrame) -> pd.DataFrame:
    """仅本地化展示列名，不改变底层数据或导出契约。"""
    localized = frame.copy().replace(VALUE_ZH)
    return localized.rename(columns={c: COLUMN_ZH.get(c, c) for c in localized.columns})


_STREAMLIT_DATAFRAME = st.dataframe


def _localized_dataframe(data, *args, **kwargs):
    """统一中文化界面表头；底层DataFrame、CSV与模型输入保持原样。"""
    if isinstance(data, pd.DataFrame):
        data = zh_frame(data)
    return _STREAMLIT_DATAFRAME(data, *args, **kwargs)


st.dataframe = _localized_dataframe


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
    st.markdown(
        f'<div class="yx-topbar"><strong>{PRODUCT_NAME} · {PRODUCT_VERSION}</strong>'
        f'<span>本地科研工作区　｜　数据可追溯　｜　研究者在环</span></div>',
        unsafe_allow_html=True,
    )
    st.markdown(
        f'<section class="yx-hero"><h1>{escape(text)}</h1><p>{escape(subtitle)}</p></section>',
        unsafe_allow_html=True,
    )
    st.markdown('<span class="status-chip">模型冻结 v0–v4-alpha</span><span class="status-chip">真实 Registry 数据</span><span class="status-chip warning-chip">实验活性未推断</span>', unsafe_allow_html=True)


def dashboard():
    title("科研决策工作台", "从虚拟筛选候选集合出发，统一查看计算证据、协议分歧、优先级排序与下一步研究建议")
    st.markdown("### 从这里开始")
    q1, q2, q3 = st.columns(3)
    q1.info("**向助手提问**\n\n用自然语言描述研究目标、候选范围和计算预算。")
    q2.info("**检查证据**\n\n核对每个候选的结构、Glide、Vina、MM/GBSA与缺失项。")
    q3.info("**形成决策**\n\n查看多目标排序和推荐理由，由研究者确认下一步。")
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
        st.markdown("### 证据登记概览")
        matrix = cached_frame("evidence")
        summaries = []
        for col in ["structure", "glide", "vina", "mmgbsa", "admet", "literature_prior", "lineage", "experiment"]:
            if col in matrix:
                counts = matrix[col].value_counts().to_dict()
                summaries.append({"evidence_group": col, **counts})
        st.dataframe(pd.DataFrame(summaries).fillna(0), width="stretch", hide_index=True)
        st.warning("未知、缺失、不适用三种状态分开保留；任何一项都不会自动当作 0。")
    with right:
        st.markdown("### 运行能力")
        caps = cached_frame("capabilities")
        if not caps.empty:
            st.dataframe(caps[[c for c in ["tool_id", "status", "version", "reason"] if c in caps]].head(18), width="stretch", hide_index=True)
        st.markdown("### 实验反馈")
        st.json(project_data().feedback_status(), expanded=False)


def external_benchmark_registry():
    title("外部基准资源库", "公开AI基准数据资源地图；目录登记不等于已经运行或获得验证结果")
    registry = project_data().benchmark_registry()
    status = project_data().benchmark_status()
    if registry.empty:
        st.info("当前没有已登记的 benchmark metadata。")
    else:
        c1, c2, c3 = st.columns(3)
        c1.metric("已登记资源", len(registry))
        c2.metric("已实际运行", int(registry.get("execution_status", pd.Series(dtype=str)).eq("completed").sum()))
        c3.metric("训练记录", 0)
        tasks = st.multiselect("任务类型", sorted(registry["task"].dropna().astype(str).unique()), default=[])
        verification = st.multiselect("核验状态", sorted(registry["verification"].dropna().astype(str).unique()), default=[])
        filtered = registry.copy()
        if tasks:
            filtered = filtered.loc[filtered["task"].isin(tasks)]
        if verification:
            filtered = filtered.loc[filtered["verification"].isin(verification)]
        show = [c for c in ["benchmark_id", "dataset", "task", "size", "input", "output", "split", "metric", "source", "reference", "relevance", "verification", "execution_status"] if c in filtered]
        paged(filtered[show], "benchmark_registry", page_size=30, height=520)
    st.warning(f"第一部分实验基准记录：{status.get('Part1 experimental benchmark records', '待补充')}。第二部分26条记录仅为元数据目录，尚未声称已执行。")


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
    show = [c for c in ["compound_id", "display_name", "candidate_source", "identity_status", "vina_affinity", "global_rank", "docking_score", "mmgbsa_score", "open_mmgbsa_deltaG", "open_mmgbsa_sd", "qc_status", "scaffold"] if c in filtered]
    paged(filtered[show], "candidate", page_size=40, height=390)
    if filtered.empty:
        return
    selected = st.selectbox("查看候选详情", filtered["compound_id"].tolist(), format_func=lambda cid: f"{filtered.loc[filtered.compound_id.eq(cid), 'display_name'].iloc[0]} · {cid}")
    detail = project_data().candidate_detail(selected)
    left, right = st.columns([1, 2.2])
    with left:
        mol = Chem.MolFromSmiles(str(detail.get("canonical_smiles", "")))
        if mol and Draw is not None:
            st.image(Draw.MolToImage(mol, size=(420, 300)), caption="由登记 SMILES 实时绘制")
        elif mol:
            st.info("当前云端镜像不提供可选的 RDKit 2D 绘图库；结构身份、描述符和登记证据仍可正常使用。")
        else:
            st.warning("登记结构无法绘制。")
    with right:
        st.json(detail)
        matrix = cached_frame("evidence").loc[lambda x: x.compound_id.eq(str(selected))]
        st.dataframe(matrix, width="stretch", hide_index=True)
    with st.expander("证据来源与溯源记录"):
        provenance = project_data().provenance(selected)
        st.dataframe(provenance, width="stretch", hide_index=True)
    with st.expander("在三维空间中查看", expanded=False):
        embedded_pose(PROJECT, str(selected), height=540)


def evidence_matrix_page():
    title("证据矩阵", "不同证据组保持语义隔离；可用、缺失、未知、不适用四种状态不会混淆")
    matrix = cached_frame("evidence")
    source = st.multiselect("候选来源", sorted(matrix["source"].unique()), default=[])
    evidence_labels = {"全部": "all", "结构": "structure", "Glide": "glide", "Vina": "vina", "MM/GBSA": "mmgbsa", "ADMET": "admet", "文献先验": "literature_prior", "谱系": "lineage", "实验": "experiment"}
    evidence = evidence_labels[st.selectbox("聚焦证据组", list(evidence_labels))]
    filtered = matrix.loc[matrix["source"].isin(source)] if source else matrix
    if evidence != "all":
        values = st.multiselect("状态", sorted(filtered[evidence].astype(str).unique()), default=[])
        if values:
            filtered = filtered.loc[filtered[evidence].astype(str).isin(values)]
    paged(filtered, "evidence", page_size=50)
    st.warning("这里的数据审计属于数据语义一致性、target annotation、endpoint segregation 和 provenance QC，不称为 biosafety。")


def protocol_comparison_page():
    title("协议比较", "历史 Glide、Vina 与真实 open MM/GBSA 的协议一致性审计；协议共识不等于生物活性")
    tab_three, tab_full = st.tabs(["Phase17.1 三协议（30候选）", "Phase14 Glide/Vina 全库"])
    with tab_three:
        summary = project_data().phase17_1_post_analysis()
        metrics_rows = summary.get("pairwise_metrics", [])
        three = project_data().phase17_1_three_protocol()
        disagreement = project_data().phase17_1_protocol_disagreement()
        impact = project_data().phase17_1_evidence_impact()
        c1, c2, c3 = st.columns(3)
        c1.metric("MM/GBSA真实结果", int(three.get("open_mmgbsa_deltaG", pd.Series(dtype=float)).notna().sum()))
        c2.metric("三协议精确匹配", summary.get("three_protocol_matched_n", "未知"))
        c3.metric("未填充缺失值", "是")
        if metrics_rows:
            st.dataframe(pd.DataFrame(metrics_rows), width="stretch", hide_index=True)
        if not three.empty:
            ranks = three[[c for c in ["candidate_id", "glide_utility", "vina_utility", "mmgbsa_utility"] if c in three]].melt(
                id_vars="candidate_id", var_name="protocol", value_name="rank_utility"
            ).dropna()
            st.altair_chart(
                alt.Chart(ranks).mark_circle(size=55, opacity=.65).encode(
                    x=alt.X("candidate_id:N", sort=None, axis=alt.Axis(labels=False), title="试运行候选"),
                    y=alt.Y("rank_utility:Q", title="协议内排名效用"),
                    color="protocol:N", tooltip=list(ranks.columns),
                ).properties(height=360), width="stretch"
            )
        left, right = st.columns(2)
        with left:
            st.markdown("### 最大三协议分歧")
            if not disagreement.empty:
                st.dataframe(disagreement.sort_values("three_protocol_disagreement", ascending=False).head(15), width="stretch", hide_index=True)
        with right:
            st.markdown("### 加入 MM/GBSA 后最大 shadow rank 变化")
            if not impact.empty:
                show = impact.assign(abs_rank_change=pd.to_numeric(impact["rank_change_after_mmgbsa"], errors="coerce").abs())
                st.dataframe(show.sort_values("abs_rank_change", ascending=False).head(15), width="stretch", hide_index=True)
        st.info("三协议只按各自有限样本的排名百分位比较；影子运行不会覆盖冻结决策引擎。")
    with tab_full:
        frame, metrics = project_data().protocol_comparison()
        m1, m2, m3, m4 = st.columns(4)
        m1.metric("匹配候选", metrics.get("matched_candidates", metrics.get("matched_subset", metrics.get("matched", len(frame)))))
        m2.metric("Spearman", f"{metrics.get('spearman', metrics.get('spearman_correlation', float('nan'))):.3f}")
        m3.metric("Kendall", f"{metrics.get('kendall_tau', metrics.get('kendall', float('nan'))):.3f}")
        m4.metric("前10名重叠", metrics.get("top10_overlap", metrics.get("top_10_overlap", "未知")))
        if not frame.empty:
            sample = frame if len(frame) <= 2500 else frame.sample(2500, random_state=17)
            chart = alt.Chart(sample).mark_circle(size=35, opacity=.45).encode(
                x=alt.X("glide_rank:Q", title="Glide排名"), y=alt.Y("vina_rank:Q", title="Vina排名"),
                color=alt.Color("abs_rank_delta:Q", scale=alt.Scale(scheme="viridis"), title="排名差绝对值"),
                tooltip=[c for c in ["canonical_id", "glide_rank", "vina_rank", "rank_delta", "scaffold"] if c in sample]
            ).properties(height=520)
            st.altair_chart(chart, width="stretch")
            st.markdown("### 最大协议分歧")
            st.dataframe(frame.sort_values("abs_rank_delta", ascending=False).head(30), width="stretch", hide_index=True)
    st.warning("两个 docking 协议均属于计算证据；相关性或Top-k重叠不构成实验验证。")


def decision_workspace():
    title("决策工作区", "历史冻结决策与更新证据后的影子运行并存；任何历史版本都不会被覆盖")
    frozen_tab, rc_tab = st.tabs(["冻结决策（17候选）", "竞赛候选版三协议影子决策（30候选）"])
    with frozen_tab:
        profile_labels = {"均衡模式": "balanced", "结合证据优先": "binding_focused", "ATP机制优先": "atp_mechanism_focused", "实验验证优先": "experimental_validation_focused"}
        profile = profile_labels[st.selectbox("研究目标模式", list(profile_labels))]
        ranking = project_data().decision_ranking(profile)
        if ranking.empty:
            st.error("冻结决策结果不可用。")
        else:
            cols = [c for c in ["rank", "candidate", "historical_alias", "compound_id", "binding_score", "ATP_score", "antibacterial_score", "drug_score", "risk", "final_score", "decision_confidence", "evidence_coverage"] if c in ranking]
            st.dataframe(ranking[cols], width="stretch", hide_index=True, height=520)
            st.markdown("### Top 候选分量")
            top = ranking.head(10)
            components = [c for c in ["binding_score", "ATP_score", "antibacterial_score", "drug_score"] if c in top]
            if components:
                long = top.melt(id_vars="compound_id", value_vars=components, var_name="component", value_name="score")
                st.altair_chart(alt.Chart(long).mark_bar().encode(x="compound_id:N", y="score:Q", color="component:N", tooltip=list(long.columns)).properties(height=360), width="stretch")
    with rc_tab:
        rc = project_data().release_candidate_decision()
        manifest = project_data().release_candidate_manifest()
        if rc.empty:
            st.info("竞赛候选版决策运行尚未生成。")
        else:
            c1, c2, c3 = st.columns(3)
            c1.metric("候选", len(rc))
            c2.metric("三协议完整", int(rc["protocol_count"].eq(3).sum()))
            c3.metric("官方模型", manifest.get("official_model", "Model v3"))
            st.dataframe(rc, width="stretch", hide_index=True, height=560)
            st.warning("候选版运行属于更新证据后的影子决策；实验ATP抑制、MIC与毒性均保持未知，不覆盖冻结决策。")
    st.info("当前页面只读取已版本化输出。切换 profile 或查看 shadow run 不代表模型性能提升。")


def acquisition_workspace():
    title("证据获取工作区", "回答预算有限时下一份高成本证据应该获取在哪个候选上")
    labels = {"研序智航综合策略": "ATP_Navigator_hybrid", "Vina高分优先": "vina_top", "Glide高分优先": "glide_top",
              "协议共识优先": "consensus_top", "结构多样性优先": "diversity_aware", "协议分歧优先": "disagreement_aware",
              "不确定性优先": "uncertainty_aware", "证据缺口优先": "evidence_gap", "随机基线": "random"}
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
    st.warning("信息价值仅作为证据获取启发式，不代表真实经济价值；获取分数也不是生物活性概率。")


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
    deploy = deployment_info(PROJECT)
    if not deploy["can_execute_local_tools"]:
        st.info("云端只读模式无法调用执行后端。仍可查看已登记的历史结果，但不能发起新计算。")
    n = st.number_input("期望生成数量", 1, 500, 30)
    preserve = st.checkbox("保留 scaffold", value=True)
    preview = {"action": "molecule_expansion_request", "backend": "rdkit_rgroup_enumeration", "seed": parent,
               "requested_count": int(n), "preserve_scaffold": preserve, "scientific_output_created": False,
               "reason": "Phase18A only previews a versioned request; existing Phase16 outputs remain frozen"}
    st.json(preview)
    confirmed = st.checkbox("我确认这只是任务请求预览，不会生成或覆盖 Phase16 结果", key="gen_confirm")
    if st.button("保存版本化请求", disabled=not confirmed or not deploy["can_execute_local_tools"]):
        request_dir = PROJECT / "workspace_local/phase18a/requests"
        request_dir.mkdir(parents=True, exist_ok=True)
        target = request_dir / f"generation_{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}.json"
        target.write_text(json.dumps({**preview, "created_at": datetime.now(timezone.utc).isoformat()}, ensure_ascii=False, indent=2), encoding="utf-8")
        st.success(f"已保存请求：{target.relative_to(PROJECT)}。未执行计算。")


def scientific_workflow_page():
    title("可复现虚拟筛选流程", "从靶点与 IN-2 出发，逐层生成、过滤、计算、登记证据并进入研究者决策门控")
    summary_path = PROJECT / "results/library_generation/workflow_public_summary.json"
    if not summary_path.exists():
        st.info("可复现工作流尚未产生已核验的运行摘要。页面不会用示例数值替代真实结果。")
        return
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    st.warning("这里展示的是重建的可复现 IN-2 衍生库，不是、也不声称等同于历史 Auto_Enum 十万库。")
    c1, c2, c3, c4 = st.columns(4)
    stages = pd.DataFrame(summary.get("stage_counts", []))
    library_stage = stages.loc[stages["stage"].eq("Library Generation")]
    docking_stage = stages.loc[stages["stage"].eq("Docking")]
    c1.metric("母体结构", "IN-2")
    c2.metric("生成后唯一结构", int(library_stage.iloc[0]["output_count"]) if len(library_stage) else 0)
    c3.metric("真实 Vina 结果", int(docking_stage.iloc[0]["output_count"]) if len(docking_stage) else 0)
    c4.metric("工作流协议", summary.get("protocol_id", "unknown"))
    st.markdown("### 科研流程")
    st.code("靶点 + IN-2 → 衍生库生成 → 结构准备与过滤 → 开放工具对接 → 分层精筛 → 高成本证据门控 → 证据整合 → AI辅助决策 → 候选面板", language=None)
    if not stages.empty:
        display = stages.rename(columns={"stage":"流程层", "tool_protocol":"工具 / 协议", "status":"状态",
                                         "input_count":"输入数量", "output_count":"输出数量",
                                         "output":"输出", "provenance":"溯源"})
        st.dataframe(display, width="stretch", hide_index=True, height=500)
    st.markdown("### 四类证据边界")
    cols = st.columns(4)
    cols[0].info("**历史商业流程**\n\n只描述已有材料能够支持的 Schrödinger 工作流，不模拟缺失商业计算。")
    cols[1].info("**恢复的历史证据**\n\n历史 Glide、MM/GBSA 等结果原值只读，来源与身份状态单独保留。")
    cols[2].info("**重建开放流程**\n\nRDKit 确定性生成与真实 Vina 使用独立协议名，不能冒充 Glide SP/XP。")
    cols[3].info("**AI决策扩展**\n\n冻结模型只在输入契约满足时调用；缺失关键证据时明确输出未知或待补充。")
    st.markdown("### 运行溯源")
    st.json({"运行编号":summary.get("run_id"), "衍生库哈希":summary.get("library_hash"),
             "生成配置哈希":summary.get("config_hash"), "输出":summary.get("outputs", {})}, expanded=False)


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
    st.warning("OpenMM软件包能够导入，不等于蛋白—配体MM/GBSA完整工具链可用。高成本计算严格遵循科学能力门控。")


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
    with st.form("research_dialogue_input", clear_on_submit=True):
        question = st.text_input("询问候选证据、预算、协议分歧或工具能力")
        submitted = st.form_submit_button("发送")
    if submitted and question.strip():
        question = question.strip()
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
               "均衡决策结果": project_data().decision_ranking("balanced"),
               "第15阶段证据获取面板": pd.read_csv(PROJECT / "results/phase15/acquisition_panel_v1.csv")}
    name = st.selectbox("导出内容", list(choices))
    frame = choices[name]
    st.dataframe(frame.head(100), width="stretch", hide_index=True)
    c1, c2 = st.columns(2)
    c1.download_button("下载 CSV", csv_bytes(frame, name, project_data()), file_name=f"YanXu_ZhiHang_{name.replace(' ', '_')}.csv", mime="text/csv")
    c2.download_button("下载 Markdown 摘要", markdown_bytes(name, frame, name, project_data()), file_name=f"YanXu_ZhiHang_{name.replace(' ', '_')}.md", mime="text/markdown")


PAGES = {
    "✨ 智能研究助手": lambda: phase18b_research_console(PROJECT, title),
    "⌂ 工作台首页": dashboard,
    "◫ 候选库": candidate_explorer,
    "▦ 证据矩阵": evidence_matrix_page,
    "⇄ 协议比较": protocol_comparison_page,
    "◎ 决策工作台": decision_workspace,
    "◈ 证据获取": acquisition_workspace,
    "⬡ 三维结构": lambda: phase18b_structural_workspace(PROJECT, title, project_data()),
    "⌁ 分子扩展": molecule_generation,
    "▥ 科研工作流": scientific_workflow_page,
    "▣ 计算任务": execution_jobs,
    "⚙ 工具能力": tool_capability,
    "↺ 实验反馈": experiment_feedback,
    "♧ 团队复核": lambda: phase18b_team_review_board(PROJECT, title, project_data()),
    "◷ 活动记录": lambda: phase18b_activity_timeline(PROJECT, title),
    "⟳ 迭代闭环": lambda: phase18b_dbtl_loop(PROJECT, title),
    "▤ 外部基准": external_benchmark_registry,
    "◇ 项目历程": overview,
    "▶ 演示模式": lambda: phase18b_presentation_mode(PROJECT, title, project_data()),
    "⇩ 导出中心": export_page,
}


@st.dialog("欢迎使用研序智航", width="large")
def onboarding_dialog():
    st.markdown("#### 从虚拟筛选结果，到可解释的实验候选优先级")
    st.write("研序智航位于计算筛选之后、实验验证之前。它帮助研究者整合多协议证据、识别分歧、安排有限计算预算，并保留每一步依据。")
    c1, c2, c3 = st.columns(3)
    with c1:
        st.markdown("**① 提出研究问题**")
        st.caption("在“智能研究助手”中直接描述目标和预算，系统会先生成可检查的计划。")
    with c2:
        st.markdown("**② 检查候选证据**")
        st.caption("在候选库、证据矩阵和协议比较中核对结构、来源、缺失项与协议分歧。")
    with c3:
        st.markdown("**③ 做出研究者决策**")
        st.caption("查看可解释排序、团队复核和下一步证据建议；AI不会替代最终科研判断。")
    st.info("快速体验：进入“智能研究助手”，输入“找出 Glide 和 Vina 分歧最大的 10 个候选”。")
    if st.button("开始使用", type="primary", width="stretch"):
        st.session_state["yx_onboarding_complete"] = True
        st.rerun()


with st.sidebar:
    st.markdown(
        '<div class="yx-brand"><span class="yx-brand-mark">研</span>'
        '<span class="yx-brand-name">研序智航</span>'
        '<div class="yx-brand-sub">AI辅助候选优先级决策工作台</div></div>',
        unsafe_allow_html=True,
    )
    if st.button("＋ 新建研究会话", type="primary", width="stretch"):
        st.session_state.pop("phase18b_messages", None)
        st.session_state.pop("phase18b_pending_plan", None)
        st.session_state["yx_nav_page"] = "✨ 智能研究助手"
        st.rerun()
    if st.session_state.get("yx_nav_page") not in PAGES:
        st.session_state["yx_nav_page"] = "✨ 智能研究助手"
    selected_page = st.radio("功能导航", list(PAGES), key="yx_nav_page", label_visibility="collapsed")
    st.divider()
    if st.button("？ 查看使用教程", width="stretch"):
        st.session_state["yx_onboarding_complete"] = False
        st.rerun()
    git = project_data().git_state()
    st.caption(f"公测版本 · 本地运行\n\n代码 {git['branch']} · {git['commit']}")
    st.caption("科学边界：实验前计算证据整合与候选优先级辅助决策")

if not st.session_state.get("yx_onboarding_complete", False):
    onboarding_dialog()

PAGES[selected_page]()
st.markdown(
    '<div class="yx-footer">研序智航 · 小范围公测版　｜　所有评分均为计算决策证据，不代表实验活性或临床结论</div>',
    unsafe_allow_html=True,
)
