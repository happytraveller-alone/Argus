# Skill: dynamic_verification

## 目标
- 在隔离沙箱中执行代码或系统指令，获取漏洞存在的确定性证据。
- 利用 Mock 技术绕过 IP 白名单、框架对象依赖等环境限制。


## 输入契约
- 基础字段: code (或 file_path), params (Dict), timeout。
- 特定字段: javascript_test: express_mode (bool), client_ip (string)。
- 特定字段: ruby_test: rails_mode (bool)。

## 推荐调用链
1. read_file 获取 Sink 点代码逻辑。
2. 根据语言选择对应的 *_test 工具（如 php_test, java_test）。
3. 构造 Mock 参数（如 client_ip 或 rails_mode）进行注入验证。
4. 分析 stdout 中的证据或 stderr 中的异常堆栈。
## 工具详解
1. 沙箱基础工具
- sandbox_exec: 执行系统命令（如 id），验证 RCE 漏洞。
- sandbox_http: 发起 HTTP 请求，验证 SSRF 或探测内网。
- verify_vulnerability: 自动化编排工具，整合路径与 Payload 输出最终报告。
2. 多语言测试工具 (*_test)
-  php_test: 模拟 $_GET/$_POST 全局变量 Mock。
-  javascript_test: 支持 express_mode 模拟 req/res，支持 client_ip 伪造。
-  java_test: 自动包装 main 并编译，预注入 Map<String, String> request。
-  go_test: 自动处理 Unused Imports，支持 os.Args 和环境变量注入。
-  ruby_test: 支持 rails_mode 和 Indifferent Access (符号与字符串键名通用)。
-  shell_test: 数字键名映射为位置参数 $1, $2，字符串键名映射为环境变量。
-  python_test: 验证 Python 代码注入，支持模拟 WSGI/Flask 上下文。
-  universal_code_test: 针对未分类语言的通用沙箱测试。

## 禁止用法
- 严禁在未尝试验证工具的情况下直接报告高危漏洞。
- 严禁在沙箱中执行破坏性指令（如 rm -rf /）。
- 不要跳过代码逻辑分析直接盲目猜测 Payload。

## 最小示例
```json
{
  "tool": "javascript_test",
  "action_input": {
    "code": "if(req.ip === '127.0.0.1') { exec(req.query.cmd); }",
    "params": {"cmd": "whoami"},
    "client_ip": "127.0.0.1",
    "express_mode": true
  }
}
```

## 失败恢复
- 逻辑对齐: 若执行报错，核对 Mock 对象属性（如 request.get）是否与代码实际调用的方法一致。
- 停止重试: 同一 Sink 点连续失败 2 次后必须调整 Payload 或重新评估代码环境。
- 降级方案: 若沙箱不可用，回退至 dataflow_analysis 进行纯静态逻辑验证。
