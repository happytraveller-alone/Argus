# Route Inventory

这里存放 Python API 的路由清单与分桶结果。

- `python-endpoints-inventory.csv`：当前实盘清单（脚本生成）
- `python-endpoints-summary.md`：分桶统计和快速查看
- `route-inventory-template.csv`：手工补录模板（如需）

分桶规则（当前已固化在脚本里）：

- `migrate`：`/projects/*`、`/system-config/*`、`/skills/*`、`/search/*`、`/static-tasks/*`、`/agent-tasks/*`
- `retire`：`/users/*`、`/projects/*/members*`、旧 `/config/*`
- `defer`：`/prompts/*`（其它低优先边界由人工补录）
- `proxy`：本波未迁移但仍需可用的接口
