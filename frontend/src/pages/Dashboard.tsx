/**
 * Dashboard Page
 * Cyberpunk Terminal Aesthetic
 */

import { useState, useEffect, useMemo } from "react";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { Label } from "@/components/ui/label";
import {
	Dialog,
	DialogContent,
	DialogHeader,
	DialogTitle,
} from "@/components/ui/dialog";
import {
	Select,
	SelectContent,
	SelectItem,
	SelectTrigger,
	SelectValue,
} from "@/components/ui/select";
import {
	Activity,
	AlertTriangle,
	Clock,
	Code,
	Upload,
	Zap,
	Terminal,
} from "lucide-react";
import { api, isDemoMode } from "@/shared/config/database";
import type { Project, AuditTask, ProjectStats } from "@/shared/types";
import { Link, useNavigate } from "react-router-dom";
import { toast } from "sonner";
import AgentModeSelector, {
	type AuditMode,
	type StaticToolSelection,
} from "@/components/agent/AgentModeSelector";
import {
	createAgentTask,
	getAgentTasks,
	type AgentTask,
} from "@/shared/api/agentTasks";
import { runAgentPreflightCheck } from "@/shared/api/agentPreflight";
import {
	createOpengrepScanTask,
	getOpengrepRules,
	getOpengrepScanTasks,
	type OpengrepRule,
	type OpengrepScanTask,
} from "@/shared/api/opengrep";
import {
	createGitleaksScanTask,
	getGitleaksScanTasks,
	type GitleaksScanTask,
} from "@/shared/api/gitleaks";
import { runWithRefreshMode } from "@/shared/utils/refreshMode";
import { isZipProject } from "@/shared/utils/projectUtils";
import { validateZipFile } from "@/features/projects/services/repoZipScan";
import { uploadZipFile } from "@/shared/utils/zipStorage";

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
const ACTIVITY_PAGE_SIZE = 10;

