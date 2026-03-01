# Tool: `test_ssti`

## Tool Purpose
专门测试 SSTI（服务端模板注入）漏洞的工具，支持多种模板引擎。

## Inputs
- `target_file` (string, required): 目标文件路径
- `param_name` (string, optional): 注入参数名，默认 `"name"`
- `payload` (string, optional): SSTI payload，默认 `"{{7*7}}"`
  - Jinja2/Twig: `{{7*7}}`, `{{config}}`
  - Freemarker: `${7*7}`
  - Velocity: `#set($x=7*7)$x`
  - Smarty: `{7*7}`
- `template_engine` (string, optional): 模板引擎类型，默认 `"auto"`（支持 jinja2, twig, freemarker, velocity, smarty）

### Example Input
```json
{
  "target_file": "app/render.py",
  "param_name": "name",
  "payload": "{{7*7}}",
  "template_engine": "jinja2"
}
```

## Outputs
- `success` (bool): 执行是否成功
- `data` (string): 测试结果摘要（包含模板渲染输出）
- `metadata` (object):
  - `vulnerability_type`: `"ssti"`
  - `template_engine` (string): 检测到的模板引擎
  - `is_vulnerable` (bool): 是否确认漏洞
  - `evidence` (string|null): 漏洞证据（表达式计算结果、配置泄露等）
  - `poc` (string|null): PoC 命令

## Typical Triggers
- 分析阶段发现用户输入进入模板渲染
- 验证阶段需要确认 SSTI 是否可利用
- 检测模板表达式计算或配置访问

## Pitfalls And Forbidden Use
- 不要使用破坏性 payload（文件系统操作、反弹 shell 等）
- 数学表达式计算成功是 SSTI 的强信号
- 不同模板引擎语法不同，需要针对性 payload
- 某些模板引擎有沙箱保护机制
