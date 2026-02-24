import { useEffect, useMemo, useState } from "react";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { api } from "@/shared/api/database";
import { SKILL_TOOLS_CATALOG, SKILL_TOOL_CATEGORY_ORDER, type SkillToolCategory, buildSkillToolPrompt } from "./skillToolsCatalog";
import {
  DEFAULT_MCP_CATALOG,
  normalizeMcpCatalog,
  type McpCatalogItem,
} from "./mcpCatalog";

const CATEGORY_DESC: Partial<Record<SkillToolCategory, string>> = {
  "代码读取与定位": "用于读取代码、检索关键位置、提取函数上下文，形成后续分析证据链起点。",
  "候选发现与模式扫描": "用于快速拉取候选风险点，缩小审计范围并为验证阶段提供高优先级线索。",
  "可达性与逻辑分析": "用于验证漏洞链路是否真实可达，识别控制条件、授权边界与业务约束。",
  "报告与协作编排": "用于审计过程编排、结论沉淀与最终报告输出，保障任务可交付性。",
};

export default function SkillToolsPanel() {
  const [mcpCatalog, setMcpCatalog] = useState<McpCatalogItem[]>(
    DEFAULT_MCP_CATALOG,
  );
  const [mcpCatalogLoading, setMcpCatalogLoading] = useState(false);

  const groupedTools = useMemo(() => {
    const grouped = new Map<SkillToolCategory, typeof SKILL_TOOLS_CATALOG>();
    for (const category of SKILL_TOOL_CATEGORY_ORDER) {
      grouped.set(
        category,
        SKILL_TOOLS_CATALOG.filter((item) => item.category === category),
      );
    }
    return grouped;
  }, []);

  useEffect(() => {
    let mounted = true;
    const loadMcpCatalog = async () => {
      setMcpCatalogLoading(true);
      try {
        const config = await api.getUserConfig();
        if (!mounted) return;
        const serverCatalog =
          config?.otherConfig?.mcpConfig?.catalog ??
          DEFAULT_MCP_CATALOG;
        setMcpCatalog(normalizeMcpCatalog(serverCatalog));
      } catch {
        if (!mounted) return;
        setMcpCatalog(DEFAULT_MCP_CATALOG);
      } finally {
        if (mounted) {
          setMcpCatalogLoading(false);
        }
      }
    };

    void loadMcpCatalog();
    return () => {
      mounted = false;
    };
  }, []);

  const mcpServerCount = useMemo(
    () => mcpCatalog.filter((item) => item.type === "mcp-server").length,
    [mcpCatalog],
  );
  const mcpSkillPackCount = useMemo(
    () => mcpCatalog.filter((item) => item.type === "skill-pack").length,
    [mcpCatalog],
  );

  return (
    <div className="space-y-6">
      <Card className="cyber-card p-5 gap-3">
        <CardHeader className="border-b border-border pb-3">
          <CardTitle className="text-base">智能审计 Skill 工具目录</CardTitle>
        </CardHeader>
        <CardContent className="pt-3">
          <p className="text-sm text-muted-foreground leading-relaxed">
            本页展示智能审计运行时可调用的全量工具（{SKILL_TOOLS_CATALOG.length} 个），每个工具包含简介、使用目标、详细 prompt 用法、示例输入和误用提示。
          </p>
          <div className="mt-3 flex items-center gap-2">
            <Badge variant="outline" className="text-xs">
              工具总数
            </Badge>
            <span className="font-mono text-sm text-foreground">
              {SKILL_TOOLS_CATALOG.length}
            </span>
          </div>
        </CardContent>
      </Card>

      {SKILL_TOOL_CATEGORY_ORDER.map((category) => {
        const tools = groupedTools.get(category) ?? [];
        return (
          <section key={category} className="space-y-3">
            <div className="flex flex-wrap items-center gap-2">
              <h3 className="font-mono text-sm font-bold uppercase text-foreground">
                {category}
              </h3>
              <Badge variant="secondary" className="text-xs">
                {tools.length} 个工具
              </Badge>
            </div>
            <p className="text-xs text-muted-foreground">{CATEGORY_DESC[category] || "该分类用于智能审计流程中的关键步骤。"} </p>

            <div className="grid grid-cols-1 gap-3">
              {tools.map((tool) => (
                <Card key={tool.id} className="cyber-card p-4 gap-3">
                  <CardHeader className="pb-2 border-b border-border">
                    <div className="flex flex-wrap items-center justify-between gap-2">
                      <code className="font-mono text-sm text-foreground">{tool.id}</code>
                      <Badge variant="outline" className="text-[10px] uppercase">
                        skill tool
                      </Badge>
                    </div>
                    <p className="text-sm text-muted-foreground leading-relaxed">
                      {tool.summary}
                    </p>
                  </CardHeader>

                  <CardContent className="space-y-3 pt-1">
                    <div className="rounded-md border border-border bg-muted/30 p-3">
                      <div className="text-xs font-mono uppercase text-muted-foreground mb-1">
                        使用目标
                      </div>
                      <div className="text-sm text-foreground">{tool.goal}</div>
                      <ul className="mt-2 space-y-1 text-xs text-muted-foreground list-disc pl-4">
                        {tool.taskList.map((task) => (
                          <li key={task}>{task}</li>
                        ))}
                      </ul>
                    </div>

                    <details className="rounded-md border border-border bg-card/70 p-3">
                      <summary className="cursor-pointer list-none font-mono text-xs uppercase text-primary">
                        查看详细使用方法 Prompt
                      </summary>
                      <div className="mt-3 space-y-3">
                        <div>
                          <div className="text-xs font-mono uppercase text-muted-foreground mb-1">
                            Prompt 模板
                          </div>
                          <pre className="text-xs whitespace-pre-wrap break-words rounded-md border border-border bg-muted/30 p-3 font-mono leading-relaxed">
                            {buildSkillToolPrompt(tool)}
                          </pre>
                        </div>

                        <div>
                          <div className="text-xs font-mono uppercase text-muted-foreground mb-1">
                            示例输入
                          </div>
                          <pre className="text-xs whitespace-pre-wrap break-words rounded-md border border-border bg-muted/30 p-3 font-mono leading-relaxed">
                            {tool.exampleInput}
                          </pre>
                        </div>

                        <div>
                          <div className="text-xs font-mono uppercase text-muted-foreground mb-1">
                            参数清单
                          </div>
                          <ul className="space-y-1 text-xs text-muted-foreground list-disc pl-4">
                            {tool.inputChecklist.map((input) => (
                              <li key={input}>{input}</li>
                            ))}
                          </ul>
                        </div>

                        <div>
                          <div className="text-xs font-mono uppercase text-muted-foreground mb-1">
                            误用提示
                          </div>
                          <ul className="space-y-1 text-xs text-muted-foreground list-disc pl-4">
                            {tool.pitfalls.map((pitfall) => (
                              <li key={pitfall}>{pitfall}</li>
                            ))}
                          </ul>
                        </div>
                      </div>
                    </details>
                  </CardContent>
                </Card>
              ))}
            </div>
          </section>
        );
      })}

      <Card className="cyber-card p-5 gap-3">
        <CardHeader className="border-b border-border pb-3">
          <CardTitle className="text-base">智能审计 MCP 目录</CardTitle>
        </CardHeader>
        <CardContent className="pt-3 space-y-3">
          <p className="text-sm text-muted-foreground leading-relaxed">
            展示当前集成 MCP 与 Skill Pack 能力，包括执行功能、输入输出接口、包含的 skill 以及启用状态。
          </p>
          <div className="flex flex-wrap items-center gap-2">
            <Badge variant="outline" className="text-xs">
              MCP Server {mcpServerCount}
            </Badge>
            <Badge variant="outline" className="text-xs">
              Skill Pack {mcpSkillPackCount}
            </Badge>
            <Badge variant="outline" className="text-xs">
              总数 {mcpCatalog.length}
            </Badge>
            {mcpCatalogLoading ? (
              <Badge variant="secondary" className="text-xs">
                目录加载中
              </Badge>
            ) : null}
            {mcpCatalog.some(
              (item) =>
                item.type === "mcp-server" &&
                item.required !== false &&
                item.startup_ready === false,
            ) ? (
              <Badge
                variant="outline"
                className="text-xs border-rose-500/40 text-rose-600 dark:text-rose-300 bg-rose-500/10"
              >
                全量 MCP 未就绪，任务不可启动
              </Badge>
            ) : null}
          </div>

          <div className="grid grid-cols-1 gap-3">
            {mcpCatalog.map((item) => (
              <Card key={item.id} className="cyber-card p-4 gap-3">
                <CardHeader className="pb-2 border-b border-border">
                  <div className="flex flex-wrap items-center justify-between gap-2">
                    <div className="flex items-center gap-2">
                      <code className="font-mono text-sm text-foreground">{item.id}</code>
                      <span className="text-sm text-foreground">{item.name}</span>
                    </div>
                    <div className="flex items-center gap-2">
                      <Badge variant="outline" className="text-[10px] uppercase">
                        {item.type === "mcp-server" ? "mcp server" : "skill pack"}
                      </Badge>
                      <Badge
                        variant="outline"
                        className={`text-[10px] uppercase ${
                          item.enabled
                            ? "border-emerald-500/40 text-emerald-600 dark:text-emerald-300 bg-emerald-500/10"
                            : "border-zinc-500/40 text-zinc-600 dark:text-zinc-300 bg-zinc-500/10"
                        }`}
                      >
                        {item.enabled ? "enabled" : "disabled"}
                      </Badge>
                    </div>
                  </div>
                  <p className="text-sm text-muted-foreground leading-relaxed">
                    {item.description}
                  </p>
                  <div className="text-xs text-muted-foreground">
                    runtime_mode: {item.runtime_mode || "n/a"}
                  </div>
                </CardHeader>

                <CardContent className="space-y-3 pt-1">
                  <div className="grid grid-cols-1 lg:grid-cols-3 gap-2">
                    <div className="rounded-md border border-border bg-muted/30 p-3">
                      <div className="text-xs font-mono uppercase text-muted-foreground mb-1">
                        执行功能
                      </div>
                      <ul className="space-y-1 text-xs text-muted-foreground list-disc pl-4">
                        {item.executionFunctions.map((func) => (
                          <li key={func}>{func}</li>
                        ))}
                      </ul>
                    </div>

                    <div className="rounded-md border border-border bg-muted/30 p-3">
                      <div className="text-xs font-mono uppercase text-muted-foreground mb-1">
                        输入接口
                      </div>
                      <ul className="space-y-1 text-xs text-muted-foreground list-disc pl-4">
                        {item.inputInterface.map((field) => (
                          <li key={field}>{field}</li>
                        ))}
                      </ul>
                    </div>

                    <div className="rounded-md border border-border bg-muted/30 p-3">
                      <div className="text-xs font-mono uppercase text-muted-foreground mb-1">
                        输出接口
                      </div>
                      <ul className="space-y-1 text-xs text-muted-foreground list-disc pl-4">
                        {item.outputInterface.map((field) => (
                          <li key={field}>{field}</li>
                        ))}
                      </ul>
                    </div>
                  </div>

                  <div className="rounded-md border border-border bg-card/70 p-3">
                    <div className="text-xs font-mono uppercase text-muted-foreground mb-1">
                      包含 Skill
                    </div>
                    <div className="flex flex-wrap items-center gap-2">
                      {item.includedSkills.map((skill) => (
                        <Badge key={skill} variant="secondary" className="text-[10px]">
                          {skill}
                        </Badge>
                      ))}
                    </div>
                    <div className="mt-2 text-xs text-muted-foreground break-all">
                      Source: {item.source}
                    </div>
                  </div>

                  {item.type === "mcp-server" ? (
                    <div className="rounded-md border border-border bg-muted/20 p-3 space-y-2">
                      <div className="text-xs font-mono uppercase text-muted-foreground">
                        域状态
                      </div>
                      <div className="grid grid-cols-1 md:grid-cols-2 gap-2 text-xs">
                        <div className="rounded border border-border p-2">
                          <div className="font-mono text-muted-foreground">backend</div>
                          <div>
                            enabled: {item.backend?.enabled ? "true" : "false"}
                          </div>
                          <div>
                            startup_ready: {item.backend?.startup_ready ? "true" : "false"}
                          </div>
                          {item.backend?.startup_error ? (
                            <div className="text-rose-600 dark:text-rose-300 break-words">
                              error: {item.backend.startup_error}
                            </div>
                          ) : null}
                        </div>
                        <div className="rounded border border-border p-2">
                          <div className="font-mono text-muted-foreground">sandbox</div>
                          <div>
                            enabled: {item.sandbox?.enabled ? "true" : "false"}
                          </div>
                          <div>
                            startup_ready: {item.sandbox?.startup_ready ? "true" : "false"}
                          </div>
                          {item.sandbox?.startup_error ? (
                            <div className="text-rose-600 dark:text-rose-300 break-words">
                              error: {item.sandbox.startup_error}
                            </div>
                          ) : null}
                        </div>
                      </div>
                      <div className="text-xs">
                        required: {item.required === false ? "false" : "true"} | startup_ready:{" "}
                        {item.startup_ready === false ? "false" : "true"}
                      </div>
                      {item.startup_error ? (
                        <div className="text-xs text-rose-600 dark:text-rose-300 break-words">
                          startup_error: {item.startup_error}
                        </div>
                      ) : null}
                    </div>
                  ) : null}
                </CardContent>
              </Card>
            ))}
          </div>
        </CardContent>
      </Card>
    </div>
  );
}
