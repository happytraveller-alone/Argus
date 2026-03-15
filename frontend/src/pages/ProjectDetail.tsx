/**
 * Project Detail Page
 * Cyberpunk Terminal Aesthetic
 */

import {
	Activity,
	AlertTriangle,
	ArrowLeft,
	Bug,
	Search,
	Shield,
} from "lucide-react";
import { useCallback, useEffect, useMemo, useState } from "react";
import { Link, useLocation, useNavigate, useParams } from "react-router-dom";
import { toast } from "sonner";
import CreateScanTaskDialog from "@/components/scan/CreateScanTaskDialog";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Progress } from "@/components/ui/progress";
import {
	Table,
	TableBody,
	TableCell,
	TableHead,
	TableHeader,
	TableRow,
} from "@/components/ui/table";
import ProjectTaskFindingsDialog from "@/pages/project-detail/components/ProjectTaskFindingsDialog";
import {
	getProjectCardPotentialVulnerabilities,
	getProjectCardRecentTasks,
	type ProjectCardPotentialVulnerability,
} from "@/features/projects/services/projectCardPreview";
import { resolveSourceModeFromTaskMeta } from "@/features/tasks/services/taskActivities";
import {
	type AgentFinding,
	type AgentTask,
	getAgentFindings,
	getAgentTasks,
} from "@/shared/api/agentTasks";
import {
	type GitleaksScanTask,
	getGitleaksScanTasks,
} from "@/shared/api/gitleaks";
import {
	type BanditScanTask,
	getBanditScanTasks,
} from "@/shared/api/bandit";
import {
	getOpengrepScanFindings,
	getOpengrepScanTasks,
	type OpengrepFinding,
	type OpengrepScanTask,
} from "@/shared/api/opengrep";
import { api } from "@/shared/config/database";
import type { AuditTask, Project } from "@/shared/types";
import { appendReturnTo } from "@/shared/utils/findingRoute";

const DETAIL_RECENT_TASK_LIMIT = 10;
const DETAIL_POTENTIAL_TOP_LIMIT = 10;
const DETAIL_POTENTIAL_SOURCE_TASK_LIMIT = 10;
const DETAIL_POTENTIAL_FINDINGS_FETCH_LIMIT = 200;

type PotentialStatus = "loading" | "ready" | "empty" | "failed";

