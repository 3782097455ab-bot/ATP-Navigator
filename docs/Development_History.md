# Development History入口

项目的唯一完整开发记录维护在[ATP_Navigator_Development_History.md](ATP_Navigator_Development_History.md)。

2026-08-27的Multi-Backend Computational Workflow、Phase 13真实7P3W Vina验证以及2026-08-28 Phase 14全库证据层、失败审计和协议比较均记录在那里，避免维护两份互相矛盾的历史。
# 2026-08-28 — Phase 14.1

- 冻结`vina_7p3w_v1`不变，以2并发显式重试5个内存型技术失败，5/5成功；最终1633 success、0 failed、1633 pose QC pass；
- 新增Hit1–Hit17 + IN-2分层身份审计：Hit13 exact canonical，其余17个unresolved，不按名称或排名猜测；
- 未训练模型，未修改Model v0–v4-alpha，未产生实验标签。
