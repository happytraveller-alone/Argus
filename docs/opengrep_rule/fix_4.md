[
  {
    "ruleName": "opengrep-rules.internal.python.subprocess-shell-true",
    "severity": "ERROR",
    "hitCount": 45,
    "problem": "规则仅以 shell=True 作为命中条件，未判断命令是否来自外部可控输入、是否仅用于内部工具/测试脚本、是否可安全改写为参数数组，导致在 tools/fuzzer/test 场景中产生大量高误报；同时缺少 CWE、说明和分级策略。",
    "codeExamples": [
      {
        "file": "v8-main/tools/android-run.py",
        "code": "process = subprocess.Popen(\n  args=cmdline,\n  shell=True,\n  stdout=fd_out,\n  stderr=fd_err,\n)"
      },
      {
        "file": "v8-main/tools/bigint-tester.py",
        "code": "return subprocess.call(\"%s %s\" % (binary, path),\n                       shell=True)"
      },
      {
        "file": "v8-main/tools/clusterfuzz/js_fuzzer/tools/run_one.py",
        "code": "output = subprocess.check_output(cmd, stderr=subprocess.PIPE, shell=True)"
      }
    ],
    "suggestion": "修复方向：1）将该规则从“仅语法命中”升级为“上下文敏感”规则，优先检测 shell=True 且命令字符串包含外部输入、字符串拼接、format/f-string、join、环境变量、命令行参数、文件内容或网络输入；2）补充 CWE-78、规则说明、风险条件、豁免条件；3）对 tools/test/fuzzer/dev 目录默认降级为 warning 或 needs-review；4）若命令为常量列表或受控白名单命令则不报或降级；5）支持识别可替代写法 subprocess.run([...], shell=False)。代码层面建议：a）优先改为参数数组调用，例如 subprocess.run([binary, path], check=False)；b）如必须使用 shell，则对命令来源做白名单约束并使用 shlex.quote 包裹动态参数；c）android-run.py 若 cmdline 为字符串，建议拆分为 argv 列表并设置 shell=False；d）run_one.py 若 cmd 为受控命令模板，改为显式参数列表并单独传递 stderr/stdout。",
    "priority": "high"
  },
  {
    "ruleName": "opengrep-rules.internal.python.python_exec_rule-subprocess-popen-shell-true",
    "severity": "ERROR",
    "hitCount": 28,
    "problem": "规则名称指向 popen-shell-true，但实际命中 subprocess.call 和 subprocess.check_output，名称与检测范围不一致；与通用 shell=True 规则及 _1 规则高度重复，造成重复告警和治理噪音；缺少风险分级与上下文判断。",
    "codeExamples": [
      {
        "file": "v8-main/tools/bigint-tester.py",
        "code": "return subprocess.call(\"%s %s\" % (binary, path),\n                       shell=True)"
      },
      {
        "file": "v8-main/tools/clusterfuzz/js_fuzzer/tools/run_one.py",
        "code": "output = subprocess.check_output(cmd, stderr=subprocess.PIPE, shell=True)"
      },
      {
        "file": "v8-main/tools/dev/gen-tags.py",
        "code": "return subprocess.call(cmd, shell=True)"
      }
    ],
    "suggestion": "修复方向：1）重命名规则，使名称准确覆盖 subprocess.call/check_output/run/Popen 等 shell=True 场景，例如 python-subprocess-shell-true-generic；2）与 opengrep-rules.internal.python.subprocess-shell-true 合并或建立主从关系，避免重复命中；3）增加仅在命令参数存在外部输入传播时提升为高危，否则降级为中低危审计；4）增加目录/文件类型例外策略，对开发辅助脚本默认降级。代码层面建议：a）bigint-tester.py 改为 subprocess.call([binary, path], shell=False)；b）gen-tags.py 若 cmd 为标签工具加参数，建议构造成列表如 [\"ctags\", \"-R\", path]；c）run_one.py 如需采集输出，改为 subprocess.check_output([prog, arg1, arg2], stderr=subprocess.PIPE, shell=False)。",
    "priority": "high"
  },
  {
    "ruleName": "opengrep-rules.internal.python.python_exec_rule-subprocess-popen-shell-true_1",
    "severity": "ERROR",
    "hitCount": 28,
    "problem": "该规则与 python_exec_rule-subprocess-popen-shell-true 基本重复，命中样例和风险语义高度一致，疑似重复建规则或规则生成异常；同时名称仍与实际命中 API 不匹配，放大告警噪音。",
    "codeExamples": [
      {
        "file": "v8-main/tools/bigint-tester.py",
        "code": "return subprocess.call(\"%s %s\" % (binary, path),\n                       shell=True)"
      },
      {
        "file": "v8-main/tools/clusterfuzz/js_fuzzer/tools/run_one.py",
        "code": "output = subprocess.check_output(cmd, stderr=subprocess.PIPE, shell=True)"
      },
      {
        "file": "v8-main/tools/dev/gen-tags.py",
        "code": "return subprocess.call(cmd, shell=True)"
      }
    ],
    "suggestion": "修复方向：1）直接删除该重复规则，或并入上一条统一规则；2）建立规则唯一性校验，避免同一 pattern 以不同 ID 重复发布；3）统一命名、说明、CWE 与严重度策略；4）若保留子规则，应明确边界，例如仅检测 Popen，且必须与名称一致。代码层面建议：本规则对应代码修改与上一条一致，核心是将字符串命令改为参数列表、默认 shell=False，并仅在无法避免 shell 时加入严格白名单和参数转义。",
    "priority": "high"
  },
  {
    "ruleName": "opengrep-rules.internal.python.open-never-closed",
    "severity": "ERROR",
    "hitCount": 17,
    "problem": "规则仅依据出现 open/io.open 就推断“未关闭”，缺少作用域、控制流和资源闭合分析，无法识别 with 语句、后续 close()、短生命周期脚本等情形；当前更像质量/可靠性检查而非高危安全漏洞。",
    "codeExamples": [
      {
        "file": "v8-main/third_party/inspector_protocol/concatenate_protocols.py",
        "code": "input_file = open(file_name, \"r\")"
      },
      {
        "file": "v8-main/tools/gen-postmortem-metadata.py",
        "code": "objfile = io.open(objfilename, 'r', encoding='utf-8');"
      },
      {
        "file": "v8-main/tools/gen-postmortem-metadata.py",
        "code": "inlfile = io.open(filename, 'r', encoding='utf-8');"
      }
    ],
    "suggestion": "修复方向：1）将规则改为资源管理规则而非安全高危规则，严重度建议降为 low/medium；2）增加闭合分析，仅在 open 返回对象逃逸、循环中反复打开、长生命周期进程中未进入 with/未 close 时告警；3）识别 with open(...) as f、try/finally close、上下文管理器封装等安全模式；4）补充规则说明，强调这是资源泄漏/可维护性问题。代码层面建议：a）统一改写为 with open(file_name, \"r\") as input_file:；b）io.open 同样使用 with io.open(..., encoding='utf-8') as objfile:；c）若需跨函数传递文件对象，则明确由调用方负责关闭，并在规则中加入例外。",
    "priority": "medium"
  },
  {
    "ruleName": "opengrep-rules.internal.cpp.c_format_rule-fprintf-vfprintf",
    "severity": "ERROR",
    "hitCount": 13,
    "problem": "规则将 fprintf/vfprintf 本身视为高危，而未判断 format 是否为外部可控、是否为常量、是否位于日志封装函数内部，因此在平台层日志代码中误报明显；缺少对格式化字符串漏洞核心条件的刻画。",
    "codeExamples": [
      {
        "file": "v8-main/src/base/platform/platform-posix.cc",
        "code": "vfprintf(out, format, args);"
      },
      {
        "file": "v8-main/src/base/platform/platform-posix.cc",
        "code": "vfprintf(stderr, format, args);"
      },
      {
        "file": "v8-main/src/base/platform/platform-win32.cc",
        "code": "vfprintf(stream, format, args);"
      }
    ],
    "suggestion": "修复方向：1）将规则从“命中敏感 API”改为“检测不可信格式串流入 printf 家族第一个格式参数”；2）对字面量 format、编译期常量、内部日志封装默认不报或降级；3）增加数据流分析，重点识别用户输入、网络输入、环境变量、argv、文件内容进入 format 参数的路径；4）补充 CWE-134、示例、修复建议。代码层面建议：a）若 format 可能来自外部输入，改为固定格式串，例如 fprintf(stream, \"%s\", user_input)；b）日志封装函数可增加 format 常量约束或使用更安全的格式化接口；c）对于当前 platform-posix.cc/platform-win32.cc 这类封装代码，若上层已保证 format 为受控值，可在规则中加入白名单或基于函数名/目录降级。",
    "priority": "medium"
  }
]