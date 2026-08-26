# Phase 11：研究会话工作区与实验反馈接口

日期：2026-08-26。定位：虚拟筛选后 AI 辅助候选优先级决策。

## 现在能做什么

会话不再只给建议：它保存输入快照、历史消息、确认提案和真实运行产物。排序仍调用冻结的 Model v3/明确标注的 v2-A fallback 和原有决策权重。研究目标通过四个已定义 profile 明确选择，不暗中推断或改权重。

```text
研究会话 → 明确任务/选择模式 → 用户确认 → 专业工具执行
                  ↑                         ↓
              继续追问 ← 排名/解释/来源/运行记录

真实实验或计算回填 → 校验/隔离 → 具名人工审查 → 独立任务数据版本
                                              ↓
                          冻结排名与同类测量比较 → 下一轮设计审查
                                              ↓
                    显式授权训练 + 独立验证 + 人工发布（本轮未执行）
```

## 使用入口

在项目目录、已有 Python 环境中运行：

```powershell
python src/research_workspace.py --input results/demo/demo_input.csv --interactive
```

可输入：

- `状态`
- `按 atp_mechanism_focused 排序`（也支持 balanced、binding_focused、experimental_validation_focused）
- 按显示的提案编号输入 `确认 proposal-...`
- `解释 Hit3`
- `比较模式`
- `查资料 ATP`
- `查资料 abaucin`
- `准备迭代`
- `评价反馈`

退出后用 `--session session-... --interactive` 恢复同一任务。新文件需要建立新会话，避免悄悄改变已分析批次。

会话数据库和运行产物在 `workspace_local/`，默认不进入 Git。每次执行产生新目录，不覆盖旧模型、旧结果。SQLite事务序列化本地动作；当前不是带账户、身份认证、多人权限和崩溃任务恢复的服务。异常动作记录失败，不自动重试。

## 聊天能力的真实边界

离线模式是有限命令解释器，不是通用大语言模型。对含糊指令会要求明确任务，不把关键词命中伪装成理解科研意图。

`src/workspace_llm_adapter.py` 提供可选 Responses API 工具路由。它只提出白名单动作；确认仍由本地用户完成，不允许训练、执行任意代码或批准实验数据。配置需在 Git 外设置 `OPENAI_API_KEY`、`ATP_NAVIGATOR_CHAT_MODEL`，并显式选择 `--provider openai --allow-external-text`。不要把密钥提交到仓库。

当前没有配置 API key，未进行真实 API 联调。仅测试了路由输出的解析及越权拦截。默认无外发；启用后发送当前和最近用户文本，不读取或发送候选文件、实验表、工具结果正文。用户在消息中直接输入的敏感内容仍可能外发，因此需要授权。当前接入口用于意图路由，不声称具备开放式论文推理或聊天模型生成的科研回答。

交互设计依据 [Function calling](https://developers.openai.com/api/docs/guides/function-calling) 和 [Conversation state](https://developers.openai.com/api/docs/guides/conversation-state)：对话状态与实际工具执行分开保存；本地程序验证参数并执行动作。这里采用本地持久记录，未复制 ChatGPT/Codex 的完整产品能力。

## 实验回填：具体操作

1. 复制 `data/templates/phase11_feedback_template.csv` 到 `data/experimental/incoming/`。模板只有17个已知身份，所有实验结果留空。
2. 添加真实原始测量文件，填写 `evidence_file`（项目相对路径）和 `evidence_sha256`。来源文件必须位于实验或外部 incoming 目录。
3. 在会话中输入 `/validate data/experimental/incoming/your_results.csv`。查看隔离原因。
4. `/import data/experimental/incoming/your_results.csv`，确认后保存原始文件快照、证据文件和校验结果。
5. 具名人工审查，只有明确认可的 record_id 入库：

```powershell
python src/experimental_feedback.py review --batch-id feedback-... --reviewer researcher_name --accept record_1 record_2
```

6. 会话输入 `准备迭代`并确认，产生独立快照；随后 `评价反馈`，与本会话冻结排名进行端点分层的描述性比较。

机器校验只证明格式、身份和文件一致性，不能证明实验真实完成。具名审查是人员声明，不是电子签名认证。修改已审查数据必须重新导入，不能覆盖原版本。

## 字段约定

| 字段组 | 必须保留的信息 |
|---|---|
| 身份 | record_id、compound_id、canonical_smiles；已登记内部ID必须结构相符 |
| 实验对象 | organism、strain、target |
| 测量 | activity_type、activity_value、comparator、unit、assay_mode |
| 可比条件 | assay_protocol_id、replicate_id；实际浓度/时间/培养条件应由协议及证据文件明确描述 |
| 来源 | reference、evidence_file、evidence_sha256、operator、experimental_date、qc_status |
| 分层 | evidence_type、dataset_role（development / holdout / benchmark） |

端点分为 MIC→Task A、ATP_IC50→Task B、MMGBSA→Task C、CC50→细胞毒性辅助任务。MMGBSA必须标为computational；其他端点必须标为experimental。支持 ng/mL、ug/mL、mg/mL、nM、uM、mM；MMGBSA仅kcal/mol。这里不自动换算单位，不将不同模式、物种、菌株、方案的测量拼成一个标签。

`<`/`>`等删失测量保留原值与比较符，不进入精确标签训练视图。重复来源导入不增加独立样本；冲突记录隔离。相同canonical结构若出现在holdout/benchmark，development副本不能用于训练。更多盐形式/互变异构体、scaffold层面的拆分仍需训练设计阶段补充。

## 回流后的评价与升级

`feedback_evaluator.py`只比较同一stratum内已审查的精确holdout/benchmark测量。重复测量以同结构、同协议中位数汇总；至少5个可比较结构且非常数才报告描述性Spearman。该门槛不代表统计充分性。排序与活性单位不同，因此不输出伪造的RMSE。

当前比较为回顾性一致性，不自动具备前瞻性资格。真正前瞻验证还需在测量前冻结候选集合、选择策略、预算和结局定义。当前没有自动重训/发布：新版本必须经过明确授权、独立验证和人工批准。已审查反馈会在会话的候选解释中单独展示，不改变现有评分公式。

## 本轮验证

- Phase10与Phase11回归测试当前28项通过，包括：跨进程确定性、重复结构不影响其他候选、特征覆盖保护、数据回填隔离、删失值、来源篡改、任务与holdout隔离、确认只执行一次、会话恢复。机器可读记录见`results/phase11_validation.json`。
- 17/17候选完成冻结v3预测和决策；24个模型目录文件运行前后hash一致。
- 真实实验回填0条；真实反馈评价状态`empty_no_matched_reviewed_holdout`。
- 非空反馈分支只在临时的明确标注测试夹具上测试，数据不进入科研库、报告指标或演示成果。
- 首次测试发现Windows SQLite连接未关闭和abaucin别名漏检，均已修复并重测。最初演示目录保留，最终演示是 `results/phase11_workspace_demo_v1_1/`。

以上通过的是软件流程测试，不是药效、实验命中率或节省成本的验证。
