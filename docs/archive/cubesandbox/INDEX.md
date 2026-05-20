# CubeSandbox Archive

归档原因: Argus (2026-05-07) 移除 cubesandbox 沙箱方案,扫描走 a3s sandbox。

归档主 commit: 见 `git log --oneline --grep="cubesandbox"` 过滤结果
tag: `pre-cubesandbox-removal-2026-05-07` (LOCAL ONLY — 见 `.omc/plans/autopilot-impl.md` §17)

## 归档清单

Phase D1 (2026-05-07) 完成归档:

| 文件 | 原路径 |
|------|--------|
| `cubesandbox-python-quickstart.md` | `docs/cubesandbox-python-quickstart.md` |
| `oci-cubesandbox-README.md` | `oci/cubesandbox/README.md` |
| `oci-cubesandbox-PATCHES.md` | `oci/cubesandbox/PATCHES.md` |

同步删除（已归档，不再需要原始文件）:
- `oci/cubesandbox/codeql-cpp.Dockerfile`
- `oci/cubesandbox/opengrep.Dockerfile`

README 中 cubesandbox 段落已替换为归档指针（见 `README.md` / `README_EN.md` 2026-05-07 之后版本）。

## 移除阶段 commits

查看所有移除阶段提交:

```bash
git log --oneline --grep="cubesandbox"
```

主要阶段:
- B5.5+B6: drop cubesandbox runtime, state, bootstrap wiring
- B7: drop OciCubesandbox sandbox kind
- B8: drop cubesandbox db modules
- D1 (本次): archive docs, clean READMEs / AGENTS.md

## Follow-ups (out of scope for this mission)

- F1: 为 a3s 实现 codeql 适配层 (`a3s_codeql_runner.rs`),恢复 codeql 功能
- F2: drop legacy retired-sandbox tables manually if an old deployment still has them
- F3: legacy docker volume cleanup RUNBOOK for old deployments
- F4: AGENTS.md cubesandbox 知识压缩为 1 行 archive 链接

## 参考

- 规格: `.omc/autopilot/spec.md`
- 实施计划: `.omc/plans/autopilot-impl.md`
- AC6 验收条件: 见 spec §AC6 — oci/cubesandbox/ 清空, README 更新, AGENTS.md 注释
