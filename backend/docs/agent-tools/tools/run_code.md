# Tool: `run_code`

## Tool Purpose
 通用代码执行工具 - 在沙箱中运行你编写的测试代码

这是你进行漏洞验证的核心工具。你可以：
1. 编写 Fuzzing Harness 隔离测试单个函数
2. 构造 mock 对象模拟数据库、HTTP 请求等依赖
3. 设计各种 payload 进行漏洞测试
4. 编写完整的 PoC 验证脚本

输入：
- code: 你编写的测试代码（完整可执行）
- language: python, php, javascript, ruby, go, java, bash
- timeout: 超时秒数（默认60，复杂测试可设更长）
- description: 简短描述代码目的

支持的语言和执行方式：
- python: python3 -c 'code'
- php: php -r 'code'  (注意：不需要 <?php 标签)
- javascript: node -e 'code'
- ruby: ruby -e 'code'
- go: go run (需写完整 package main)
- java: javac + java (需写完整 class)
- bash: bash -c 'code'

示例 - 命令注入 Fuzzing Harness:
```python
# 提取目标函数并构造测试
import os

# Mock os.system 来检测是否被调用
executed_commands = []
original_system = os.system
def mock_system(cmd):
    print(f"[DETECTED] os.system called: {cmd}")
    executed_commands.append(cmd)
    return 0
os.system = mock_system

# 目标函数（从项目代码复制）
def vulnerable_function(user_input):
    os.system(f"echo {user_input}")

# Fuzzing 测试
payloads = ["; id", "| whoami", "$(cat /etc/passwd)", "`id`"]
for payload in payloads:
    print(f"\nTesting payload: {payload}")
    executed_commands.clear()
    try:
        vulnerable_function(payload)
        if executed_commands:
            print(f"[VULN] Command injection detected!")
    except Exception as e:
        print(f"Error: {e}")
```

重要提示：
- 代码在 Docker 沙箱中执行，与真实环境隔离
- 你需要自己 mock 依赖（数据库、HTTP、文件系统等）
- 你需要自己设计 payload 和检测逻辑
- 你需要自己分析输出判断漏洞是否存在

## Goal
在 verification 阶段支撑审计编排和结果产出。

## Task List
- 协助 Agent 制定下一步行动。
- 沉淀中间结论与可追溯信息。
- 保障任务收敛与结果可交付性。


## Inputs
- `code` (string, required): 要执行的代码
- `language` (string, optional): 编程语言: python, php, javascript, ruby, go, java, bash
- `timeout` (integer, optional): 超时时间（秒），复杂测试可设置更长
- `description` (string, optional): 简短描述这段代码的目的（用于日志）


### Example Input
```json
{
  "code": "<text>",
  "language": "python",
  "timeout": 60
}
```

## Outputs
- `success` (bool): 执行是否成功。
- `data` (any): 工具主结果载荷。
- `error` (string|null): 失败时错误信息。
- `duration_ms` (int): 执行耗时（毫秒）。
- `metadata` (object): 补充上下文信息。

## Typical Triggers
- 当 Agent 需要完成“在 verification 阶段支撑审计编排和结果产出。”时触发。
- 常见阶段: `verification`。
- 分类: `报告与协作编排`。
- 可选工具: `否`。

## Pitfalls And Forbidden Use
- 不要在输入缺失关键参数时盲目调用。
- 不要将该工具输出直接当作最终结论，必须结合上下文复核。
- 不要在权限不足或路径不合法时重复重试同一输入。
