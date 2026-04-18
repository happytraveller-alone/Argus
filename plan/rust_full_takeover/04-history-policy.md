# History Policy

## 文档定位

- 类型：Explanation
- 目标读者：需要理解为什么这里不再维护历史流水账的开发者

## 当前约定

`rust_full_takeover/` 不再维护逐次 slice 进度日志。

原因：

- 历史日志会快速失真
- 旧计数和旧 blocker 很容易误导后续执行者
- 当前执行更需要“现状 + 下一步 + 验证门”，而不是时间线回顾

## 当前应该看什么

- 看当前剩余面：`03-current-state-and-ledger.md`
- 看下一步优先级：`07-next-targets.md`
- 看精确文件清单：`08-remaining-python-function-inventory.md`
- 看验证门：`05-validation-and-gates.md`

## 还保留什么原始材料

只保留会被当前工作引用的 raw evidence：

- [wait_correct/route-inventory/python-endpoints-summary.md](/home/xyf/audittool_personal/plan/wait_correct/route-inventory/python-endpoints-summary.md)
- [wait_correct/route-inventory/python-endpoints-inventory.csv](/home/xyf/audittool_personal/plan/wait_correct/route-inventory/python-endpoints-inventory.csv)
- [wait_correct/waves/wave-a-log.md](/home/xyf/audittool_personal/plan/wait_correct/waves/wave-a-log.md)

除此之外的历史性说明、旧计数和旧 ledger 已从本目录删除。
