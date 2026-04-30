[
  {
    "ruleName": "opengrep-rules.internal.c.c_format_rule-snprintf-vsnprintf",
    "severity": "ERROR",
    "hitCount": 25,
    "problem": "当前规则仅依据 snprintf/vsnprintf 函数名命中并统一按高危处理，误报较多。snprintf/vsnprintf 本身属于带长度限制的安全格式化接口，只有在格式串可控、size 计算错误、返回值未检查且截断会影响后续安全逻辑时，才具有较强漏洞意义。",
    "codeExamples": [
      {
        "file": "FFmpeg-master/fftools/ffmpeg.c:559",
        "code": "vsnprintf(buf, sizeof(buf), fmt, va);"
      },
      {
        "file": "FFmpeg-master/libavfilter/af_aspectralstats.c:189",
        "code": "snprintf(value, sizeof(value), fmt, val);"
      },
      {
        "file": "FFmpeg-master/libavfilter/af_astats.c:469",
        "code": "snprintf(value, sizeof(value), fmt, val);"
      }
    ],
    "suggestion": "规则修复方向：1）将该规则默认严重度从 ERROR 下调为 INFO 或 WARNING；2）增加前置条件，仅在 fmt 非字面量、可被外部输入污染、size 不是目标缓冲区真实大小、或返回值被忽略且结果继续用于认证/拼接/路径构造等场景时告警；3）排除 snprintf(buf, sizeof(buf), const_fmt, ...) 这类典型安全模式；4）增加返回值与截断检测逻辑，例如判断 ret < 0 或 ret >= sizeof(buf) 时再提升风险。代码层建议：对 vsnprintf/snprintf 调用补充返回值检查；对 fmt 来源做非常量格式串识别与污点分析；对安全样例建立白名单模式。示例修改：int n = vsnprintf(buf, sizeof(buf), fmt, va); if (n < 0 || n >= sizeof(buf)) { /* handle truncation/error */ }。",
    "priority": "low"
  },
  {
    "ruleName": "opengrep-rules.internal.c.c_buffer_rule-strcpy",
    "severity": "ERROR",
    "hitCount": 18,
    "problem": "当前规则对 strcpy 一刀切报 ERROR，虽然 strcpy 具有真实风险，但未区分短常量复制、已知容量缓冲区、可控输入复制等场景，导致误报与真实风险混杂。",
    "codeExamples": [
      {
        "file": "FFmpeg-master/fftools/cmdutils.c:965",
        "code": "strcpy(datadir + datadir_len, \"/ffpresets\");"
      },
      {
        "file": "FFmpeg-master/libavcodec/vaapi_encode.c:1247",
        "code": "strcpy(supported_rc_modes_string, \"unknown\");"
      },
      {
        "file": "FFmpeg-master/libavfilter/vf_drawtext.c:1878",
        "code": "strcpy(s->text, bbox->detect_label);"
      }
    ],
    "suggestion": "规则修复方向：1）将 strcpy 规则拆分为多类：源为外部可控字符串、源为编译期常量、目标为静态数组、目标为偏移写入/路径拼接；2）仅对目标容量不可证、源长度可变或受输入控制、以及路径/文本累积拼接场景维持较高告警；3）识别上文是否存在 malloc/av_malloc、sizeof、strlen 比较、剩余空间检查等边界证明；4）对 strcpy(dst, \"short-const\") 且 dst 为已知足够大数组场景降级为 INFO/WARNING 或过滤。代码层建议：优先替换为 av_strlcpy/strlcpy/snprintf/memcpy(带长度校验)；对 datadir + datadir_len 这类拼接改为 snprintf(datadir + datadir_len, remaining, \"/ffpresets\"); 或先校验剩余空间；对 s->text 复制外部标签前显式检查标签长度与缓冲区大小。示例修改：if (strlen(bbox->detect_label) < sizeof(s->text)) av_strlcpy(s->text, bbox->detect_label, sizeof(s->text)); else /* truncate or allocate dynamically */;",
    "priority": "high"
  },
  {
    "ruleName": "opengrep-rules.internal.c.c_buffer_rule-strcat",
    "severity": "ERROR",
    "hitCount": 4,
    "problem": "当前规则对 strcat 直接报 ERROR 有一定依据，但未结合剩余空间校验、目标容量、追加内容来源及是否为动态缓冲区，仍存在误报。相比 strcpy，该类调用在循环追加和多段拼接场景中更容易形成真实溢出。",
    "codeExamples": [
      {
        "file": "FFmpeg-master/libavfilter/vf_drawtext.c:1880",
        "code": "strcat(s->text, \", \");"
      },
      {
        "file": "FFmpeg-master/libavfilter/vf_drawtext.c:1881",
        "code": "strcat(s->text, bbox->classify_labels[j]);"
      },
      {
        "file": "FFmpeg-master/tools/pktdumper.c:111",
        "code": "strcat(fntemplate2, EXTRADATAFILESUFF);"
      }
    ],
    "suggestion": "规则修复方向：1）保留该规则较高关注度，但将判断增强为：仅在缺少容量证明、追加源可变、存在循环/多次累积拼接时提升为 ERROR；2）识别 strcat 前是否已有 strlen(dst)+strlen(src)<sizeof(dst) 或等价剩余空间检查；3）对追加固定短常量且目标容量静态可证的场景降级；4）识别动态扩容缓冲区或使用安全封装函数的情况避免误报。代码层建议：将 strcat 改为 av_strlcat/strlcat/snprintf；对 drawtext 的 s->text 采用剩余空间累计计算，避免多标签追加越界；若标签数量和长度不固定，改为动态分配缓冲区。示例修改：av_strlcpy(s->text, bbox->detect_label, sizeof(s->text)); av_strlcat(s->text, \", \", sizeof(s->text)); av_strlcat(s->text, bbox->classify_labels[j], sizeof(s->text)); 或使用 size_t used = strlen(s->text); snprintf(s->text + used, sizeof(s->text) - used, \"%s\", bbox->classify_labels[j]);",
    "priority": "high"
  },
  {
    "ruleName": "opengrep-rules.internal.c.c_format_rule-printf-vprintf",
    "severity": "ERROR",
    "hitCount": 4,
    "problem": "当前规则将 printf/vprintf 普遍视为高危不合理，真正风险集中在格式串是否非常量且可被外部输入控制。对编译期常量格式串直接告警会产生明显误报。",
    "codeExamples": [
      {
        "file": "FFmpeg-master/fftools/textformat/tw_stdout.c:58",
        "code": "vprintf(fmt, vl);"
      },
      {
        "file": "FFmpeg-master/tools/pktdumper.c:118",
        "code": "printf(EXTRADATAFILESUFF \"\\n\", i, par->extradata_size);"
      },
      {
        "file": "FFmpeg-master/tools/pktdumper.c:139",
        "code": "printf(PKTFILESUFF \"\\n\", pktnum, pkt->stream_index, pkt->pts, pkt->size, (pkt->flags & AV_PKT_FLAG_KEY) ? 'K' : '_');"
      }
    ],
    "suggestion": "规则修复方向：1）将规则收敛为‘格式串非字面量/非常量且来源不可信’时才告警；2）默认排除 printf(\"const\", ...) 这类常量格式串输出；3）对 vprintf(fmt, vl) 增加 fmt 来源追踪，若来自外部配置、命令行、网络、文件内容等则提升风险；4）将严重度从 ERROR 调整为按来源分级，常量格式串不报或降为 INFO。代码层建议：对需要转发外部文本时使用 printf(\"%s\", user_input) 而非 printf(user_input)；对 tw_stdout.c 中的 fmt 增加来源约束，确保上层只传入受控模板；扫描规则中加入 AST/污点分析判断首参是否字符串字面量。示例修改：若存在外部可控输出，替换为 fputs(user_input, stdout) 或 printf(\"%s\", user_input)。",
    "priority": "medium"
  },
  {
    "ruleName": "opengrep-rules.internal.c.c_buffer_rule-lstrcpy-wcscpy",
    "severity": "ERROR",
    "hitCount": 3,
    "problem": "当前规则对 wcscpy/lstrcpy 统一按高危处理，未区分复制固定短宽字符串常量与复制可变宽字符串输入的差异，误报较明显。真实风险仍取决于目标宽字符缓冲区大小和后续拼接行为。",
    "codeExamples": [
      {
        "file": "FFmpeg-master/libavdevice/dshow_pin.c:115",
        "code": "wcscpy(info->achName, L\"Capture\");"
      },
      {
        "file": "FFmpeg-master/libavutil/wchar_filename.h:216",
        "code": "wcscpy(temp_w, unc_prefix);"
      },
      {
        "file": "FFmpeg-master/libavutil/wchar_filename.h:225",
        "code": "wcscpy(temp_w, extended_path_prefix);"
      }
    ],
    "suggestion": "规则修复方向：1）参照 strcpy 规则进行细分，区分固定宽字符串常量复制、路径前缀复制、外部宽字符串复制；2）仅在目标容量不可证、源长度不受控、后续继续拼接且无边界检查时维持高优先级告警；3）对复制 L\"Capture\"、UNC 前缀、extended path 前缀等固定短常量场景降级或过滤；4）识别 Windows 结构体字段已知长度与 PATH 前缀固定长度的安全模式。代码层建议：使用 wcsncpy_s/StringCchCopyW/自定义带长度封装；在 temp_w 构造路径前先校验容量，再进行前缀复制和后续拼接；对已知字段长度场景显式添加长度常量，使规则可推断安全性。示例修改：StringCchCopyW(info->achName, ARRAYSIZE(info->achName), L\"Capture\"); 或 if (ARRAYSIZE(temp_w) > wcslen(unc_prefix)) wcscpy(temp_w, unc_prefix);",
    "priority": "medium"
  }
]