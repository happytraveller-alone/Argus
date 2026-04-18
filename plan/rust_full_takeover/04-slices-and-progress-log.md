# Slices And Progress Log

## 文档定位

- 类型：Explanation
- 目标读者：需要理解“为什么剩余面会收敛成现在这几个 cluster”的开发者

## 使用约定

这个文件不再记录逐次操作流水账。

它只保留仍会影响当前决策的里程碑摘要：

- 哪些大类已经确认退役
- 哪些“容易删”的历史壳层已经基本清空
- 为什么接下来的工作必须转向 live runtime cluster

详细逐条历史统一下沉到 archive 和 raw ledger。

## 仍然重要的里程碑

### 1. Package Shell 和 Namespace 清理基本完成

`app/__init__.py`、`core/__init__.py`、`models/__init__.py`、`llm/__init__.py`、
`llm/adapters/__init__.py` 以及多处 namespace shell 已退休。

含义：

- 低价值的 package shell 清理已经做过一轮
- 后续不应继续把主要精力放在“删壳”上

### 2. 规则与镜像类 Python shim 已明显收缩

`rule_contracts.py`、`git_mirror.py`、`package_source_selector.py`
等兼容层已经退役或被收口。

含义：

- Rust takeover 已经越过“只接 API 表面”的阶段
- 现在剩下的大头更偏 runtime 本体，而不是外围 shim

### 3. 非 opengrep 扫描引擎已按方向收口

`bandit`、`gitleaks`、`phpstan`、`pmd` 的 retained Python surface
已被逐步退役，扫描方向收口到 `opengrep-only`。

含义：

- 扫描域的 easy wins 基本吃完了
- 现在要面对的是 retained scanner 主链，而不是旧引擎残片

### 4. Dead Bootstrap Helper 已清掉一轮

`bootstrap_policy.py`、`bootstrap_entrypoints.py`、`bootstrap_seeds.py`、
`bootstrap_findings.py`、`bootstrap/base.py`、`bootstrap/opengrep.py`
等 dead helper 已退出主清单。

含义：

- scanner cluster 里只剩真正还承担行为的文件
- 下一步应直面 runner / queue / scope filter

### 5. Scanner Cluster 已被收缩到 4 个 live 文件

当前 retained scanner 主链已经压缩到：

- `recon_risk_queue.py`
- `vulnerability_queue.py`
- `scanner_runner.py`
- `scope_filters.py`

含义：

- 当前最值得优先拿下的 slice 已经非常明确
- 继续做零散清理的收益会快速下降

### 6. Business Logic Retained Runtime 已退出

orphaned Python business-logic runtime 已被 Rust-owned surface 接管并退役。

含义：

- “Rust 接管外层 surface，再删除 Python runtime”的做法已经验证可行
- 接下来可以把同样套路复制到 scanner / agent / flow / tool runtime

## 当前结论

这条迁移线已经跨过“历史壳层清理”阶段，正在进入真正的 retained runtime 拆除阶段。

后续 canonical 文档应该聚焦：

- 当前剩余功能面
- 当前执行顺序
- 当前验证门

而不是继续追加逐次 slice 过程记录。

## 历史明细入口

- [archive/legacy-ledgers/backend-old-python-ledger.md](/home/xyf/audittool_personal/plan/rust_full_takeover/archive/legacy-ledgers/backend-old-python-ledger.md)
- [wait_correct/waves/wave-a-log.md](/home/xyf/audittool_personal/plan/wait_correct/waves/wave-a-log.md)
