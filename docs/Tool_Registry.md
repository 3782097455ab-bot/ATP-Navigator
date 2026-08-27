# Computational Tool Registry

更新时间：2026-08-28。来源：真实本机探测；最新摘要`results/system_capabilities.json`，不可变快照在`results/multibackend/`。

| tool_id | 版本来源 | 后端/任务 | 本机状态 |
|---|---|---|---|
| rdkit | 导入模块2026.03.5 | 结构QC、描述符、3D几何辅助 | available，已执行 |
| meeko | 模块0.7.1 | 配体PDBQT、已准备受体导入/受体转换接口 | available，已真实处理IN-2+17内部候选配体，并将历史pre-protonated 7P3W受体转换为PDBQT；不是重新执行Protein Preparation Wizard |
| vina | 实际--version：1.2.7 | 开源对接 | available；冻结`vina_7p3w_v1`在Phase 14.1最终1633/1633成功，1633 pose QC通过 |
| ligprep | 安装MacroModel14.4包 | 商业配体准备 | installed_but_license_unavailable |
| glide | 安装Glide10.3包 | HTVS/SP/XP输入合同 | installed_but_license_unavailable |
| prime_mmgbsa | 安装PSP7.6包 | 商业MM/GBSA | installed_but_license_unavailable |
| qikprop | 安装QikProp8.0包 | 商业性质预测 | installed_but_license_unavailable |
| gnina/openmm/gmx_mmpbsa/desmond | unknown | 预留adapter | configuration_error：未实现该执行adapter，不声称可运行 |

统一接口：detect、validate_environment、prepare_input、build_command、run、parse_output、register_evidence。工具记录包括ID/名称/版本/路径/许可/可用状态/backend/supported_tasks及可执行文件hash。不存在“LLM填一个Docking数值”的接口。

状态区分：not_found、installed、configuration_error、installed_but_license_unavailable、available。帮助能启动不等于签出成功；签出成功也不等于具体任务成功。Windows启动环境在子进程内修复，不改系统或许可证文件。

最终签出请求：Glide的GLIDE_MAIN/SP/XP，Prime的PSP_PLOP，QikProp的QIKPROP_MAIN，LigPrep的LIGPREP_MAIN。跟踪文件只存返回码、输出hash和特征名，不保存许可密钥或服务器地址。运行时若还需其他协议专用特征，必须真实报错，不模拟。

## Phase 14执行审计

- Vina executable SHA-256：`e0c4b2715e0c1a74f6e92d0f3be0328ac97542eafbc111e6b1efad897a73cce5`；
- receptor PDBQT SHA-256：`e5e92ede1b1d000b00a7e5dbe3f3b02f0df0cd63b47dd8a421eeb8bddb1083ed`；
- protocol file hash：`19ff755d00741e9d2ec60c732f24dea6a28fd4f478940b28dbc11bea68c3fe36`；Registry frozen protocol hash：`5b930c3ba77cbe9b622c4e285cab89f721bedf3693e1200e98d1a4e07dc4a403`；
- Phase 14主恢复阶段固定16并发；启动时1468个成功cache hit，只真实执行剩余165个；初始终态1628 success、5 failed；
- 5个失败stderr均为`Error: insufficient memory!`；Phase 14.1经授权后以2并发只重试这5个，5/5成功，最终1633 success、0 failed；
- 全过程未改变receptor、box、ligand preparation、exhaustiveness=16、num_modes=9、energy_range=3、seed=20260827或CPU/job=1。

安装与使用：`examples/setup_open_toolchain.py`从官方发行获取固定Vina版本，并把Meeko/gemmi/psutil放入`workspace_local/tool_deps`，没有改动原模型的Python包集合。商业产品由用户管理安装与许可；程序不调用安装介质中的补丁工具。

Phase 13许可证复检结果：Glide 10.3、Prime/PSP 7.6、QikProp 8.0、LigPrep 14.4均找到安装和可执行文件，但真实feature checkout返回失败，状态保持`installed_but_license_unavailable`，`commercial_full=blocked`。Vina 1.2.7真实执行了18个项目分子（17内部候选+IN-2参照），所有原生输出、stdout/stderr、工具/输入/pose hash均登记。
