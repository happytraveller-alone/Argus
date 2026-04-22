# Skill: dynamic_verification

## 目标
- 在隔离沙箱中执行代码或系统指令，获取漏洞存在的确定性证据。
- 利用 Mock 技术绕过 IP 白名单、框架对象依赖等环境限制。


## 输入契约
- 基础字段: code (或 file_path), params (Dict), timeout。

## 推荐调用链
1. search_code / get_code_window 获取 Sink 点代码逻辑。
2. 使用 run_code 构造验证 Harness 进行注入验证。
3. 使用 sandbox_exec 执行系统命令验证 RCE。
4. 分析 stdout 中的证据或 stderr 中的异常堆栈。
## 工具详解
1. 沙箱基础工具
- sandbox_exec: 执行系统命令（如 id），验证 RCE 漏洞。
- verify_vulnerability: 自动化编排工具，整合路径与 Payload 输出最终报告。
2. 代码运行工具
- run_code: 运行验证 Harness/PoC，收集动态执行证据。

## 禁止用法
- 严禁在未尝试验证工具的情况下直接报告高危漏洞。
- 严禁在沙箱中执行破坏性指令（如 rm -rf /）。
- 不要跳过代码逻辑分析直接盲目猜测 Payload。

## 最小示例
```json
{
  "tool": "run_code",
  "action_input": {
    "language": "python",
    "code": "import subprocess; result = subprocess.run(['id'], capture_output=True, text=True); print(result.stdout)"
  }
}
```

## 失败恢复
- 逻辑对齐: 若执行报错，核对 Mock 对象属性（如 request.get）是否与代码实际调用的方法一致。
- 停止重试: 同一 Sink 点连续失败 2 次后必须调整 Payload 或重新评估代码环境。
- 降级方案: 若沙箱不可用，回退至 dataflow_analysis 进行纯静态逻辑验证。
