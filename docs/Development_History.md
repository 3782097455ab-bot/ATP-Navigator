# Development History入口

项目的唯一完整开发记录维护在[ATP_Navigator_Development_History.md](ATP_Navigator_Development_History.md)。

2026-08-27的Multi-Backend Computational Workflow、Phase 13真实7P3W Vina验证以及2026-08-28 Phase 14全库证据层、失败审计和协议比较均记录在那里，避免维护两份互相矛盾的历史。
# 2026-08-28 — Phase 16

- 新增统一Generator API与Generated Candidate Registry；
- RDKit围绕IN-2/Hit3生成400 raw、400 valid、360 unique；Hit3 HTVS identity保持unresolved；
- 120个cheap-screened候选在冻结`vina_7p3w_v1`下真实执行成功，形成30候选generated acquisition panel；
- CReM、REINVENT4、AiZynthFinder unavailable且0模拟结果；未训练或修改历史模型。

# 2026-08-28 — Phase 15

- 基于1633个Glide/Vina matched candidates建立预算感知Evidence Acquisition Engine；
- 分离protocol/model/objective/evidence/chemical-space五类不确定性，model uncertainty不可用时保持NaN；
- 生成60候选六类面板、十种策略和budget 10/20/40/60/100模拟；
- GNINA unavailable，不生成伪score；未训练或修改历史模型。

# 2026-08-28 — Phase 14.1

- 冻结`vina_7p3w_v1`不变，以2并发显式重试5个内存型技术失败，5/5成功；最终1633 success、0 failed、1633 pose QC pass；
- 新增Hit1–Hit17 + IN-2分层身份审计：Hit13 exact canonical，其余17个unresolved，不按名称或排名猜测；
- 未训练模型，未修改Model v0–v4-alpha，未产生实验标签。
