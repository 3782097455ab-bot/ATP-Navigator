# Phase 8 Maestro Structure Extraction Report

日期：2026-08-25  
状态：结构提取已运行；未训练或修改模型

## 结论

现有Schrödinger文件足以直接提取分子结构，不需要导师或队员重新提供SMILES。RDKit内置Maestro reader读取原子、键、形式电荷、立体信息和三维坐标；`.maegz`只在临时目录解压，原始文件保持只读。

## 全库结果

- Maestro源文件：3；
- Docking记录：4,373；
- 成功解析结构：4,372；失败：1；
- source/title/variant精确连接：4,372/4,373；
- compound级最佳pose结构：1,633；
- RDKit有效canonical SMILES：1,633；
- compound scaffolds：565；
- Phase 8 60候选SMILES：60/60；P0 SDF：24/24。

## 已知结构验证

- 可连接的内部Hit—HTVS桥：1；
- exact isomeric SMILES一致：1；
- connectivity一致：1。

已知桥目前只有Hit13/compound 91074，因此它能证明读取器在这一条上的一致性，但不能单独证明所有1,633条的人工化学正确性。全库仍使用RDKit sanitize、计数一致、唯一键和源文件hash进行程序化QC。

## 输出

- `data/htvs_structures_v0_1.csv`：1,633个compound最佳pose结构；
- `data/htvs_best_pose_structures_v0_1.sdf`：1,633个compound三维最佳pose；
- `results/phase8_data_acquisition/htvs_pose_structure_audit.csv`：4,373个pose结构连接审计；
- `results/phase8_data_acquisition/selected_structure_manifest_v0_1.csv`：60候选结构；
- `results/phase8_data_acquisition/selected_structures_v0_1.sdf`；
- `results/phase8_data_acquisition/p0_structures_v0_1.sdf`；
- `results/phase8_data_acquisition/known_structure_validation.csv`；
- `results/phase8_data_acquisition/maestro_source_audit.csv`。

## 边界

- canonical SMILES来自Maestro pose的RDKit解析，不是外部数据库重新检索；
- SDF保留Maestro三维构象，但尚未执行新的protein preparation或MM/GBSA；
- 提取成功不是活性验证，也不产生任何新标签；
- 结构可用后应另建v2 acquisition queue，用Morgan/scaffold替换原descriptor-only diversity臂，保留v1队列作审计对照。
