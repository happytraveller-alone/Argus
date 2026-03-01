# Tool: `sandbox_http`

## Tool Purpose
在沙箱中发起 HTTP 请求，验证 Web 漏洞信号（如注入/XSS/SSRF）。

## Inputs
- `method` (string, optional): HTTP 方法，默认 `GET`
- `url` (string, required): 目标 URL
- `headers` (object, optional): 请求头
- `data` (string, optional): 请求体
- `timeout` (integer, optional): 超时秒数

### Example Input
```json
{
  "method": "POST",
  "url": "http://127.0.0.1:8080/search",
  "headers": {"Content-Type": "application/json"},
  "data": "{\"q\":\"' OR '1'='1\"}",
  "timeout": 20
}
```

## Outputs
- `success` / `error`
- `data`: 状态码与响应摘要
- `metadata`: `method`, `url`, `status_code`

## Typical Triggers
- 已有可访问服务，需要做请求级验证

## Pitfalls And Forbidden Use
- 若服务未启动，失败不代表漏洞不存在
- 避免对外部未授权目标发起测试
