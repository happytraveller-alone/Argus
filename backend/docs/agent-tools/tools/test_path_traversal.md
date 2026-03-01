# Tool: `test_path_traversal`

## Tool Purpose
专门测试路径遍历（Path Traversal / LFI / RFI）漏洞的工具。

## Inputs
- `target_file` (string, required): 目标文件路径
- `param_name` (string, optional): 文件参数名，默认 `"file"`
- `payload` (string, optional): 路径遍历 payload，默认 `"../../../etc/passwd"`
  - Unix: `../../../etc/passwd`
  - 编码绕过: `..%2f..%2f..%2fetc/passwd`
  - 双写绕过: `....//....//....//etc/passwd`
  - Windows: `..\\..\\..\\windows\\win.ini`
- `language` (string, optional): 语言类型，默认 `"auto"`

### Example Input
```json
{
  "target_file": "app/download.php",
  "param_name": "file",
  "payload": "../../../etc/passwd",
  "language": "php"
}
```

## Outputs
- `success` (bool): 执行是否成功
- `data` (string): 测试结果摘要（包含读取的文件内容片段）
- `metadata` (object):
  - `vulnerability_type`: `"path_traversal"`
  - `is_vulnerable` (bool): 是否确认漏洞
  - `evidence` (string|null): 漏洞证据（敏感文件内容特征）
  - `poc` (string|null): PoC 命令

## Typical Triggers
- 分析阶段发现文件读取/包含操作（file_get_contents, include, readFile 等）
- 验证阶段需要确认路径遍历漏洞
- 检测路径过滤/规范化机制是否有效

## Pitfalls And Forbidden Use
- 不要尝试读取会破坏系统的敏感文件
- payload 应针对测试环境调整（Unix vs Windows）
- 成功读取文件不一定意味着可以遍历到所有路径
- 注意路径前缀限制和 chroot 环境
