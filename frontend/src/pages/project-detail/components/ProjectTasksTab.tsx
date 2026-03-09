import { Link, useLocation } from "react-router-dom";
import { FileText, Play, Activity } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import type { AuditTask } from "@/shared/types";
import type { UnifiedTask } from "@/shared/types";
import { appendReturnTo } from "@/shared/utils/findingRoute";

export function ProjectTasksTab(props: {
  unifiedTasks: UnifiedTask[];
  onCreateTask: () => void;
  formatDate: (dateString: string) => string;
  renderStatusBadge: (status: string) => React.ReactNode;
  renderStatusIcon: (status: string) => React.ReactNode;
  getTaskRoute?: (task: UnifiedTask) => string;
}) {
  const location = useLocation();
  const {
    unifiedTasks,
    onCreateTask,
    formatDate,
    renderStatusBadge,
    renderStatusIcon,
    getTaskRoute,
  } = props;
  const currentRoute = `${location.pathname}${location.search}`;

  return (
    <>
      <div className="flex items-center justify-between">
        <div className="section-header mb-0 pb-0 border-0">
          <FileText className="w-5 h-5 text-primary" />
          <h3 className="section-title">扫描任务</h3>
        </div>
        <Button onClick={onCreateTask} className="cyber-btn-primary">
          <Play className="w-4 h-4 mr-2" />
          新建任务
        </Button>
      </div>

      {unifiedTasks.length > 0 ? (
        <div className="space-y-4">
          {unifiedTasks.map((wrappedTask) => {
            const isAuditTask = wrappedTask.kind === "audit";
            const isStaticTask = wrappedTask.kind === "static";
            const task: any = wrappedTask.task as any;

            const issueCount = isStaticTask
              ? (task.total_findings ?? 0)
              : isAuditTask
                ? (task.issues_count ?? 0)
                : (task.findings_count ?? 0);
            const totalFiles = isStaticTask ? (task.files_scanned ?? 0) : (task.total_files ?? 0);
            const totalLines = isStaticTask ? (task.lines_scanned ?? "-") : (task.total_lines ?? "-");
            const defaultRoute = isStaticTask
              ? `/static-analysis/${task.id}`
              : isAuditTask
                ? `/tasks/${task.id}`
                : `/agent-audit/${task.id}`;
            const detailRoute = getTaskRoute ? getTaskRoute(wrappedTask) : defaultRoute;
            const resolvedDetailRoute = appendReturnTo(detailRoute, currentRoute);

            return (
              <div key={`${wrappedTask.kind}:${task.id}`} className="cyber-card p-6">
                <div className="flex items-center justify-between mb-4 pb-4 border-b border-border">
                  <div className="flex items-center space-x-3">
                    <div
                      className={`w-10 h-10 rounded-lg flex items-center justify-center ${task.status === "completed"
                        ? "bg-emerald-500/20"
                        : task.status === "running"
                          ? "bg-sky-500/20"
                          : task.status === "interrupted"
                            ? "bg-orange-500/20"
                          : task.status === "failed"
                            ? "bg-rose-500/20"
                            : "bg-muted"
                        }`}
                    >
                      {renderStatusIcon(task.status)}
                    </div>
                    <div>
                      <h4 className="font-bold text-foreground uppercase">
                        {isStaticTask
                          ? "静态分析任务"
                          : isAuditTask
                            ? ((task as AuditTask).task_type === "repository" ? "扫描任务" : "即时分析任务")
                            : "Agent 扫描任务"}
                      </h4>
                      <p className="text-sm text-muted-foreground font-mono">创建于 {formatDate(task.created_at)}</p>
                    </div>
                  </div>
                  <div className="flex items-center gap-2">
                    <Badge className={
                      wrappedTask.kind === "agent"
                        ? "cyber-badge-info"
                        : wrappedTask.kind === "static"
                          ? "cyber-badge-warning"
                          : "cyber-badge-muted"
                    }>
                      {wrappedTask.kind === "agent"
                        ? "AGENT"
                        : wrappedTask.kind === "static"
                          ? "STATIC"
                          : "AUDIT"}
                    </Badge>
                    {renderStatusBadge(task.status)}
                  </div>
                </div>

                <div className="grid grid-cols-2 md:grid-cols-3 gap-4 mb-4 font-mono">
                  <div className="text-center p-3 bg-muted rounded-lg border border-border">
                    <p className="text-2xl font-bold text-foreground">{totalFiles}</p>
                    <p className="text-xs text-muted-foreground uppercase">总文件数</p>
                  </div>
                  <div className="text-center p-3 bg-muted rounded-lg border border-border">
                    <p className="text-2xl font-bold text-foreground">{totalLines}</p>
                    <p className="text-xs text-muted-foreground uppercase">代码行数</p>
                  </div>
                  <div className="text-center p-3 bg-muted rounded-lg border border-border">
                    <p className="text-2xl font-bold text-amber-400">{issueCount}</p>
                    <p className="text-xs text-muted-foreground uppercase">{isAuditTask ? "发现问题" : "发现漏洞"}</p>
                  </div>
                </div>

                <div className="flex justify-end space-x-2 pt-4 border-t border-border">
                  <Link to={resolvedDetailRoute}>
                    <Button variant="outline" size="sm" className="cyber-btn-outline">
                      <FileText className="w-4 h-4 mr-2" />
                      查看详情
                    </Button>
                  </Link>
                </div>
              </div>
            );
          })}
        </div>
      ) : (
        <div className="cyber-card p-12 text-center">
          <Activity className="w-16 h-16 text-muted-foreground mx-auto mb-4" />
          <h3 className="text-lg font-bold text-foreground mb-2 uppercase">暂无扫描任务</h3>
          <p className="text-sm text-muted-foreground font-mono">
            点击右上角「新建任务」开始代码安全分析
          </p>
        </div>
      )}
    </>
  );
}
