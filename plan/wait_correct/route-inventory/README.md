# Route Inventory

这里存放 Python API 的路由清单与分桶结果。

注意：这里是 raw inventory，不是当前 canonical 迁移主入口。
当前总计划请优先看 [plan/rust_full_takeover/README.md](/home/xyf/audittool_personal/plan/rust_full_takeover/README.md)。

- `python-endpoints-inventory.csv`：当前实盘清单（脚本生成）
- `python-endpoints-summary.md`：分桶统计和快速查看

分桶规则（当前已固化在脚本里）：

- `migrate`：`/projects/*`、`/system-config/*`、`/skills/*`、`/search/*`、`/static-tasks/*`、`/agent-tasks/*`
- `retire`：`/users/*`、`/projects/*/members*`、旧 `/config/*`
- `defer`：`/prompts/*`（其它低优先边界由人工补录）
- `proxy`：本波未迁移但仍需可用的接口

`retire` 只表示“计划上希望移除”，不自动等于“frontend / consumer 已清零”。

当前目录以脚本生成物为主，不再保留额外 template。
