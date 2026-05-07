# CubeSandbox Archive

归档原因: Argus (2026-05-07) 移除 cubesandbox 沙箱方案,扫描走 a3s sandbox。

归档主 commit: <Phase 14 后填写>
tag: `pre-cubesandbox-removal-2026-05-07` (LOCAL ONLY — 见 `.omc/plans/autopilot-impl.md` §17)

## 归档清单

(Phase 13 D1 完成后填写)

- cubesandbox-python-quickstart.md (origin: docs/cubesandbox-python-quickstart.md)
- oci-cubesandbox-README.md (origin: oci/cubesandbox/README.md)
- oci-cubesandbox-PATCHES.md (origin: oci/cubesandbox/PATCHES.md)
- README excerpt (cubesandbox section, see README.md history before 2026-05-07)

## Follow-ups (out of scope for this mission)

- F1: 为 a3s 实现 codeql 适配层 (`a3s_codeql_runner.rs`),恢复 codeql 功能
- F2: drop `rust_cubesandbox_*` 表(或运行 `scripts/purge-cubesandbox.sh --drop-tables`)
- F3: docker volume `backend_cubesandbox_data` 清理 RUNBOOK
- F4: AGENTS.md cubesandbox 知识压缩为 1 行 archive 链接

## 参考

- 规格: `.omc/autopilot/spec.md` (preserved at the same hash)
- 实施计划 v2: `.omc/plans/autopilot-impl.md`