export default function ProjectDetail() {
	const { id } = useParams<{ id: string }>();
	const location = useLocation();
	const navigate = useNavigate();
	const [project, setProject] = useState<Project | null>(null);
	const [auditTasks, setAuditTasks] = useState<AuditTask[]>([]);
	const [agentTasks, setAgentTasks] = useState<AgentTask[]>([]);
	const [staticTasks, setStaticTasks] = useState<OpengrepScanTask[]>([]);
	const [gitleaksTasks, setGitleaksTasks] = useState<GitleaksScanTask[]>([]);
	const [banditTasks, setBanditTasks] = useState<BanditScanTask[]>([]);
	const [potentialVulnerabilities, setPotentialVulnerabilities] = useState<
		ProjectCardPotentialVulnerability[]
	>([]);
	const [potentialStatus, setPotentialStatus] =
		useState<PotentialStatus>("loading");
	const [recentTaskTimeKeyword, setRecentTaskTimeKeyword] = useState("");
	const [loading, setLoading] = useState(true);
	const [showCreateScanTaskDialog, setShowCreateScanTaskDialog] = useState(false);
	const [selectedTaskFindings, setSelectedTaskFindings] = useState<{
		taskId: string;
		taskCategory: ProjectCardPotentialVulnerability["taskCategory"];
		taskLabel: string;
	} | null>(null);

	const fallbackBackPath = "/projects#project-browser";
	const sourceFromState =
		typeof (location.state as { from?: unknown } | null)?.from === "string"
			? ((location.state as { from?: string }).from ?? "")
			: "";
	const normalizedSourceFrom = sourceFromState.startsWith("/")
		? sourceFromState
		: "";
	const backTarget =
		normalizedSourceFrom && normalizedSourceFrom !== location.pathname
			? normalizedSourceFrom
			: fallbackBackPath;
	const currentRoute = `${location.pathname}${location.search}`;
	const withStaticReturnTo = useCallback(
		(route: string, taskKind: string) => {
			if (taskKind !== "static") return route;
			return appendReturnTo(route, currentRoute);
		},
		[currentRoute],
	);

	const handleBack = () => {
		navigate(backTarget);
	};

	const fetchProjectPotentialVulnerabilities = useCallback(
		async (
			projectId: string,
			sourceAgentTaskPool: AgentTask[],
			sourceOpengrepTaskPool: OpengrepScanTask[],
		) => {
			setPotentialStatus("loading");
			setPotentialVulnerabilities([]);

			try {
				const sourceOpengrepTasks = sourceOpengrepTaskPool
					.filter((task) => task.project_id === projectId)
					.sort(
						(a, b) =>
							new Date(b.created_at).getTime() -
							new Date(a.created_at).getTime(),
					)
					.slice(0, DETAIL_POTENTIAL_SOURCE_TASK_LIMIT);

				const sourceAgentTasks = sourceAgentTaskPool
					.filter((task) => {
						if (task.project_id !== projectId) return false;
						const verifiedCount = Math.max(Number(task.verified_count ?? 0), 0);
						if (verifiedCount <= 0) return false;
						const sourceMode = resolveSourceModeFromTaskMeta(
							"intelligent_audit",
							task.name,
							task.description,
						);
						return sourceMode === "intelligent" || sourceMode === "hybrid";
					})
					.sort(
						(a, b) =>
							new Date(b.created_at).getTime() -
							new Date(a.created_at).getTime(),
					)
					.slice(0, DETAIL_POTENTIAL_SOURCE_TASK_LIMIT);

				if (sourceOpengrepTasks.length === 0 && sourceAgentTasks.length === 0) {
					setPotentialStatus("empty");
					return;
				}

				const staticFindingsResult = await Promise.allSettled(
					sourceOpengrepTasks.map((task) =>
						getOpengrepScanFindings({
							taskId: task.id,
							limit: DETAIL_POTENTIAL_FINDINGS_FETCH_LIMIT,
							confidence: "HIGH",
						}),
					),
				);

				const staticFindings: OpengrepFinding[] = staticFindingsResult.flatMap(
					(result, index) => {
						if (result.status !== "fulfilled" || !Array.isArray(result.value)) {
							return [];
						}
						const fallbackTaskId = sourceOpengrepTasks[index]?.id || "";
						return result.value.map((finding) => ({
							...finding,
							scan_task_id: finding.scan_task_id || fallbackTaskId,
						}));
					},
				);

				const agentFindingsResult = await Promise.allSettled(
					sourceAgentTasks.map((task) =>
						getAgentFindings(task.id, {
							is_verified: true,
							include_false_positive: false,
						}),
					),
				);

				const verifiedAgentFindings: AgentFinding[] =
					agentFindingsResult.flatMap((result) => {
						if (result.status !== "fulfilled" || !Array.isArray(result.value)) {
							return [];
						}
						return result.value;
					});
				const agentTaskCategoryMap: Record<string, "intelligent" | "hybrid"> =
					{};
				for (const task of sourceAgentTasks) {
					const mode = resolveSourceModeFromTaskMeta(
						"intelligent_audit",
						task.name,
						task.description,
					);
					agentTaskCategoryMap[task.id] =
						mode === "hybrid" ? "hybrid" : "intelligent";
				}

				const topVulnerabilities = getProjectCardPotentialVulnerabilities({
					opengrepFindings: staticFindings,
					verifiedAgentFindings,
					agentTaskCategoryMap,
					limit: DETAIL_POTENTIAL_TOP_LIMIT,
				});

				setPotentialVulnerabilities(topVulnerabilities);
				setPotentialStatus(topVulnerabilities.length > 0 ? "ready" : "empty");
			} catch {
				setPotentialStatus("failed");
			}
		},
		[],
	);

	const loadProjectData = useCallback(async () => {
		if (!id) return;

		try {
			setLoading(true);
			setPotentialStatus("loading");
			setPotentialVulnerabilities([]);

			const [
				projectRes,
				auditTasksRes,
				agentTasksRes,
				staticTasksRes,
				gitleaksTasksRes,
				banditTasksRes,
			] = await Promise.allSettled([
				api.getProjectById(id),
				api.getAuditTasks(id),
				getAgentTasks({ project_id: id }),
				getOpengrepScanTasks({ projectId: id }),
				getGitleaksScanTasks({ projectId: id }),
				getBanditScanTasks({ projectId: id }),
			]);

			const nextAuditTasks =
				auditTasksRes.status === "fulfilled" &&
				Array.isArray(auditTasksRes.value)
					? auditTasksRes.value
					: [];
			const nextAgentTasks =
				agentTasksRes.status === "fulfilled" &&
				Array.isArray(agentTasksRes.value)
					? agentTasksRes.value
					: [];
			const nextStaticTasks =
				staticTasksRes.status === "fulfilled" &&
				Array.isArray(staticTasksRes.value)
					? staticTasksRes.value
					: [];
			const nextGitleaksTasks =
				gitleaksTasksRes.status === "fulfilled" &&
				Array.isArray(gitleaksTasksRes.value)
					? gitleaksTasksRes.value
					: [];
			const nextBanditTasks =
				banditTasksRes.status === "fulfilled" &&
				Array.isArray(banditTasksRes.value)
					? banditTasksRes.value
					: [];

			if (projectRes.status === "fulfilled") {
				setProject(projectRes.value);
			} else {
				console.error("Failed to load project:", projectRes.reason);
				setProject(null);
			}

			if (auditTasksRes.status !== "fulfilled") {
				console.error("Failed to load scan tasks:", auditTasksRes.reason);
			}
			if (agentTasksRes.status !== "fulfilled") {
				console.warn("Failed to load agent tasks:", agentTasksRes.reason);
			}
			if (staticTasksRes.status !== "fulfilled") {
				console.warn("Failed to load static tasks:", staticTasksRes.reason);
			}
			if (gitleaksTasksRes.status !== "fulfilled") {
				console.warn("Failed to load gitleaks tasks:", gitleaksTasksRes.reason);
			}
			if (banditTasksRes.status !== "fulfilled") {
				console.warn("Failed to load bandit tasks:", banditTasksRes.reason);
			}

			setAuditTasks(nextAuditTasks);
			setAgentTasks(nextAgentTasks);
			setStaticTasks(nextStaticTasks);
			setGitleaksTasks(nextGitleaksTasks);
			setBanditTasks(nextBanditTasks);

			void fetchProjectPotentialVulnerabilities(
				id,
				nextAgentTasks,
				nextStaticTasks,
			);
		} catch (error) {
			console.error("Failed to load project data:", error);
			toast.error("加载项目数据失败");
			setPotentialStatus("failed");
			setPotentialVulnerabilities([]);
		} finally {
			setLoading(false);
		}
	}, [fetchProjectPotentialVulnerabilities, id]);

	useEffect(() => {
		if (!id) return;
		void loadProjectData();
	}, [id, loadProjectData]);

	const recentTasks = useMemo(() => {
		if (!id) return [];
		return getProjectCardRecentTasks({
			projectId: id,
			auditTasks,
			agentTasks,
			opengrepTasks: staticTasks,
			gitleaksTasks,
			banditTasks,
			limit: DETAIL_RECENT_TASK_LIMIT,
		});
	}, [id, auditTasks, agentTasks, staticTasks, gitleaksTasks, banditTasks]);

	const handleRunScan = () => {
		setShowCreateScanTaskDialog(true);
	};

	const handleTaskCreated = () => {
		toast.success("扫描任务已创建", {
			description:
				"因为网络和代码文件大小等因素，扫描时长通常至少需要1分钟，请耐心等待...",
			duration: 5000,
		});
		void loadProjectData();
	};

	const getStatusBadge = (status: string) => {
		switch (status) {
			case "completed":
				return <Badge className="cyber-badge-success">完成</Badge>;
			case "running":
				return <Badge className="cyber-badge-info">运行中</Badge>;
			case "failed":
				return <Badge className="cyber-badge-danger">失败</Badge>;
			case "interrupted":
				return (
					<Badge className="bg-orange-500/20 text-orange-300 border-orange-500/30">
						中断
					</Badge>
				);
			case "cancelled":
				return <Badge className="cyber-badge-muted">已取消</Badge>;
			default:
				return <Badge className="cyber-badge-muted">等待中</Badge>;
		}
	};

	const getTaskProgressBarClassName = (status: string) => {
		const normalized = String(status || "")
			.trim()
			.toLowerCase();
		if (normalized === "running") return "[&>div]:bg-sky-500";
		if (normalized === "completed") return "[&>div]:bg-emerald-500";
		return "[&>div]:bg-slate-400";
	};

	const getVulnerabilitySeverityBadgeClassName = (
		severity: ProjectCardPotentialVulnerability["severity"],
	) => {
		if (severity === "CRITICAL") return "cyber-badge-danger";
		if (severity === "HIGH") return "cyber-badge-warning";
		if (severity === "MEDIUM") return "cyber-badge-info";
		if (severity === "LOW") return "cyber-badge-muted";
		return "cyber-badge-muted";
	};

	const getVulnerabilitySeverityText = (
		severity: ProjectCardPotentialVulnerability["severity"],
	) => {
		if (severity === "CRITICAL") return "严重";
		if (severity === "HIGH") return "高危";
		if (severity === "MEDIUM") return "中危";
		if (severity === "LOW") return "低危";
		return "未知";
	};

	const getVulnerabilityConfidenceText = (
		confidence: ProjectCardPotentialVulnerability["confidence"],
	) => {
		if (confidence === "HIGH") return "高";
		if (confidence === "MEDIUM") return "中";
		if (confidence === "LOW") return "低";
		return "-";
	};

	const getVulnerabilityConfidenceBadgeClassName = (
		confidence: ProjectCardPotentialVulnerability["confidence"],
	) => {
		if (confidence === "HIGH") {
			return "bg-emerald-500/20 text-emerald-300 border-emerald-500/30";
		}
		if (confidence === "MEDIUM") {
			return "bg-amber-500/20 text-amber-300 border-amber-500/30";
		}
		if (confidence === "LOW") {
			return "bg-sky-500/20 text-sky-300 border-sky-500/30";
		}
		return "cyber-badge-muted";
	};

	const getTaskCategoryBadgeClassName = (
		category: ProjectCardPotentialVulnerability["taskCategory"],
	) => {
		if (category === "static")
			return "bg-sky-500/20 text-sky-300 border-sky-500/30";
		if (category === "intelligent") {
			return "bg-emerald-500/20 text-emerald-300 border-emerald-500/30";
		}
		return "bg-amber-500/20 text-amber-300 border-amber-500/30";
	};

	const getTaskCategoryText = (
		category: ProjectCardPotentialVulnerability["taskCategory"],
	) => {
		if (category === "static") return "静态扫描";
		if (category === "intelligent") return "智能扫描";
		return "混合扫描";
	};

	const openTaskFindingsDialog = useCallback(
		(
			taskId: string,
			taskCategory: ProjectCardPotentialVulnerability["taskCategory"],
			taskLabel: string,
		) => {
			setSelectedTaskFindings({
				taskId,
				taskCategory,
				taskLabel,
			});
		},
		[],
	);

	const toProjectRelativePath = useCallback(
		(filePath: string) => {
			const normalizedPath = String(filePath || "")
				.trim()
				.replace(/\\/g, "/");
			if (!normalizedPath) return "-";

			const trimmed = normalizedPath.replace(/^\/+/, "");
			const projectName = String(project?.name || "")
				.trim()
				.replace(/\\/g, "/");
			if (!projectName) return trimmed || "-";

			const pathLower = normalizedPath.toLowerCase();
			const projectLower = projectName.toLowerCase();
			const marker = `/${projectLower}/`;
			const markerIndex = pathLower.lastIndexOf(marker);
			if (markerIndex >= 0) {
				const relative = normalizedPath.slice(markerIndex + marker.length);
				return relative || "-";
			}

			if (pathLower.startsWith(`${projectLower}/`)) {
				return normalizedPath.slice(projectName.length + 1) || "-";
			}

			if (pathLower === projectLower) return "-";

			return trimmed || "-";
		},
		[project?.name],
	);

	const toStaticRelativePath = useCallback(
		(filePath: string) => {
			const normalizedPath = String(filePath || "")
				.trim()
				.replace(/\\/g, "/");
			if (!normalizedPath) return "-";

			const trimmed = normalizedPath.replace(/^\/+/, "");
			if (!trimmed) return "-";

			const segments = trimmed.split("/").filter(Boolean);
			if (segments.length === 0) return "-";

			const normalizedProjectName = String(project?.name || "")
				.trim()
				.replace(/\\/g, "/")
				.toLowerCase();

			if (normalizedProjectName) {
				const projectRootIndex = segments.findIndex((segment) => {
					const normalizedSegment = segment.toLowerCase();
					return (
						normalizedSegment === normalizedProjectName ||
						normalizedSegment.startsWith(`${normalizedProjectName}-`) ||
						normalizedSegment.startsWith(`${normalizedProjectName}_`) ||
						normalizedSegment.startsWith(`${normalizedProjectName}.`)
					);
				});

				if (projectRootIndex >= 0) {
					if (projectRootIndex >= segments.length - 1) return "-";
					return segments.slice(projectRootIndex + 1).join("/");
				}
			}

			const sourceRootSegments = new Set([
				"src",
				"include",
				"lib",
				"app",
				"apps",
				"test",
				"tests",
			]);
			const sourceRootIndex = segments.findIndex((segment) =>
				sourceRootSegments.has(segment.toLowerCase()),
			);
			if (sourceRootIndex >= 0) {
				return segments.slice(sourceRootIndex).join("/");
			}

			return trimmed || "-";
		},
		[project?.name],
	);

	const formatPotentialLocation = useCallback(
		(
			filePath: string,
			line: number | null,
			source: ProjectCardPotentialVulnerability["source"],
		) => {
			const relativePath =
				source === "static"
					? toStaticRelativePath(filePath)
					: toProjectRelativePath(filePath);
			if (typeof line === "number" && Number.isFinite(line) && line > 0) {
				return `${relativePath}:${line}`;
			}
			return relativePath;
		},
		[toProjectRelativePath, toStaticRelativePath],
	);

	const formatDate = useCallback((dateString: string) => {
		return new Date(dateString).toLocaleDateString("zh-CN", {
			year: "numeric",
			month: "short",
			day: "numeric",
			hour: "2-digit",
			minute: "2-digit",
		});
	}, []);

	const formatRecentTaskMetricValue = (value: number | null) => {
		if (value === null || !Number.isFinite(value)) return "--";
		return value.toLocaleString();
	};

	const filteredRecentTasks = useMemo(() => {
		const keyword = recentTaskTimeKeyword.trim().toLowerCase();
		if (!keyword) return recentTasks;

		const normalizeForFuzzyMatch = (value: string) =>
			value.toLowerCase().replace(/[\s/:\-._年月日时分秒]+/g, "");

		const normalizedKeyword = normalizeForFuzzyMatch(keyword);

		return recentTasks.filter((task) => {
			const raw = String(task.createdAt || "");
			const formatted = formatDate(task.createdAt);
			const searchable = `${raw} ${formatted}`.toLowerCase();
			const normalizedSearchable = normalizeForFuzzyMatch(searchable);
			return (
				searchable.includes(keyword) ||
				(!!normalizedKeyword &&
					normalizedSearchable.includes(normalizedKeyword))
			);
		});
	}, [formatDate, recentTaskTimeKeyword, recentTasks]);

	const potentialStatusMessage = useMemo(() => {
		if (potentialStatus === "loading") return "加载中...";
		if (potentialStatus === "failed") return "加载失败";
		if (potentialStatus === "empty") return "暂无潜在漏洞";
		return null;
	}, [potentialStatus]);

	if (loading) {
		return (
			<div className="flex items-center justify-center min-h-[60vh]">
				<div className="text-center space-y-4">
					<div className="loading-spinner mx-auto" />
					<p className="text-muted-foreground font-mono text-sm uppercase tracking-wider">
						加载项目数据...
					</p>
				</div>
			</div>
		);
	}

	if (!project) {
		return (
			<div className="flex items-center justify-center min-h-[60vh]">
				<div className="cyber-card p-8 text-center">
					<AlertTriangle className="w-16 h-16 text-rose-400 mx-auto mb-4" />
					<h2 className="text-2xl font-bold text-foreground mb-2 uppercase">
						项目未找到
					</h2>
					<p className="text-muted-foreground mb-4 font-mono">
						请检查项目ID是否正确
					</p>
					<Button className="cyber-btn-primary" onClick={handleBack}>
						<ArrowLeft className="w-4 h-4 mr-2" />
						返回
					</Button>
				</div>
			</div>
		);
	}

	return (
		<div className="space-y-6 p-6 cyber-bg-elevated min-h-screen font-mono relative">
			<div className="absolute inset-0 cyber-grid-subtle pointer-events-none" />

			<div className="relative z-10 flex items-center justify-between">
				<div className="flex items-center gap-3">
					<h1 className="text-2xl font-bold text-foreground uppercase tracking-wider">
						{project.name}
					</h1>
					<Badge
						className={`${project.is_active ? "cyber-badge-success" : "cyber-badge-muted"}`}
					>
						{project.is_active ? "活跃" : "暂停"}
					</Badge>
				</div>

				<div className="flex items-center space-x-3">
					<Button
						variant="outline"
						size="sm"
						className="cyber-btn-ghost h-10 px-3 flex items-center justify-center gap-2"
						onClick={handleBack}
					>
						<ArrowLeft className="w-5 h-5" />
						返回
					</Button>
					{/* <Button onClick={handleRunScan} className="cyber-btn-primary">
						<Shield className="w-4 h-4 mr-2" />
						启动扫描
					</Button> */}
				</div>
			</div>

			<div className="relative z-10 space-y-4 mt-6">
				<div className="cyber-card p-5">
					<div className="flex flex-wrap items-center justify-between gap-3 mb-3">
						<div className="flex items-center gap-2">
							<Activity className="w-4 h-4 text-sky-400" />
							<h3 className="text-sm font-semibold uppercase tracking-wider">
								最近任务
							</h3>
						</div>
						<div className="relative w-full sm:w-[320px]">
							<Search className="absolute left-2.5 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-muted-foreground" />
							<Input
								value={recentTaskTimeKeyword}
								onChange={(event) =>
									setRecentTaskTimeKeyword(event.target.value)
								}
								placeholder="按时间搜索"
								className="h-8 pl-8 text-xs"
							/>
						</div>
					</div>

					<Table className="table-fixed">
						<TableHeader>
							<TableRow>
								<TableHead className="w-[18%]">类型</TableHead>
								<TableHead className="w-[24%]">创建时间</TableHead>
								<TableHead className="w-[20%]">进度</TableHead>
								<TableHead className="w-[16%]">状态</TableHead>
								<TableHead className="w-[10%]">漏洞</TableHead>
								<TableHead className="w-[20%]">操作</TableHead>
							</TableRow>
						</TableHeader>
						<TableBody>
							{filteredRecentTasks.length > 0 ? (
								filteredRecentTasks.map((task) => {
									const progressPercent = Math.max(
										0,
										Math.min(100, Math.round(task.progressPercent)),
									);
									return (
										<TableRow key={`${task.kind}:${task.id}`}>
											<TableCell className="text-sm text-foreground">
												{task.scanTypeLabel}
											</TableCell>
											<TableCell className="text-sm text-muted-foreground">
												{formatDate(task.createdAt)}
											</TableCell>
											<TableCell>
												<div className="space-y-1.5">
													<div className="text-xs text-muted-foreground">
														{progressPercent}%
													</div>
													<Progress
														value={progressPercent}
														className={`h-1.5 bg-muted ${getTaskProgressBarClassName(task.status)}`}
													/>
												</div>
											</TableCell>
											<TableCell>{getStatusBadge(task.status)}</TableCell>
											<TableCell className="text-sm text-muted-foreground">
												{formatRecentTaskMetricValue(task.vulnerabilities)}
											</TableCell>
											<TableCell>
													<div className="flex items-center gap-2 whitespace-nowrap">
														<Button
															asChild
															size="sm"
															variant="outline"
															className="cyber-btn-ghost h-7 px-3"
														>
															<Link to={withStaticReturnTo(task.route, task.kind)}>
																任务详情
															</Link>
														</Button>
								{task.supportsFindingsDetail && task.taskCategory ? (
															<Button
																type="button"
																size="sm"
																variant="outline"
																className="cyber-btn-ghost h-7 px-3"
																onClick={() => {
																	const taskCategory = task.taskCategory;
																	if (!taskCategory) return;
																	openTaskFindingsDialog(
																		task.id,
																		taskCategory,
																		getTaskCategoryText(taskCategory),
																	);
																}}
															>
																漏洞详情
															</Button>
														) : (
															<span title={task.findingsButtonDisabledReason || undefined}>
																<Button
																	type="button"
																	size="sm"
																	variant="outline"
																	className="cyber-btn-ghost h-7 px-3"
																	disabled
																>
																	漏洞详情
																</Button>
															</span>
														)}
													</div>
												</TableCell>
										</TableRow>
									);
								})
							) : (
								<TableRow>
									<TableCell
										colSpan={6}
										className="py-10 text-center text-sm text-muted-foreground"
									>
										{recentTaskTimeKeyword.trim() ? "未匹配到任务" : "暂无任务"}
									</TableCell>
								</TableRow>
							)}
						</TableBody>
					</Table>
				</div>

				<div className="cyber-card p-5">
					<div className="flex items-center gap-2 mb-3">
						<Bug className="w-4 h-4 text-amber-400" />
						<h3 className="text-sm font-semibold uppercase tracking-wider">
							潜在漏洞
						</h3>
					</div>

					<Table className="table-fixed">
						<TableHeader>
							<TableRow>
								<TableHead className="w-[16%] text-left whitespace-nowrap">
									类型
								</TableHead>
								<TableHead className="w-[28%] text-left whitespace-nowrap">
									位置
								</TableHead>
								<TableHead className="w-[16%] px-3 text-center whitespace-nowrap">
									所属任务
								</TableHead>
								<TableHead className="w-[10%] px-3 text-center whitespace-nowrap">
									危害
								</TableHead>
								<TableHead className="w-[10%] px-3 text-center whitespace-nowrap">
									置信度
								</TableHead>
								<TableHead className="w-[12%] text-center whitespace-nowrap">
									操作
								</TableHead>
							</TableRow>
						</TableHeader>
						<TableBody>
							{potentialStatusMessage ? (
								<TableRow>
									<TableCell
										colSpan={6}
										className="py-10 text-center text-sm text-muted-foreground"
									>
										{potentialStatusMessage}
									</TableCell>
								</TableRow>
							) : (
								potentialVulnerabilities.map((item) => (
									<TableRow key={`${item.taskId}:${item.id}`}>
										<TableCell
											className="text-left text-sm text-foreground whitespace-nowrap overflow-hidden text-ellipsis"
											title={`${item.cweLabel} ${item.title}`}
										>
											{item.cweLabel}
										</TableCell>
										<TableCell
											className="text-left text-xs text-muted-foreground whitespace-nowrap overflow-hidden text-ellipsis"
											title={formatPotentialLocation(
												item.filePath,
												item.line,
												item.source,
											)}
										>
											{formatPotentialLocation(
												item.filePath,
												item.line,
												item.source,
											)}
										</TableCell>
										<TableCell className="px-3 text-center whitespace-nowrap">
											<Badge
												className={getTaskCategoryBadgeClassName(
													item.taskCategory,
												)}
											>
												{getTaskCategoryText(item.taskCategory)}
											</Badge>
										</TableCell>
										<TableCell className="px-3 text-center whitespace-nowrap">
											<Badge
												className={getVulnerabilitySeverityBadgeClassName(
													item.severity,
												)}
											>
												{getVulnerabilitySeverityText(item.severity)}
											</Badge>
										</TableCell>
										<TableCell className="px-3 text-center whitespace-nowrap">
											<Badge
												className={getVulnerabilityConfidenceBadgeClassName(
													item.confidence,
												)}
											>
												{getVulnerabilityConfidenceText(item.confidence)}
											</Badge>
										</TableCell>
										<TableCell className="whitespace-nowrap">
											<div className="flex items-center justify-center">
												<Button
													asChild
													size="sm"
													variant="outline"
													className="cyber-btn-ghost h-7 px-3"
												>
													<Link to={appendReturnTo(item.route, currentRoute)}>
														详情
													</Link>
												</Button>
											</div>
										</TableCell>
									</TableRow>
								))
							)}
						</TableBody>
					</Table>
				</div>
			</div>

			<CreateScanTaskDialog
				open={showCreateScanTaskDialog}
				onOpenChange={setShowCreateScanTaskDialog}
				onTaskCreated={handleTaskCreated}
				preselectedProjectId={id}
			/>
			<ProjectTaskFindingsDialog
				open={selectedTaskFindings !== null}
				onOpenChange={(nextOpen) => {
					if (!nextOpen) {
						setSelectedTaskFindings(null);
					}
				}}
				taskId={selectedTaskFindings?.taskId || ""}
				taskCategory={selectedTaskFindings?.taskCategory || "static"}
				projectName={project.name}
				returnTo={currentRoute}
				taskLabel={selectedTaskFindings?.taskLabel || "任务"}
			/>
		</div>
	);
}
