/**
 * Dashboard Page
 * Cyberpunk Terminal Aesthetic
 */

import { useState, useEffect } from "react";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import {
  Activity, AlertTriangle, Clock, Code,
  Zap, Terminal
} from "lucide-react";
import { api, isDemoMode } from "@/shared/config/database";
import type { Project, AuditTask, ProjectStats } from "@/shared/types";
import { Link } from "react-router-dom";
import { toast } from "sonner";
import { getAgentTasks, type AgentTask } from "@/shared/api/agentTasks";
import {
  getOpengrepRules,
  getOpengrepScanTasks,
  type OpengrepScanTask,
} from "@/shared/api/opengrep";
import { getGitleaksScanTasks, type GitleaksScanTask } from "@/shared/api/gitleaks";
import { runWithRefreshMode } from "@/shared/utils/refreshMode";

type RecentActivityItem = {
  id: string;
  projectName: string;
  kind: "rule_scan" | "intelligent_audit";
  status: string;
  gitleaksEnabled?: boolean;
  createdAt: string;
  route: string;
};

const INTERRUPTED_STATUSES = new Set(["interrupted", "aborted", "cancelled"]);

export default function Dashboard() {
  const [stats, setStats] = useState<ProjectStats | null>(null);
  const [recentActivities, setRecentActivities] = useState<RecentActivityItem[]>([]);
  const [interruptedTasksCount, setInterruptedTasksCount] = useState(0);
  const [loading, setLoading] = useState(true);
  const [ruleStats, setRuleStats] = useState({ total: 0, enabled: 0 });

  useEffect(() => {
    loadDashboardData();

    const timer = window.setInterval(() => {
      loadDashboardData({ silent: true });
    }, 15000);

    return () => {
      window.clearInterval(timer);
    };
  }, []);

  const getRelativeTime = (time: string) => {
    const now = new Date();
    const taskDate = new Date(time);
    const diffMs = now.getTime() - taskDate.getTime();
    const diffMins = Math.floor(diffMs / 60000);
    const diffHours = Math.floor(diffMs / 3600000);
    const diffDays = Math.floor(diffMs / 86400000);

    if (diffMins < 60) return `${Math.max(diffMins, 1)}分钟前`;
    if (diffHours < 24) return `${diffHours}小时前`;
    return `${diffDays}天前`;
  };

  const formatCreatedAt = (time: string) => {
    const date = new Date(time);
    if (Number.isNaN(date.getTime())) return time;
    return date.toLocaleString("zh-CN", {
      year: "numeric",
      month: "2-digit",
      day: "2-digit",
      hour: "2-digit",
      minute: "2-digit",
      hour12: false,
    });
  };

  const getTaskStatusText = (status: string) => {
    switch (status) {
      case "completed":
        return "任务完成";
      case "running":
        return "任务运行中";
      case "failed":
        return "任务失败";
      case "pending":
        return "任务待处理";
      case "cancelled":
      case "interrupted":
      case "aborted":
        return "任务中止";
      default:
        return status || "未知状态";
    }
  };

  const getTaskStatusClassName = (status: string) => {
    if (status === "completed") {
      return "bg-emerald-500/5 border-emerald-500/20 hover:border-emerald-500/40";
    }
    if (status === "running") {
      return "bg-sky-500/5 border-sky-500/20 hover:border-sky-500/40";
    }
    if (status === "failed") {
      return "bg-rose-500/5 border-rose-500/20 hover:border-rose-500/40";
    }
    if (INTERRUPTED_STATUSES.has(status)) {
      return "bg-orange-500/5 border-orange-500/20 hover:border-orange-500/40";
    }
    return "bg-muted/30 border-border hover:border-border";
  };

  const getTaskStatusBadgeClassName = (status: string) => {
    if (status === "completed") {
      return "cyber-badge-success";
    }
    if (status === "running") {
      return "cyber-badge-info";
    }
    if (status === "failed") {
      return "cyber-badge-danger";
    }
    if (INTERRUPTED_STATUSES.has(status)) {
      return "cyber-badge-warning";
    }
    return "cyber-badge-muted";
  };

  const loadDashboardData = async (options?: { silent?: boolean }) => {
    try {
      await runWithRefreshMode(async () => {
      const results = await Promise.allSettled([
        api.getProjectStats(),
        api.getProjects(),
        api.getAuditTasks()
      ]);

      if (results[0].status === 'fulfilled') {
        setStats(results[0].value);
      } else {
        setStats({
          total_projects: 0,
          active_projects: 0,
          total_tasks: 0,
          completed_tasks: 0,
          total_issues: 0,
          resolved_issues: 0,
          avg_quality_score: 0
        });
      }

      const allProjects: Project[] =
        results[1].status === "fulfilled" && Array.isArray(results[1].value)
          ? results[1].value
          : [];
      const projectNameMap = new Map(
        allProjects.map((project) => [project.id, project.name]),
      );

      let tasks: AuditTask[] = [];
      if (results[2].status === 'fulfilled') {
        tasks = Array.isArray(results[2].value) ? results[2].value : [];
      }
      const baseInterruptedCount = tasks.filter((task) =>
        INTERRUPTED_STATUSES.has(task.status),
      ).length;
      setInterruptedTasksCount(baseInterruptedCount);

      try {
        const [agentTasks, opengrepTasks, gitleaksTasks] = await Promise.all([
          getAgentTasks({ limit: 100 }),
          getOpengrepScanTasks({ limit: 100 }),
          getGitleaksScanTasks({ limit: 100 }),
        ]);

        const resolveProjectName = (projectId: string) =>
          projectNameMap.get(projectId) || "未知项目";

        const gitleaksByProject = new Map<string, GitleaksScanTask[]>();
        for (const task of gitleaksTasks) {
          const list = gitleaksByProject.get(task.project_id) || [];
          list.push(task);
          gitleaksByProject.set(task.project_id, list);
        }
        for (const [projectId, list] of gitleaksByProject.entries()) {
          list.sort(
            (a, b) =>
              new Date(a.created_at).getTime() - new Date(b.created_at).getTime(),
          );
          gitleaksByProject.set(projectId, list);
        }
        const usedGitleaksTaskIds = new Set<string>();
        const pairingWindowMs = 60 * 1000;

        const pickPairedGitleaksTask = (opengrepTask: OpengrepScanTask) => {
          const candidates = gitleaksByProject.get(opengrepTask.project_id) || [];
          if (candidates.length === 0) return null;
          const opengrepTime = new Date(opengrepTask.created_at).getTime();
          let bestTask: GitleaksScanTask | null = null;
          let bestDiff = Number.POSITIVE_INFINITY;
          for (const candidate of candidates) {
            if (usedGitleaksTaskIds.has(candidate.id)) continue;
            const diff = Math.abs(
              new Date(candidate.created_at).getTime() - opengrepTime,
            );
            if (diff <= pairingWindowMs && diff < bestDiff) {
              bestTask = candidate;
              bestDiff = diff;
            }
          }
          if (bestTask) {
            usedGitleaksTaskIds.add(bestTask.id);
          }
          return bestTask;
        };

        const ruleScanActivities: RecentActivityItem[] = opengrepTasks.map((task) => {
          const pairedGitleaksTask = pickPairedGitleaksTask(task);
          const params = new URLSearchParams();
          params.set("opengrepTaskId", task.id);
          params.set("muteToast", "1");
          if (pairedGitleaksTask) {
            params.set("gitleaksTaskId", pairedGitleaksTask.id);
          }
          return {
            id: `opengrep-${task.id}`,
            projectName: resolveProjectName(task.project_id),
            kind: "rule_scan" as const,
            status: task.status,
            gitleaksEnabled: Boolean(pairedGitleaksTask),
            createdAt: task.created_at,
            route: `/static-analysis/${task.id}?${params.toString()}`,
          };
        });

        const activityItems: RecentActivityItem[] = [
          ...ruleScanActivities,
          ...agentTasks.map((task: AgentTask) => ({
            id: `agent-${task.id}`,
            projectName: resolveProjectName(task.project_id),
            kind: "intelligent_audit" as const,
            status: task.status,
            createdAt: task.created_at,
            route: `/agent-audit/${task.id}?muteToast=1`,
          })),
        ].sort(
          (a, b) =>
            new Date(b.createdAt).getTime() - new Date(a.createdAt).getTime(),
        );

        setRecentActivities(activityItems.slice(0, 8));
        setInterruptedTasksCount(
          baseInterruptedCount +
            agentTasks.filter((task) => INTERRUPTED_STATUSES.has(task.status))
              .length +
            opengrepTasks.filter((task) => INTERRUPTED_STATUSES.has(task.status))
              .length +
            gitleaksTasks.filter((task) => INTERRUPTED_STATUSES.has(task.status))
              .length,
        );
      } catch (error) {
        console.error("获取最近活动失败:", error);
        setRecentActivities([]);
      }

      try {
        const rules = await getOpengrepRules();
        const totalRules = rules.length;
        const enabledRules = rules.filter((rule) => rule.is_active).length;
        setRuleStats({ total: totalRules, enabled: enabledRules });
      } catch (error) {
        console.error('获取规则统计失败:', error);
      }
      }, { ...options, setLoading });
    } catch (error) {
      console.error('仪表盘数据加载失败:', error);
      toast.error("数据加载失败");
    }
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center min-h-[60vh]">
        <div className="text-center space-y-4">
          <div className="loading-spinner mx-auto" />
          <p className="text-muted-foreground font-mono text-base uppercase tracking-wider">加载数据中...</p>
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-6 p-6 bg-background min-h-screen font-mono relative">
      {/* Grid background */}
      <div className="absolute inset-0 cyber-grid-subtle pointer-events-none" />

      {/* Demo Mode Warning */}
      {isDemoMode && (
        <div className="relative z-10 cyber-card p-4 border-amber-500/30 bg-amber-500/5">
          <div className="flex items-start gap-3">
            <AlertTriangle className="w-5 h-5 text-amber-400 mt-0.5" />
            <div className="text-sm text-foreground/80">
              当前使用<span className="text-amber-400 font-bold">演示模式</span>，显示的是模拟数据。
              <Link to="/admin" className="ml-2 text-primary font-bold hover:underline">
                前往配置 →
              </Link>
            </div>
          </div>
        </div>
      )}

      {/* Stats Cards */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4 relative z-10">
        {/* Total Projects */}
        <div className="cyber-card p-4">
          <div className="flex items-center justify-between">
            <div>
              <p className="stat-label">总项目数</p>
              <p className="stat-value">{stats?.total_projects || 0}</p>
              <p className="text-sm text-emerald-400 mt-1 flex items-center gap-1">
                <span className="w-2 h-2 rounded-full bg-emerald-400" />
                活跃: {stats?.active_projects || 0}
              </p>
            </div>
            <div className="stat-icon text-primary">
              <Code className="w-6 h-6" />
            </div>
          </div>
        </div>

        {/* Audit Tasks */}
        <div className="cyber-card p-4">
          <div className="flex items-center justify-between">
            <div>
              <p className="stat-label">审计任务</p>
              <p className="stat-value">{stats?.total_tasks || 0}</p>
              <p className="text-sm mt-1 flex items-center gap-3">
                <span className="text-emerald-400 inline-flex items-center gap-1">
                  <span className="w-2 h-2 rounded-full bg-emerald-400" />
                  已完成: {stats?.completed_tasks || 0}
                </span>
                <span className="text-orange-400 inline-flex items-center gap-1">
                  <span className="w-2 h-2 rounded-full bg-orange-400" />
                  中止: {interruptedTasksCount}
                </span>
              </p>
            </div>
            <div className="stat-icon text-emerald-400">
              <Activity className="w-6 h-6" />
            </div>
          </div>
        </div>

        {/* Rule Library */}
        <div className="cyber-card p-4">
          <div className="flex items-center justify-between">
            <div>
              <p className="stat-label">审计规则</p>
              <p className="stat-value">{ruleStats.total}</p>
              <p className="text-sm text-sky-400 mt-1 flex items-center gap-1">
                <span className="w-2 h-2 rounded-full bg-sky-400" />
                已启用: {ruleStats.enabled}
              </p>
            </div>
            <div className="stat-icon text-sky-400">
              <AlertTriangle className="w-6 h-6" />
            </div>
          </div>
        </div>

      </div>

      {/* Main Content */}
      <div className="grid grid-cols-1 xl:grid-cols-4 gap-4 relative z-10">
        {/* Left Content */}
        <div className="xl:col-span-3 space-y-4">
          {/* Recent Activity */}
          <div className="cyber-card p-4">
            <div className="section-header">
              <Terminal className="w-5 h-5 text-amber-400" />
              <h3 className="section-title">最新活动</h3>
            </div>
            <div className="space-y-2">
              {recentActivities.length > 0 ? (
                recentActivities.map((activity) => {
                  const activityName =
                    activity.kind === "rule_scan"
                      ? `${activity.projectName}-规则扫描`
                      : `${activity.projectName}-智能审计`;
                  return (
                    <Link
                      key={activity.id}
                      to={activity.route}
                      className={`block p-3 rounded-lg border transition-all ${getTaskStatusClassName(activity.status)}`}
                    >
                      <div className="flex flex-wrap items-center gap-x-3 gap-y-2">
                        <p className="text-base font-medium text-foreground">
                          {activityName}
                        </p>
                        {activity.kind === "rule_scan" && (
                          <span className="text-xs text-muted-foreground">
                            Gitleaks扫描：{activity.gitleaksEnabled ? "已启用" : "未启用"}
                          </span>
                        )}
                        <Badge className={getTaskStatusBadgeClassName(activity.status)}>
                          漏洞扫描状态：{getTaskStatusText(activity.status)}
                        </Badge>
                        <span className="text-sm text-muted-foreground/80">
                          创建时间：{formatCreatedAt(activity.createdAt)}（{getRelativeTime(activity.createdAt)}）
                        </span>
                      </div>
                    </Link>
                  );
                })
              ) : (
                <div className="empty-state py-6">
                  <Clock className="w-10 h-10 text-muted-foreground mb-2" />
                  <p className="text-base text-muted-foreground">暂无活动记录</p>
                </div>
              )}
            </div>
          </div>

        </div>

        {/* Right Sidebar */}
        <div className="xl:col-span-1 space-y-4">
          {/* Quick Actions */}
          <div className="cyber-card p-4">
            <div className="section-header">
              <Zap className="w-5 h-5 text-primary" />
              <h3 className="section-title">快速操作</h3>
            </div>
            <div className="space-y-2">
              <Link to="/projects" className="block">
                <Button variant="outline" className="w-full justify-start cyber-btn-outline h-10">
                  创建项目
                </Button>
              </Link>                          
              
            </div>
          </div>

        </div>
      </div>
    </div>
  );
}
