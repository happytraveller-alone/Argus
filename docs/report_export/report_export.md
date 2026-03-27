# DeepAudit 漏洞报告导出架构分析

> 生成日期：2026-03-26

---

## 一、概述

DeepAudit 后端提供三种格式的漏洞审计报告导出：**PDF**、**Markdown**、**JSON**。报告内容由两个阶段产生：

1. **ReportAgent 阶段**（扫描期间）：为每条已验证漏洞生成 Markdown 格式的详情报告，并对整个项目生成风险评估报告，分别存储于数据库字段 `AgentFinding.report` 和 `AgentTask.report`。
2. **导出阶段**（按需请求）：用户调用导出 API，系统从数据库拉取数据，组装并转换为目标格式后以附件形式返回。

---

## 二、核心文件清单

| 文件路径 | 行数 | 职责 |
|---------|------|------|
| `app/api/v1/endpoints/agent_tasks_reporting.py` | 1200+ | 导出 API 路由；`_markdown_to_html`、`_render_markdown_to_pdf_bytes`、`_build_task_export_markdown`、`generate_audit_report` |
| `app/services/report_generator.py` | 507 | 基于 WeasyPrint + Jinja2 的 PDF 报告生成器（备用/独立路径） |
| `app/services/agent/agents/report.py` | 773 | `ReportAgent`：扫描期间调用，生成漏洞详情及项目级 Markdown 报告 |
| `app/services/agent/tools/reporting_tool.py` | 326 | `CreateVulnerabilityReportTool`：Agent 调用的漏洞记录工具 |
| `app/api/v1/endpoints/agent_tasks_findings.py` | 2000+ | `_build_structured_cn_description_markdown`、`_resolve_cwe_id`、`_resolve_vulnerability_profile` |
| `app/models/agent_task.py` | 650+ | `AgentTask`、`AgentFinding`、`AgentEvent` 数据模型 |
| `app/schemas/vulnerability_descriptor.py` | — | 漏洞描述构建工具函数（CWE、标题、中文描述） |
| `app/services/agent/utils/vulnerability_naming.py` | — | `normalize_cwe_id`、`resolve_vulnerability_profile` |

---

## 三、API 接口

### 3.1 任务报告导出

```
GET /api/v1/agent-tasks/{task_id}/report?format=pdf|markdown|json
```

| format | Content-Type | 文件名 |
|--------|-------------|--------|
| `pdf` | `application/pdf` | `audit_report_{task_id[:8]}_{YYYYMMDD}.pdf` |
| `markdown` | `text/markdown; charset=utf-8` | `audit_report_{task_id[:8]}_{YYYYMMDD}.md` |
| `json` | `application/json` | — |

### 3.2 单条漏洞报告导出

```
GET /api/v1/agent-tasks/{task_id}/findings/{finding_id}/report?format=markdown|json
```

---

## 四、支持的导出格式

### 4.1 PDF 格式

**实现链路：** Markdown → 自定义 HTML → WeasyPrint → PDF 字节流

核心函数（`agent_tasks_reporting.py`）：

- `_markdown_to_html(markdown_text: str) -> str`（行 248-346）
  - 自定义轻量 Markdown 解析器
  - 支持：标题（h1-h5）、代码块（\`\`\`）、行内代码、有序/无序列表、加粗、斜体、链接、分割线
  - 进行 HTML 转义，防止 XSS

- `_render_markdown_to_pdf_bytes(markdown_text: str) -> bytes`（行 349-385）
  - 将 HTML 包装为完整 A4 文档
  - 中文字体：Noto Sans CJK SC → PingFang SC → Microsoft YaHei
  - 页边距：上下 20mm，左右 15mm
  - 调用 `weasyprint.HTML(string=...).write_pdf()`

### 4.2 Markdown 格式

核心函数：`_build_task_export_markdown(task, findings, report_descriptions) -> str`（行 388-433）

**输出结构：**
```
# 安全审计报告 - {project_name}

**报告信息：**
- 任务 ID: {task_id}
- 生成时间: {timestamp}
- 扫描状态: {status}

{task.report}  ← 项目级风险评估报告（ReportAgent 生成）

---

## 漏洞详情