export default function Dashboard() {
	const navigate = useNavigate();
	const [stats, setStats] = useState<ProjectStats | null>(null);
	const [projects, setProjects] = useState<Project[]>([]);
	const [recentActivities, setRecentActivities] = useState<
		RecentActivityItem[]
	>([]);
	const [activityKeyword, setActivityKeyword] = useState("");
	const [activityPage, setActivityPage] = useState(1);
	const [interruptedTasksCount, setInterruptedTasksCount] = useState(0);
	const [loading, setLoading] = useState(true);
	const [ruleStats, setRuleStats] = useState({ total: 0, enabled: 0 });
	const [createProjectOpen, setCreateProjectOpen] = useState(false);
	const [creatingProject, setCreatingProject] = useState(false);
	const [projectName, setProjectName] = useState("");
	const [projectDescription, setProjectDescription] = useState("");
	const [projectZipFile, setProjectZipFile] = useState<File | null>(null);
	const [createAuditOpen, setCreateAuditOpen] = useState(false);
	const [creatingAudit, setCreatingAudit] = useState(false);
	const [selectedProjectId, setSelectedProjectId] = useState<string>("");
	const [auditMode, setAuditMode] = useState<AuditMode>("static");
	const [staticTools, setStaticTools] = useState<StaticToolSelection>({
		opengrep: true,
		gitleaks: false,
	});

	useEffect(() => {
		loadDashboardData();

		const timer = window.setInterval(() => {
			loadDashboardData({ silent: true });
		}, 15000);

		return () => {
			window.clearInterval(timer);
		};
	}, []);

	const filteredActivities = useMemo(() => {
		const keyword = activityKeyword.trim().toLowerCase();
		if (!keyword) return recentActivities;
		return recentActivities.filter((activity) => {
			const kindText =
				activity.kind === "rule_scan" ? "静态扫描" : "智能审计";
			return (
				activity.projectName.toLowerCase().includes(keyword) ||
				kindText.includes(keyword) ||
				getTaskStatusText(activity.status).includes(keyword)
			);
		});
	}, [recentActivities, activityKeyword]);

	const totalActivityPages = Math.max(
		1,
		Math.ceil(filteredActivities.length / ACTIVITY_PAGE_SIZE),
	);

	useEffect(() => {
		setActivityPage(1);
	}, [activityKeyword]);

	useEffect(() => {
		if (activityPage > totalActivityPages) {
			setActivityPage(totalActivityPages);
		}
	}, [activityPage, totalActivityPages]);

	const pagedActivities = useMemo(() => {
		const start = (activityPage - 1) * ACTIVITY_PAGE_SIZE;
		return filteredActivities.slice(start, start + ACTIVITY_PAGE_SIZE);
	}, [filteredActivities, activityPage]);

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

	function getTaskStatusText(status: string) {
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
	}

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

	const extractApiErrorMessage = (error: unknown): string => {
		if (error instanceof Error) {
			const detail = (error as any)?.response?.data?.detail;
			if (typeof detail === "string" && detail.trim()) return detail;
			if (Array.isArray(detail) && detail.length > 0) {
				const msgs = detail
					.map((item: any) =>
						typeof item?.msg === "string" ? item.msg : String(item),
					)
					.filter(Boolean);
				if (msgs.length > 0) return msgs.join("; ");
			}
			return error.message || "未知错误";
		}
		const detail = (error as any)?.response?.data?.detail;
		if (typeof detail === "string" && detail.trim()) return detail;
		return "未知错误";
	};

	const loadDashboardData = async (options?: { silent?: boolean }) => {
		try {
			await runWithRefreshMode(
				async () => {
					const results = await Promise.allSettled([
						api.getProjectStats(),
						api.getProjects(),
						api.getAuditTasks(),
					]);

					if (results[0].status === "fulfilled") {
						setStats(results[0].value);
					} else {
						setStats({
							total_projects: 0,
							active_projects: 0,
							total_tasks: 0,
							completed_tasks: 0,
							total_issues: 0,
							resolved_issues: 0,
							avg_quality_score: 0,
						});
					}

					const allProjects: Project[] =
						results[1].status === "fulfilled" && Array.isArray(results[1].value)
							? results[1].value
							: [];
					setProjects(allProjects);
					const projectNameMap = new Map(
						allProjects.map((project) => [project.id, project.name]),
					);

					let tasks: AuditTask[] = [];
					if (results[2].status === "fulfilled") {
						tasks = Array.isArray(results[2].value) ? results[2].value : [];
					}
					const baseInterruptedCount = tasks.filter((task) =>
						INTERRUPTED_STATUSES.has(task.status),
					).length;
					setInterruptedTasksCount(baseInterruptedCount);

					try {
						const [agentTasks, opengrepTasks, gitleaksTasks] =
							await Promise.all([
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
									new Date(a.created_at).getTime() -
									new Date(b.created_at).getTime(),
							);
							gitleaksByProject.set(projectId, list);
						}
						const usedGitleaksTaskIds = new Set<string>();
						const pairingWindowMs = 60 * 1000;

						const pickPairedGitleaksTask = (opengrepTask: OpengrepScanTask) => {
							const candidates =
								gitleaksByProject.get(opengrepTask.project_id) || [];
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

						const ruleScanActivities: RecentActivityItem[] = opengrepTasks.map(
							(task) => {
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
							},
						);

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
								new Date(b.createdAt).getTime() -
								new Date(a.createdAt).getTime(),
						);

						setRecentActivities(activityItems);
						setInterruptedTasksCount(
							baseInterruptedCount +
								agentTasks.filter((task) =>
									INTERRUPTED_STATUSES.has(task.status),
								).length +
								opengrepTasks.filter((task) =>
									INTERRUPTED_STATUSES.has(task.status),
								).length +
								gitleaksTasks.filter((task) =>
									INTERRUPTED_STATUSES.has(task.status),
								).length,
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
						console.error("获取规则统计失败:", error);
					}
				},
				{ ...options, setLoading },
			);
		} catch (error) {
			console.error("仪表盘数据加载失败:", error);
			toast.error("数据加载失败");
		}
	};

	useEffect(() => {
		if (!createAuditOpen) return;
		if (selectedProjectId) return;
		if (projects.length === 0) return;
		setSelectedProjectId(projects[0].id);
	}, [createAuditOpen, selectedProjectId, projects]);

	const selectedProject = projects.find((p) => p.id === selectedProjectId);
	const canCreateAudit =
		!!selectedProject &&
		(auditMode === "agent"
			? true
			: isZipProject(selectedProject) &&
				(staticTools.opengrep || staticTools.gitleaks));

	const resetCreateProjectForm = () => {
		setProjectName("");
		setProjectDescription("");
		setProjectZipFile(null);
	};

	const handleProjectZipSelect = (
		event: React.ChangeEvent<HTMLInputElement>,
	) => {
		const file = event.target.files?.[0] || null;
		if (!file) {
			setProjectZipFile(null);
			return;
		}
		const validation = validateZipFile(file);
		if (!validation.valid) {
			toast.error(validation.error || "压缩包校验失败");
			event.target.value = "";
			return;
		}
		setProjectZipFile(file);
		event.target.value = "";
	};

	const handleCreateProject = async () => {
		if (!projectName.trim()) {
			toast.error("请输入项目名称");
			return;
		}
		if (!projectZipFile) {
			toast.error("请先选择项目压缩包");
			return;
		}
		let createdProject: Project | null = null;
		try {
			setCreatingProject(true);
			createdProject = await api.createProject({
				name: projectName.trim(),
				description: projectDescription.trim() || undefined,
				source_type: "zip",
				repository_type: "other",
				repository_url: undefined,
				default_branch: "main",
				programming_languages: [],
			} as any);
			const uploadResult = await uploadZipFile(
				createdProject.id,
				projectZipFile,
			);
			if (!uploadResult.success) {
				throw new Error(uploadResult.message || "压缩包上传失败");
			}

			setCreateProjectOpen(false);
			resetCreateProjectForm();
			toast.success("项目创建成功");
			await loadDashboardData({ silent: true });
		} catch (error) {
			if (createdProject) {
				try {
					await api.deleteProject(createdProject.id);
				} catch (cleanupError) {
					console.error("回滚失败项目失败:", cleanupError);
				}
			}
			await loadDashboardData({ silent: true });
			const rawMsg = extractApiErrorMessage(error);
			const msg = rawMsg.includes("解压文件数超过 10000")
				? "压缩包解压后文件数量超过 10000 个，请精简后重试"
				: rawMsg;
			toast.error(`创建项目失败: ${msg}`);
		} finally {
			setCreatingProject(false);
		}
	};

	const handleCreateAudit = async (navigateToTask: boolean = true) => {
		if (!selectedProject) {
			toast.error("请先选择项目");
			return;
		}

		try {
			setCreatingAudit(true);

			if (auditMode === "agent") {
				const preflightToast = toast.loading(
					"正在检查智能审计配置（LLM / RAG）...",
				);
				const preflight = await runAgentPreflightCheck();
				toast.dismiss(preflightToast);
				if (!preflight.ok) {
					toast.error(preflight.message);
					return;
				}

				const agentTask = await createAgentTask({
					project_id: selectedProject.id,
					name: `智能审计-${selectedProject.name}`,
					branch_name:
						selectedProject.source_type === "repository"
							? selectedProject.default_branch || "main"
							: undefined,
					verification_level: "sandbox",
				});
				setCreateAuditOpen(false);
				toast.success("智能审计任务已创建");
				if (navigateToTask) {
					navigate(`/agent-audit/${agentTask.id}`);
				}
				await loadDashboardData({ silent: true });
				return;
			}

			if (!staticTools.opengrep && !staticTools.gitleaks) {
				toast.error("请选择至少一个静态分析工具");
				return;
			}
			if (!isZipProject(selectedProject)) {
				toast.error("静态分析仅支持源码归档项目，请选择上传项目");
				return;
			}

			let opengrepTask: { id: string } | null = null;
			let gitleaksTask: { id: string } | null = null;

			if (staticTools.opengrep) {
				const activeRules: OpengrepRule[] = await getOpengrepRules({
					is_active: true,
				});
				const activeRuleIds = activeRules.map((rule) => rule.id);
				if (activeRuleIds.length === 0) {
					toast.error("没有可用启用规则，请先启用规则");
					return;
				}
				opengrepTask = await createOpengrepScanTask({
					project_id: selectedProject.id,
					name: `静态分析-Opengrep-${selectedProject.name}`,
					rule_ids: activeRuleIds,
					target_path: ".",
				});
			}

			if (staticTools.gitleaks) {
				gitleaksTask = await createGitleaksScanTask({
					project_id: selectedProject.id,
					name: `静态分析-Gitleaks-${selectedProject.name}`,
					target_path: ".",
					no_git: true,
				});
			}

			const primaryTaskId = opengrepTask?.id || gitleaksTask?.id;
			if (!primaryTaskId) {
				toast.error("静态分析任务创建失败");
				return;
			}

			const params = new URLSearchParams();
			if (opengrepTask && gitleaksTask) {
				params.set("opengrepTaskId", opengrepTask.id);
				params.set("gitleaksTaskId", gitleaksTask.id);
			}
			if (!opengrepTask && gitleaksTask) {
				params.set("tool", "gitleaks");
			}

			setCreateAuditOpen(false);
			toast.success("静态分析任务已创建");
			if (navigateToTask) {
				navigate(
					`/static-analysis/${primaryTaskId}${params.toString() ? `?${params.toString()}` : ""}`,
				);
			}
			await loadDashboardData({ silent: true });
		} catch (error) {
			const msg = extractApiErrorMessage(error);
			toast.error(`创建审计任务失败: ${msg}`);
		} finally {
			setCreatingAudit(false);
		}
	};

	if (loading) {
		return (
			<div className="flex items-center justify-center min-h-[60vh]">
				<div className="text-center space-y-4">
					<div className="loading-spinner mx-auto" />
					<p className="text-muted-foreground font-mono text-base uppercase tracking-wider">
						加载数据中...
					</p>
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
							当前使用<span className="text-amber-400 font-bold">演示模式</span>
							，显示的是模拟数据。
							<Link
								to="/admin"
								className="ml-2 text-primary font-bold hover:underline"
							>
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
							<h3 className="section-title">任务浏览</h3>
						</div>
						<div className="space-y-3 mb-3">
							<div className="flex items-center gap-2">
								<Input
									value={activityKeyword}
									onChange={(e) => setActivityKeyword(e.target.value)}
									placeholder="按项目名/任务类型/状态搜索"
									className="h-9 font-mono"
								/>
							</div>
							<div className="flex items-center justify-between text-xs text-muted-foreground">
								<span>
									按时间倒序展示（新 → 旧）
								</span>
								<span>
									共 {filteredActivities.length} 条
								</span>
							</div>
						</div>
						<div className="space-y-2">
							{pagedActivities.length > 0 ? (
								pagedActivities.map((activity) => {
									const activityName =
										activity.kind === "rule_scan"
											? `${activity.projectName}-静态扫描`
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
														Gitleaks扫描：
														{activity.gitleaksEnabled ? "已启用" : "未启用"}
													</span>
												)}
												<Badge
													className={getTaskStatusBadgeClassName(
														activity.status,
													)}
												>
													漏洞扫描状态：{getTaskStatusText(activity.status)}
												</Badge>
												<span className="text-sm text-muted-foreground/80">
													创建时间：{formatCreatedAt(activity.createdAt)}（
													{getRelativeTime(activity.createdAt)}）
												</span>
											</div>
										</Link>
									);
								})
							) : (
								<div className="empty-state py-6">
									<Clock className="w-10 h-10 text-muted-foreground mb-2" />
									<p className="text-base text-muted-foreground">
										{recentActivities.length === 0
											? "暂无活动记录"
											: "未匹配到任务"}
									</p>
								</div>
							)}
						</div>
						{filteredActivities.length > 0 && (
							<div className="mt-4 flex items-center justify-between">
								<div className="text-xs text-muted-foreground">
									第 {activityPage} / {totalActivityPages} 页（每页{" "}
									{ACTIVITY_PAGE_SIZE} 条）
								</div>
								<div className="flex items-center gap-2">
									<Button
										variant="outline"
										size="sm"
										className="cyber-btn-outline h-8 px-3"
										disabled={activityPage <= 1}
										onClick={() =>
											setActivityPage((prev) => Math.max(prev - 1, 1))
										}
									>
										上一页
									</Button>
									<Button
										variant="outline"
										size="sm"
										className="cyber-btn-outline h-8 px-3"
										disabled={activityPage >= totalActivityPages}
										onClick={() =>
											setActivityPage((prev) =>
												Math.min(prev + 1, totalActivityPages),
											)
										}
									>
										下一页
									</Button>
								</div>
							</div>
						)}
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
							<Button
								variant="outline"
								className="w-full justify-start cyber-btn-outline h-10"
								onClick={() => setCreateProjectOpen(true)}
							>
								创建项目
							</Button>
							<Button
								variant="outline"
								className="w-full justify-start cyber-btn-outline h-10"
								onClick={() => setCreateAuditOpen(true)}
							>
								创建审计
							</Button>
						</div>
					</div>
				</div>
			</div>

			<Dialog
				open={createProjectOpen}
				onOpenChange={(open) => {
					setCreateProjectOpen(open);
					if (!open && !creatingProject) {
						resetCreateProjectForm();
					}
				}}
			>
				<DialogContent className="!w-[min(90vw,620px)] !max-w-none max-h-[85vh] overflow-y-auto p-0 gap-0 cyber-dialog border border-border rounded-lg">
					<DialogHeader className="px-5 py-4 border-b border-border bg-muted">
						<DialogTitle className="text-base font-bold uppercase tracking-wider">
							创建项目
						</DialogTitle>
					</DialogHeader>

					<div className="p-5 space-y-4">
						<div className="space-y-1.5">
							<Label className="font-mono font-bold uppercase text-base text-muted-foreground">
								项目名称 *
							</Label>
							<Input
								value={projectName}
								onChange={(e) => setProjectName(e.target.value)}
								placeholder="输入项目名称"
								className="h-11 text-base border-0 border-b border-border rounded-none px-0 bg-transparent focus-visible:ring-0 focus-visible:border-primary"
								disabled={creatingProject}
							/>
						</div>

						<div className="space-y-1.5">
							<Label className="font-mono font-bold uppercase text-base text-muted-foreground">
								描述
							</Label>
							<Textarea
								value={projectDescription}
								onChange={(e) => setProjectDescription(e.target.value)}
								placeholder="// 项目描述..."
								rows={3}
								className="cyber-input min-h-[80px]"
								disabled={creatingProject}
							/>
						</div>

						<div className="space-y-2">
							<Label className="font-mono font-bold uppercase text-base text-muted-foreground">
								项目压缩包 *
							</Label>
							<div className="cyber-input p-4 border-dashed border-2 border-border/60 hover:border-primary/60 transition-colors rounded-lg">
								<div className="flex items-center gap-3 mb-2">
									<Upload className="w-4 h-4 text-primary" />
									<p className="text-sm font-mono text-foreground">
										选择 ZIP / TAR / 7Z / RAR 压缩包
									</p>
								</div>
								<input
									type="file"
									accept=".zip,.tar,.tar.gz,.tar.bz2,.7z,.rar"
									onChange={handleProjectZipSelect}
									disabled={creatingProject}
									className="block w-full text-xs text-muted-foreground file:mr-3 file:py-1.5 file:px-3 file:border-0 file:rounded file:bg-primary/20 file:text-primary file:font-mono file:cursor-pointer"
								/>
								{projectZipFile && (
									<p className="text-xs text-emerald-400 mt-2 font-mono">
										已选择: {projectZipFile.name}
									</p>
								)}
							</div>
						</div>

						<div className="flex items-center justify-end gap-2 pt-2">
							<Button
								variant="outline"
								className="cyber-btn-outline"
								onClick={() => setCreateProjectOpen(false)}
								disabled={creatingProject}
							>
								取消
							</Button>
							<Button
								className="cyber-btn-primary"
								onClick={handleCreateProject}
								disabled={
									creatingProject || !projectName.trim() || !projectZipFile
								}
							>
								{creatingProject ? "创建中..." : "创建项目"}
							</Button>
						</div>
					</div>
				</DialogContent>
			</Dialog>

			<Dialog open={createAuditOpen} onOpenChange={setCreateAuditOpen}>
				<DialogContent className="!w-[min(90vw,680px)] !max-w-none max-h-[85vh] overflow-y-auto p-0 gap-0 cyber-dialog border border-border rounded-lg">
					<DialogHeader className="px-5 py-4 border-b border-border bg-muted">
						<DialogTitle className="text-base font-bold uppercase tracking-wider">
							创建审计任务
						</DialogTitle>
					</DialogHeader>

					<div className="p-5 space-y-4">
						<div className="space-y-2">
							<p className="text-xs font-mono uppercase tracking-wider text-muted-foreground">
								已导入项目
							</p>
							<Select
								value={selectedProjectId}
								onValueChange={setSelectedProjectId}
								disabled={projects.length === 0 || creatingAudit}
							>
								<SelectTrigger className="font-mono">
									<SelectValue
										placeholder={
											projects.length === 0
												? "暂无项目，请先创建项目"
												: "请选择项目"
										}
									/>
								</SelectTrigger>
								<SelectContent>
									{projects.map((project) => (
										<SelectItem key={project.id} value={project.id}>
											{project.name}（
											{project.source_type === "zip" ? "上传项目" : "远程仓库"}
											）
										</SelectItem>
									))}
								</SelectContent>
							</Select>
						</div>

						<AgentModeSelector
							value={auditMode}
							onChange={setAuditMode}
							staticTools={staticTools}
							onStaticToolsChange={setStaticTools}
							disabled={creatingAudit || !selectedProject}
						/>

						{auditMode === "static" &&
							selectedProject &&
							!isZipProject(selectedProject) && (
								<div className="p-3 border border-orange-500/40 bg-orange-500/10 rounded text-xs text-orange-300 font-mono">
									当前项目是远程仓库类型。静态分析仅支持源码归档项目，请先在项目详情上传源码归档。
								</div>
							)}

						<div className="flex items-center justify-end gap-2 pt-2">
							<Button
								variant="outline"
								className="cyber-btn-outline"
								onClick={() => setCreateAuditOpen(false)}
								disabled={creatingAudit}
							>
								取消
							</Button>
							<Button
								variant="outline"
								className="cyber-btn-outline"
								onClick={() => handleCreateAudit(false)}
								disabled={!canCreateAudit || creatingAudit}
							>
								{creatingAudit ? "创建中..." : "创建后返回"}
							</Button>
							<Button
								className="cyber-btn-primary"
								onClick={() => handleCreateAudit(true)}
								disabled={!canCreateAudit || creatingAudit}
							>
								{creatingAudit ? "创建中..." : "创建并进入任务"}
							</Button>
						</div>
					</div>
				</DialogContent>
			</Dialog>
		</div>
	);
}
