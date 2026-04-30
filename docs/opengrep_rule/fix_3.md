[
  {
    "ruleName": "opengrep-rules.internal.cpp.c_format_rule-fprintf-vfprintf",
    "severity": "ERROR",
    "hitCount": 110,
    "problem": "规则将 fprintf/fwprintf/vfprintf 类调用近乎等同于漏洞，未判断格式串是否为编译期常量、是否存在用户可控输入直接作为格式串、是否只是测试/诊断输出，导致大量固定字符串日志被误报。当前命中样例均为 NativeTests 中的固定格式错误输出，不符合高危格式串漏洞特征。",
    "codeExamples": [
      {
        "file": "ChakraCore-master/bin/NativeTests/FileLoadHelpers.cpp:39",
        "code": "fwprintf(stderr, _u(\": %s\"), wszBuff);"
      },
      {
        "file": "ChakraCore-master/bin/NativeTests/FileLoadHelpers.cpp:41",
        "code": "fwprintf(stderr, _u(\"\\n\"));"
      },
      {
        "file": "ChakraCore-master/bin/NativeTests/FileLoadHelpers.cpp:63",
        "code": "fwprintf(stderr, _u(\"out of memory\"));"
      }
    ],
    "suggestion": "规则层面：1) 仅在“第一个格式参数非字面量/非常量传播值”时告警；2) 将严重度拆分为：非字面量格式串=high，常量格式串但参数来源不可信=info或不报；3) 增加测试目录、调试日志、stderr 固定诊断输出白名单或降级策略；4) 增加危险模式识别，如 fprintf(stderr, userInput)、fwprintf(f, buf) 这类直接把变量当格式串传入。代码层面：当前示例无需安全修复；若担心消息内容中含格式符，可统一改为显式常量格式串输出，例如保持 fwprintf(stderr, _u(\"%s\"), wszBuff) 这类写法，禁止 fwprintf(stderr, wszBuff)。",
    "priority": "high"
  },
  {
    "ruleName": "opengrep-rules.internal.cpp.c_format_rule-printf-vprintf",
    "severity": "ERROR",
    "hitCount": 87,
    "problem": "规则对 printf/wprintf/vprintf 使用进行机械匹配，未区分固定日志、断言输出与真实格式串注入场景，且未结合模块属性判断测试代码，导致 GCStress 中大量正常诊断输出被错误提升为 ERROR。",
    "codeExamples": [
      {
        "file": "ChakraCore-master/bin/GCStress/GCStress.cpp:17",
        "code": "wprintf(_u(\"==== FAILURE: '%S' evaluated to false. %S(%d)\\n\"), expr, file, line);"
      },
      {
        "file": "ChakraCore-master/bin/GCStress/GCStress.cpp:289",
        "code": "wprintf(_u(\"Recycler created, initializing heap...\\n\"));"
      },
      {
        "file": "ChakraCore-master/bin/GCStress/GCStress.cpp:323",
        "code": "wprintf(_u(\"Initialization complete\\n\"));"
      }
    ],
    "suggestion": "规则层面：1) 仅在 printf/wprintf 的格式串非字面量，或由外部输入/跨函数参数传播得到时告警；2) 对测试代码、断言框架、固定启动日志添加路径级抑制；3) 引入简单数据流，识别 user/argv/env/file/network 输入是否进入格式参数位置；4) 将当前 ERROR 下调，只有格式串可控时才保留高严重度。代码层面：当前样例可保持不变；若希望统一安全风格，可抽象为日志宏，强制格式参数为常量，例如 LOGW(_u(\"Initialization complete\\n\"))，并通过编译器属性或包装函数限制非常量格式串传入。",
    "priority": "high"
  },
  {
    "ruleName": "opengrep-rules.internal.cpp.c_format_rule-snprintf-vsnprintf",
    "severity": "ERROR",
    "hitCount": 15,
    "problem": "规则把 snprintf/vsnprintf 这类有界格式化函数的常规使用直接视为 ERROR，未区分安全用法与真实风险点。真正问题应聚焦于格式串可控、size 参数错误、返回值未检查、截断引发逻辑错误等，而非 API 本身。",
    "codeExamples": [
      {
        "file": "ChakraCore-master/lib/Runtime/PlatformAgnostic/Platform/Common/Trace.cpp:123",
        "code": "length = snprintf(TEMP, FILE_BUFFER_SIZE, format, data);"
      },
      {
        "file": "ChakraCore-master/pal/src/cruntime/printfcpp.cpp:1408",
        "code": "TempInt = snprintf(TempSprintfStr, TEMP_COUNT, TempBuff, trunc1);"
      },
      {
        "file": "ChakraCore-master/pal/src/cruntime/printfcpp.cpp:1423",
        "code": "snprintf(TempSprintfStr, TempInt, TempBuff, trunc2);"
      }
    ],
    "suggestion": "规则层面：1) 仅当格式串非字面量或来自不可信输入时告警；2) 增加 size 参数校验逻辑，如 size 来源是否可能大于目标缓冲区、是否为先前返回值且未经边界约束；3) 检查返回值处理，识别 length < 0、length >= buffer_size 未处理的情况；4) 对运行时库内部 printf 实现代码降级，因为其天然会处理动态格式模板。代码层面：Trace.cpp 中若 format 可能外部可控，应改为固定模板拼接或对 format 做受限枚举；同时检查 snprintf 返回值，例如 if (length < 0 || length >= FILE_BUFFER_SIZE) { /* 截断/错误处理 */ }。printfcpp.cpp 中二次 snprintf 使用 TempInt 作为 size 时，应确保 TempInt > 0 且不超过 TEMP_COUNT，必要时改为 min((size_t)TempInt, TEMP_COUNT)。",
    "priority": "high"
  },
  {
    "ruleName": "opengrep-rules.internal.c.c_format_rule-printf-vprintf",
    "severity": "ERROR",
    "hitCount": 12,
    "problem": "该规则与 C++ 版本问题相同，仅凭 printf/wprintf 出现就报错，缺乏对固定格式串、测试/调试代码、真实攻击面的识别，导致 GCStress 调试输出被误判。",
    "codeExamples": [
      {
        "file": "ChakraCore-master/bin/GCStress/RecyclerTestObject.h:45",
        "code": "wprintf(_u(\"-------------------------------------------\\n\"));"
      },
      {
        "file": "ChakraCore-master/bin/GCStress/RecyclerTestObject.h:46",
        "code": "wprintf(_u(\"Full heap walk starting. Current generation: %12llu\\n\"), (unsigned long long) currentGeneration);"
      },
      {
        "file": "ChakraCore-master/bin/GCStress/RecyclerTestObject.h:78",
        "code": "wprintf(_u(\"Full heap walk finished\\n\"));"
      }
    ],
    "suggestion": "规则层面：1) 与 C++ 规则统一收敛到“非字面量格式串”检测；2) 对 header 中内联调试输出、测试框架目录、GC 压测目录做降噪；3) 仅在格式参数来自变量且该变量可受外部输入影响时升级告警。代码层面：当前示例无需修改；可选地统一迁移到项目日志宏，借助包装接口限制格式串必须为常量，减少后续规则噪声。",
    "priority": "medium"
  },
  {
    "ruleName": "opengrep-rules.internal.cpp.c_race_rule-access",
    "severity": "ERROR",
    "hitCount": 12,
    "problem": "该规则方向基本正确，能捕获 access(F_OK) 之后再进行文件操作的潜在 TOCTOU 问题，但当前只看 access 调用本身，缺少与后续 open/create/rename/unlink/chmod 等敏感操作的控制流关联，可能把仅用于提示性检查的代码也报为 ERROR。",
    "codeExamples": [
      {
        "file": "ChakraCore-master/pal/src/file/pal_file.cpp:654",
        "code": "if ( access( lpUnixPath, F_OK ) == 0 )"
      },
      {
        "file": "ChakraCore-master/pal/src/file/pal_file.cpp:667",
        "code": "if ( access( lpUnixPath, F_OK ) == 0 )"
      },
      {
        "file": "ChakraCore-master/pal/src/file/pal_file.cpp:1455",
        "code": "if ( access(dest, F_OK) == 0 )"
      }
    ],
    "suggestion": "规则层面：1) 增加控制流/数据流关联，仅当 access 结果用于决定后续敏感文件操作时告警；2) 区分存在性检查后的操作类型：open(O_CREAT|O_EXCL)、rename、unlink、chmod、copy/move 等应重点关注；3) 若后续操作本身具备原子失败语义，则降级为 medium 或提示优化；4) 增加对安全替代模式的识别，如 open(..., O_CREAT|O_EXCL)、mkstemp、fstat 已打开文件句柄。代码层面：避免“先 access 再操作”，改为直接执行原子文件操作并根据 errno 判断结果。例如创建新文件时用 open(path, O_CREAT|O_EXCL, mode)；覆盖/替换时使用原子 rename 流程；需要校验对象属性时先 open 再 fstat 同一文件描述符，而不是先 access 后再 open。对 dest 存在性判断，如果只是为了避免覆盖，应让实际创建/重命名调用自己失败并处理 EEXIST。",
    "priority": "medium"
  }
]