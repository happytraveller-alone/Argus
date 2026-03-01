# Tool: `test_xss`

## Tool Purpose
专门测试 XSS（跨站脚本）漏洞的工具，支持 Reflected、Stored、DOM XSS 检测。

## Inputs
- `target_file` (string, required): 目标文件路径
- `param_name` (string, optional): 注入参数名，默认 `"input"`
- `payload` (string, optional): XSS payload，默认 `"<script>alert('XSS')</script>"` 
  - Script 标签: `<script>alert('XSS')</script>`
  - 事件处理: `<img src=x onerror=alert('XSS')>`
  - SVG: `<svg onload=alert('XSS')>`
  - JavaScript 协议: `javascript:alert('XSS')`
- `xss_type` (string, optional): XSS 类型，默认 `"reflected"`（支持 reflected, stored, dom）
- `language` (string, optional): 语言类型，默认 `"auto"`

### Example Input
```json
{
  "target_file": "app/search.php",
  "param_name": "q",
  "payload": "<script>alert(1)</script>",
  "xss_type": "reflected"
}
```

## Outputs
- `success` (bool): 执行是否成功
- `data` (string): 测试结果摘要（包含 HTML 输出、payload 反射状态）
- `metadata` (object):
  - `vulnerability_type`: `"xss"`
  - `xss_type` (string): XSS 类型
  - `is_vulnerable` (bool): 是否确认漏洞
  - `evidence` (string|null): 漏洞证据（payload 被反射或编码情况）
  - `poc` (string|null): PoC 命令

## Typical Triggers
- 分析阶段发现用户输入直接输出到 HTML
- 验证阶段需要确认 XSS 是否可触发
- 检测输出编码/过滤机制是否有效

## Pitfalls And Forbidden Use
- payload 被 HTML 编码不一定代表完全防护（可能存在其他上下文注入）
- 不要使用破坏性或恶意 payload
- 注意检查不同输出上下文（HTML 标签、属性、JS 代码块）
- DOM XSS 可能需要浏览器环境才能完整验证
