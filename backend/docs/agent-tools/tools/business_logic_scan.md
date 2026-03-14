# BusinessLogicScanTool - 业务逻辑漏洞扫描工具

## 概述

**BusinessLogicScanTool** 是 DeepAudit 针对 **Web 应用**的业务逻辑漏洞发现工具。它通过 **5 步内部 LLM 协调分析**流程，自动识别常见的业务逻辑漏洞，包括：

- 🔓 **身份识别与授权 (IDOR/权限提升)**
  - 缺少或不完整的授权检查
  - 基于可预测 ID 的直接对象引用
  - 权限提升漏洞

- 🔄 **业务流程绕过**
  - 状态转换逻辑漏洞
  - 多步骤流程的跳过攻击
  - 条件验证被绕过

- 💰 **金融与账户操作**
  - 转账/支付逻辑漏洞
  - 余额检查绕过
  - 双花/重放攻击

- 📊 **业务数据操纵**
  - 数据一致性破坏
  - 竞态条件（Race Condition）
  - 不当的缓存处理

## 工作原理

### 5 步内部分析流程

1. **入口发现阶段**
   - LLM 识别应用的所有 Web 入口点（HTTP 端点、WebSocket、消息队列等）
   - 分类为管理员端、用户端、API 等
   - 输出：入口点列表

2. **功能分析阶段**
   - 深入每个入口点，理解其业务功能
   - 识别关键数据传输和流向
   - 输出：功能映射表

3. **敏感操作识别阶段**
   - 识别涉及金融、权限、数据修改等的敏感操作
   - 标记操作的风险等级
   - 输出：敏感操作清单

4. **污点分析阶段**
   - 从用户输入追踪到敏感操作
   - 检测是否有完整的验证逻辑
   - 输出：污点路径和漏洞位置

5. **漏洞确认阶段**
   - 综合前 4 步结果，确认实际的业务逻辑漏洞
   - 生成清晰的漏洞描述和复现步骤
   - 输出：最终漏洞发现

### 特点

✅ **内部 LLM 协调** - 5 个步骤无需 Analysis Agent 手动管理  
✅ **自动重试机制** - 每个阶段失败时最多重试 3 次  
✅ **上下文累积** - 每个阶段的输出成为后续阶段的输入  
✅ **Demo 模式** - 开发/测试时可生成示例漏洞而不需要真实的 LLM 调用  
✅ **框架无关** - 支持 Django、FastAPI、Express、Spring 等常见 Web 框架  

## 使用方法

### 在 Analysis Agent 中调用

当工具在 `analysis_tools` 字典中注册后（仅 Web 项目自动启用），Analysis Agent 可以这样调用：

```
Thought: 该项目是 Web 应用，包含 FastAPI 框架。我需要调用 business_logic_scan 来深度分析业务逻辑漏洞。

Action: business_logic_scan
Action Input: {
    "target": ".",
    "focus_areas": ["authentication", "authorization", "payment_processing"],
    "max_iterations": 5
}
```

### 输入参数

| 参数 | 类型 | 必需 | 说明 |
|------|------|------|------|
| `target` | string | ✓ | 扫描目标目录（通常为 `.` 表示项目根目录） |
| `focus_areas` | list | ✗ | 关注的业务逻辑区域，如 "authentication", "authorization", "payment", "account_management" 等 |
| `max_iterations` | int | ✗ | 内部 LLM 最大分析迭代数（默认 5） |
| `quick_mode` | bool | ✗ | 快速模式：只执行前 3 个步骤（默认 false） |
| `demo_results` | bool | ✗ | Demo 模式：生成示例漏洞用于测试（默认 false） |

### 返回格式

```json
{
  "success": true,
  "findings": [
    {
      "id": "BL-001",
      "title": "app/api/user.py中用户权限检查缺失的权限提升漏洞",
      "severity": "high",
      "vulnerability_type": "privilege_escalation",
      "description": "用户端点 `/api/users/{user_id}` 缺少对访问权限的检查，任何认证用户都可以修改其他用户的个人信息。",
      "file_path": "app/api/user.py",
      "function_name": "update_user",
      "line_start": 42,
      "line_end": 58,
      "code_snippet": "...",
      "confidence": 0.92,
      "taint_path": [
        {"stage": "entry", "detail": "用户 ID 来自 URL 路径参数"},
        {"stage": "operation", "detail": "直接查询数据库并更新"},
        {"stage": "missing_check", "detail": "缺少权限验证: if user_id != current_user.id"}
      ],
      "missing_checks": [
        "Authorization check for user_id",
        "Ownership verification"
      ],
      "suggestion": "在数据库操作前添加权限检查：验证当前用户是否可以修改目标用户信息。",
      "fix_description": "添加授权检查：if user_id != current_user.id: raise PermissionError()",
      "verification_evidence": "通过以下步骤可复现：1. 以用户 A 登录；2. 尝试修改用户 B 的信息（/api/users/B）；3. 观察是否成功修改",
      "poc_plan": "使用 curl 模拟不同用户修改彼此资料"
    }
  ],
  "summary": "分析了 8 个入口点，发现 3 个业务逻辑漏洞（2 个高危，1 个中危）",
  "analysis_details": {
    "entry_points_analyzed": 8,
    "sensitive_operations_identified": 12,
    "phase_results": {
      "entry_discovery": "✓ 发现 8 个入口点",
      "functional_analysis": "✓ 分析 12 个功能点",
      "sensitive_ops_identification": "✓ 识别 5 个敏感操作",
      "taint_analysis": "✓ 完成污点分析",
      "vulnerability_confirmation": "✓ 确认 3 个漏洞"
    }
  }
}
```

### 漏洞类型

支持的 `vulnerability_type` 包括：

- `idor` - 间接对象引用 (IDOR)
- `privilege_escalation` - 权限提升
- `business_logic_flaw` - 业务流程漏洞
- `account_takeover` - 账户接管
- `race_condition` - 竞态条件
- `authorization_bypass` - 授权绕过
- `payment_fraud` - 支付欺诈
- `data_manipulation` - 数据操纵

## 示例

### 示例 1：检测 IDOR 漏洞

```javascript
// 项目中的 Express 路由代码
app.get('/api/orders/:orderId', (req, res) => {
  // ❌ 缺少权限检查：任何认证用户都可以查看任何订单
  const order = db.getOrder(req.params.orderId);
  res.json(order);
});

// 工具会生成以下发现：
// {
//   "title": "routes/orders.js中order查询权限检查缺失的权限提升漏洞",
//   "severity": "high",
//   "vulnerability_type": "idor",
//   ...
// }
```

### 示例 2：检测支付流程绕过

```python
# Django 支付处理代码
def process_payment(request):
    amount = request.POST.get('amount')
    
    # ❌ 缺少金额验证：用户可以输入任意金额
    if amount > 0:  # 只检查大于 0，没有上限
        charge_card(request.user, amount)
        return "Payment successful"

# 工具会识别这个漏洞
```