### 漏洞 1 / N: {title} [{severity}]
{finding.report}  ← 单条漏洞详情报告（ReportAgent 生成）
...
```

### 4.3 JSON 格式

**输出结构：**
```json
{
  "report_metadata": {
    "task_id": "...",
    "project_id": "...",
    "project_name": "...",
    "generated_at": "ISO-8601",
    "task_status": "completed",
    "duration_seconds": 1234
  },
  "summary": {
    "security_score": 85.5,
    "total_files_analyzed": 42,
    "total_findings": 12,
    "verified_findings": 10,
    "severity_distribution": {
      "critical": 1, "high": 3, "medium": 5, "low": 3
    },
    "agent_metrics": {
      "total_iterations": 50,
      "tool_calls": 245,
      "tokens_used": 52000
    }
  },
  "findings": [
    {
      "id": "...",
      "title": "...",
      "vulnerability_type": "...",
      "severity": "high",
      "cwe_id": "CWE-89",
      "file_path": "...",
      "line_start": 42,
      "line_end": 55,
      "is_verified": true,
      "verdict": "confirmed",
      "ai_confidence": 0.95,
      "description": "...",
      "code_snippet": "...",
      "dataflow_path": [...],
      "poc_code": "...",
      "suggestion": "..."
    }
  ]
}
```

---

## 五、完整数据流链路

```
╔══════════════════════════════════════════════════════════╗
║              扫描阶段（异步执行）                          ║
╠══════════════════════════════════════════════════════════╣
║                                                          ║
║  Agent 扫描代码                                          ║
║      │                                                   ║
║      ▼                                                   ║
║  CreateVulnerabilityReportTool._execute()                ║
║      │  记录漏洞 → 存入内存列表                           ║
║      ▼                                                   ║
║  验证逻辑（VerificationAgent）                           ║
║      │  AgentFinding.is_verified = True                  ║
║      ▼                                                   ║
║  ReportAgent.run()                                       ║
║      ├─ 读取代码上下文                                   ║
║      ├─ 追踪数据流                                       ║
║      ├─ 生成漏洞详情 Markdown                            ║
║      │   └─► 写入 AgentFinding.report（DB）              ║
║      └─ 生成项目级风险评估 Markdown                      ║
║          └─► 写入 AgentTask.report（DB）                 ║
║                                                          ║
╠══════════════════════════════════════════════════════════╣
║              导出阶段（按需请求）                          ║
╠══════════════════════════════════════════════════════════╣
║                                                          ║
║  GET /agent-tasks/{task_id}/report?format=xxx            ║
║      │                                                   ║
║      ▼                                                   ║
║  generate_audit_report(task_id, format)                  ║
║      │                                                   ║
║      ├─[1] 从 DB 加载 AgentTask + AgentFinding[]        ║
║      │                                                   ║
║      ├─[2] _build_report_descriptions()                  ║
║      │       ├─ _resolve_vulnerability_profile()         ║
║      │       ├─ _resolve_cwe_id()                        ║
║      │       └─ _build_structured_cn_description_md()    ║
║      │                                                   ║
║      ├─[3] 按 format 分支                               ║
║      │       │                                           ║
║      │       ├─ format="json"                            ║
║      │       │   └─► JSONResponse(dict)                  ║
║      │       │                                           ║
║      │       ├─ format="markdown"                        ║
║      │       │   └─ _build_task_export_markdown()        ║
║      │       │       └─► Response(text/markdown)         ║
║      │       │                                           ║
║      │       └─ format="pdf"                             ║
║      │           ├─ _build_task_export_markdown()        ║
║      │           ├─ _markdown_to_html()                  ║
║      │           ├─ 包装 A4 HTML（中文字体/样式）        ║
║      │           └─ weasyprint.HTML.write_pdf()          ║
║      │               └─► Response(application/pdf)       ║
║      │                                                   ║
║      └─[4] Content-Disposition: attachment 下载         ║
║                                                          ║
╚══════════════════════════════════════════════════════════╝
```

---

## 六、数据模型

### AgentTask（扫描任务）

```python
class AgentTask(Base):
    id                = Column(String, primary_key=True)  # UUID
    project_id        = Column(String, ForeignKey(...))
    status            = Column(String)           # pending/running/completed/failed
    report            = Column(Text)             # 项目级风险评估报告（Markdown）
    security_score    = Column(Float)            # 安全评分 0-100
    quality_score     = Column(Float)            # 代码质量评分
    analyzed_files    = Column(Integer)          # 扫描文件数
    total_iterations  = Column(Integer)          # Agent 迭代次数
    tool_calls_count  = Column(Integer)          # 工具调用次数
    tokens_used       = Column(Integer)          # 词元消耗量
    started_at        = Column(DateTime)
    completed_at      = Column(DateTime)
    findings          = relationship("AgentFinding", cascade="all, delete-orphan")
