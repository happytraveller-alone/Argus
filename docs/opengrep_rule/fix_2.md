[
  {
    "ruleName": "opengrep-rules.internal.c.c_buffer_rule-sprintf-vsprintf",
    "severity": "ERROR",
    "hitCount": 210,
    "problem": "规则对 sprintf/vsprintf 进行一刀切高危判定，缺少目标缓冲区大小、剩余容量、格式串是否常量、输入是否可控、是否存在预先长度校验等上下文分析，且与另一条 sprintf/vsprintf 规则存在明显重复，导致误报和重复告警较多。样例中既有真实需关注的外部字符串拼接场景，也有像整数格式化这类低风险固定模板场景。",
    "codeExamples": [
      {
        "file": "vim-master/runtime/tools/xcmdsrv_client.c",
        "code": "sprintf(property, \"%c%c%c-n %s%c-s %s\", 0, asKeys ? 'k' : 'c', 0, name, 0, cmd);"
      },
      {
        "file": "vim-master/runtime/tools/xcmdsrv_client.c",
        "code": "sprintf(property + length, \"%c-r %x %d\", 0, (uint) commWindow, serial);"
      },
      {
        "file": "vim-master/src/autocmd.c",
        "code": "sprintf((char *)buflocal_pat, \"<buffer=%d>\", buflocal_nr);"
      }
    ],
    "suggestion": "修复方向：将规则从“API 出现即报 ERROR”调整为“基于上下文分级”的检测。1）优先识别高风险场景：向固定大小缓冲区写入且源数据可变、追加写入 offset 位置、调用 vsprintf、无任何容量校验。2）降低低风险场景：格式串为字面量、写入内容长度上界可静态推导、目标缓冲区容量可证明充足时降级为 medium/low 或不报。3）与 raptor-insecure-api-sprintf-vsprintf 去重：本规则聚焦缓冲区越界风险，另一条聚焦格式串风险。代码修改建议：a）将 sprintf/vsprintf 替换为 snprintf/vsnprintf，并显式传入 sizeof(buf) 或剩余容量；b）对追加写入改为 snprintf(property + length, total_size - length, ...)，并在写入前校验 length < total_size；c）对 xcmdsrv_client.c 中 name/cmd 拼接增加总长度计算与截断/失败处理；d）对 autocmd.c 这类固定格式整数输出，若缓冲区长度可证明足够，可保留但建议统一改为 vim_snprintf/snprintf 以降低治理噪音。",
    "priority": "high"
  },
  {
    "ruleName": "opengrep-rules.internal.c.raptor-insecure-api-sprintf-vsprintf",
    "severity": "ERROR",
    "hitCount": 106,
    "problem": "规则与 c_buffer_rule-sprintf-vsprintf 高度重叠，当前仅凭 sprintf/vsprintf 使用就报错，未区分缓冲区越界风险与格式串风险。样例中真正更高价值的是非字面量格式串场景，但规则没有突出这一点，导致语义模糊、重复告警和精度不足。",
    "codeExamples": [
      {
        "file": "vim-master/runtime/tools/xcmdsrv_client.c",
        "code": "sprintf(property, \"%c%c%c-n %s%c-s %s\", 0, asKeys ? 'k' : 'c', 0, name, 0, cmd);"
      },
      {
        "file": "vim-master/src/autocmd.c",
        "code": "sprintf((char *)namep, s, (char *)name, (char *)ap->pat);"
      },
      {
        "file": "vim-master/src/dosinst.c",
        "code": "sprintf(buf, \"%s\\\\filetype.vim\", installdir);"
      }
    ],
    "suggestion": "修复方向：将本规则重构为“格式串安全”专用规则，而不是重复做通用 sprintf 禁用。1）高优先命中：格式串参数不是字面量、来源可控、经过拼接/传递后进入 sprintf/vsprintf。2）中优先命中：vsprintf 无边界写入。3）低优先或转交另一规则：字面量格式串导致的普通长度问题。代码修改建议：a）对 autocmd.c 中 sprintf(namep, s, ...) 重点审查变量 s 的来源，若 s 可被外部输入影响，应改为固定格式模板或对白名单模板做枚举选择；b）对 dosinst.c 路径拼接改为 snprintf(buf, sizeof(buf), \"%s\\\\filetype.vim\", installdir) 并校验返回值；c）若项目已有封装函数，统一替换为带长度参数的安全格式化接口；d）规则层面与上一条去重：当格式串为字面量时由缓冲区规则处理，当格式串非常量时由本规则升级为 high-confidence 告警。",
    "priority": "high"
  },
  {
    "ruleName": "opengrep-rules.internal.c.c_buffer_rule-strcpy",
    "severity": "ERROR",
    "hitCount": 68,
    "problem": "规则把 strcpy 一律视为 ERROR，未结合目标缓冲区容量、源字符串长度上界、是否同尺寸数组、是否已有截断或校验逻辑，误报偏多。样例具备审计价值，但风险高低取决于数组大小关系和输入可控性。",
    "codeExamples": [
      {
        "file": "vim-master/runtime/tools/ccfilter.c",
        "code": "strcpy( Line, Line2 );"
      },
      {
        "file": "vim-master/src/dosinst.c",
        "code": "strcpy(tmpname, cp);"
      },
      {
        "file": "vim-master/src/dosinst.c",
        "code": "strcpy(default_bat_dir, targets[i].oldbat);"
      }
    ],
    "suggestion": "修复方向：规则应增加容量与数据流判断。1）高风险：源字符串来自外部输入或动态路径，目标缓冲区大小固定且无法证明足够。2）中风险：同模块内部缓冲区复制但大小关系未知。3）低风险：同尺寸数组间复制且前序已保证 NUL 终止与长度上界。代码修改建议：a）优先将 strcpy 替换为 snprintf(dst, sizeof(dst), \"%s\", src) 或项目内安全复制封装；b）若使用 strncpy/strlcpy，需确保手动 NUL 终止并检查截断；c）在 dosinst.c 中对 cp、targets[i].oldbat 先做长度校验，再写入 tmpname/default_bat_dir；d）在 ccfilter.c 中若 Line 与 Line2 为同尺寸数组，也建议改为 memmove/STRNCPY 这类带上界方式并显式限制拷贝长度。规则层面可对“目标为数组且可解析 sizeof”的情况进行更精细建模。",
    "priority": "medium"
  },
  {
    "ruleName": "opengrep-rules.internal.c.c_buffer_rule-strcat",
    "severity": "ERROR",
    "hitCount": 25,
    "problem": "规则仅凭 strcat 出现即报错，未判断目标剩余空间、追加内容长度、是否只追加固定短字面量、是否有前置长度管理，因此对补分隔符、补换行等场景误报明显。真正更值得关注的是向已有缓冲区追加未知长度字符串。",
    "codeExamples": [
      {
        "file": "vim-master/runtime/tools/ccfilter.c",
        "code": "strcat( Reason, \": \" );"
      },
      {
        "file": "vim-master/runtime/tools/ccfilter.c",
        "code": "strcat( Reason, p );"
      },
      {
        "file": "vim-master/runtime/tools/ccfilter.c",
        "code": "strcat( Line, \"\\n\" );"
      }
    ],
    "suggestion": "修复方向：将规则细化为基于“剩余容量 + 追加来源”的分级检测。1）高风险：追加内容为变量字符串、来源不可信、目标容量未知。2）中风险：目标为固定数组但当前长度接近上限。3）低风险：仅追加 1~2 字节固定字面量且可证明目标空间充足。代码修改建议：a）把 strcat(Reason, p) 改为 strncat/strlcat 或 snprintf(Reason + len, size - len, \"%s\", p)，并在追加前计算 len 与剩余容量；b）对 strcat(Reason, \": \")、strcat(Line, \"\\n\") 这类固定短追加也建议统一改成带剩余容量的追加接口，便于规范化治理；c）若项目允许，维护显式长度变量，避免反复扫描与盲目拼接。规则层面可对固定短字面量追加进行降级，聚焦未知长度追加。",
    "priority": "medium"
  },
  {
    "ruleName": "opengrep-rules.internal.c.c_buffer_rule-fscanf-sscanf",
    "severity": "ERROR",
    "hitCount": 13,
    "problem": "规则将 fscanf/sscanf 统一归为高危缓冲区问题，但真正风险取决于格式串中是否存在无宽度限制的 %s、%[^...]、%[...]，以及目标缓冲区大小与类型是否匹配。当前未解析格式串细节，容易把正常整数解析和已有限宽读取误报为 ERROR。",
    "codeExamples": [
      {
        "file": "vim-master/runtime/tools/ccfilter.c",
        "code": "rv = sscanf( Line, \"In file included from %[^:]:%lu:\", FileName, &Row );"
      },
      {
        "file": "vim-master/runtime/tools/ccfilter.c",
        "code": "if ((rv = sscanf( Line, \"%[^:]:%lu: warning: %[^\\n]\", FileName, &Row, Reason ))==3) {"
      },
      {
        "file": "vim-master/runtime/tools/ccfilter.c",
        "code": "rv = sscanf( Line, \"%[^:]:%lu: %[^\\n]\", FileName, &Row, Reason );"
      }
    ],
    "suggestion": "修复方向：将规则升级为“格式串语义分析”型检测。1）仅对无宽度限制写入字符数组的 %s/%[^...]/%[...] 报高危；2）对纯数字解析或已设置最大宽度的模式降级；3）结合目标数组声明大小，给出推荐宽度。代码修改建议：a）将 %[^:]、%[^\\n] 改为带宽度限制的形式，如 %255[^:]、%1023[^\\n]，宽度值应与 FileName、Reason 的数组长度一致并预留 NUL；b）优先采用 fgets 读取后再手动分割/解析，减少复杂 sscanf 模式带来的边界问题；c）校验 sscanf 返回值并处理解析失败分支，避免使用未初始化输出；d）若输入来自编译器输出等相对窄攻击面场景，可将严重度从 ERROR 下调至 MEDIUM，但对无宽度 scanset 仍应保留修复建议。",
    "priority": "medium"
  }
]