# API Contract Diff

这里存放 Python 和 Rust 的接口合同对比结果。

这是一个输出目录，不是 canonical 文档目录。
建议只保留实际生成出来的 diff 结果文件；固定模板文件已经移除。

- 输出文件命名：`api-contract-diff-<timestamp>.json|md`
- 默认只比对 inventory 中 `migrate` 桶
- 默认仅执行只读方法（GET/HEAD/OPTIONS）

建议每波迁移至少跑一次，并把差异结论回写到 `../waves/` 对应记录。