```

### AgentFinding（漏洞发现）

```python
class AgentFinding(Base):
    id                    = Column(String, primary_key=True)
    task_id               = Column(String, ForeignKey(...))
    # 基本信息
    vulnerability_type    = Column(String(100))  # SQL注入、XSS 等
    severity              = Column(String(20))   # critical/high/medium/low
    title                 = Column(Text)
    description           = Column(Text)
    # 位置信息
    file_path             = Column(Text)
    line_start            = Column(Integer)
    line_end              = Column(Integer)
    function_name         = Column(String(255))
    # 代码与污点分析
    code_snippet          = Column(Text)
    code_context          = Column(Text)
    source                = Column(Text)         # 污点源
    sink                  = Column(Text)         # 危险函数
    dataflow_path         = Column(JSON)         # 数据流路径
    # 验证结果
    is_verified           = Column(Boolean)
    verification_result   = Column(JSON)
    verdict               = Column(String(20))   # confirmed/likely/uncertain/false_positive
    ai_confidence         = Column(Float)
    confidence            = Column(Float)
    verification_evidence = Column(Text)
    # 报告与修复
    report                = Column(Text)         # 漏洞详情报告（Markdown，ReportAgent生成）
    has_poc               = Column(Boolean)
    poc_code              = Column(Text)
    poc_steps             = Column(JSON)         # 复现步骤列表
    suggestion            = Column(Text)         # 修复建议
    fix_code              = Column(Text)
```

---

## 七、关键函数说明

| 函数 | 文件 | 功能 |
|------|------|------|
| `generate_audit_report` | `agent_tasks_reporting.py:436` | 主入口，协调加载→构建→格式化→返回 |
| `_build_task_export_markdown` | `agent_tasks_reporting.py:388` | 组装完整 Markdown 报告文本 |
| `_markdown_to_html` | `agent_tasks_reporting.py:248` | 自定义 Markdown→HTML 解析 |
| `_render_markdown_to_pdf_bytes` | `agent_tasks_reporting.py:349` | HTML→PDF 字节流（WeasyPrint） |
| `_build_report_descriptions` | `agent_tasks_reporting.py` | 批量构建漏洞描述（CWE+中文） |
| `_build_structured_cn_description_markdown` | `agent_tasks_findings.py` | 生成结构化中文漏洞描述（Markdown） |
| `_resolve_cwe_id` | `agent_tasks_findings.py` | 从验证结果推断 CWE ID |
| `_resolve_vulnerability_profile` | `agent_tasks_findings.py` | 获取漏洞类型配置文件 |
| `ReportAgent.run` | `agents/report.py` | 生成漏洞详情及项目级 Markdown 报告 |
| `CreateVulnerabilityReportTool._execute` | `tools/reporting_tool.py` | Agent 工具：记录单条漏洞 |

---

## 八、第三方依赖

| 库 | 版本要求 | 用途 |
|----|---------|------|
| `weasyprint` | >=60.0 | HTML→PDF 转换，支持 CSS3、中文字体、分页 |
| `jinja2` | >=3.1.6 | HTML 模板渲染（`report_generator.py` 中使用） |
| `sqlalchemy` | — | ORM，数据库读取 AgentTask/AgentFinding |
| `fastapi` | — | API 路由与 Response 对象 |

---

## 九、ReportAgent 内部流程

ReportAgent（`app/services/agent/agents/report.py`）在扫描完成后对每条已验证漏洞独立运行：

```
输入：AgentFinding（已验证）+ 源码访问权限
    │
    ▼
1. 调用代码读取工具（ReadFileTool）获取完整上下文
    │
    ▼
2. 追踪数据流路径（source → sink）
    │
    ▼
3. 验证漏洞可利用性，生成 PoC 步骤
    │
    ▼
4. 调用 update_vulnerability_finding() 修正漏洞信息
    │
    ▼
5. 生成 Markdown 格式漏洞详情报告
    └─► 写入 AgentFinding.report

另外，在所有单条报告完成后：
PROJECT_REPORT_SYSTEM_PROMPT 驱动 Agent 生成项目级风险评估
    └─► 写入 AgentTask.report
```

报告内容结构（单条漏洞）：
- 漏洞概述（类型、严重程度、CWE、置信度）
- 漏洞位置（文件路径、行号、函数名）
- 漏洞原理与代码分析
- 数据流路径（污点源 → 危险函数）
- 复现步骤（PoC）
- 影响分析
- 修复建议与示例代码
