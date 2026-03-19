/**
 * Project Detail Page
 * Cyberpunk Terminal Aesthetic
 */

import {
	Activity,
	AlertTriangle,
	ArrowLeft,
	Bug,
	FileText,
	Loader2,
	Search,
} from "lucide-react";
import { useCallback, useEffect, useMemo, useState } from "react";
import { Link, useLocation, useNavigate, useParams } from "react-router-dom";
import { toast } from "sonner";
import CreateScanTaskDialog from "@/components/scan/CreateScanTaskDialog";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Progress } from "@/components/ui/progress";
import { Skeleton } from "@/components/ui/skeleton";
import {
	Table,
	TableBody,
	TableCell,
	TableHead,
	TableHeader,
	TableRow,
} from "@/components/ui/table";
import ProjectTaskFindingsDialog from "@/pages/project-detail/components/ProjectTaskFindingsDialog";
import ProjectPotentialVulnerabilitiesSection from "@/pages/project-detail/components/ProjectPotentialVulnerabilitiesSection";
import {
	buildProjectDetailPotentialTree,
	getProjectDetailPotentialTaskCategoryText,
	type ProjectDetailPotentialTaskNode,
} from "@/pages/project-detail/potentialVulnerabilities";
import {
	getProjectCardRecentTasks,
	type ProjectCardTaskFindingCategory,
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
	type PhpstanScanTask,
	getPhpstanScanTasks,
} from "@/shared/api/phpstan";
import {
	getOpengrepScanFindings,
	getOpengrepScanTasks,
	type OpengrepFinding,
	type OpengrepScanTask,
} from "@/shared/api/opengrep";
import { api } from "@/shared/api/database";
import type { AuditTask, Project } from "@/shared/types";
import { appendReturnTo } from "@/shared/utils/findingRoute";

const DETAIL_RECENT_TASK_LIMIT = 10;
const DETAIL_POTENTIAL_FINDINGS_FETCH_LIMIT = 200;

type PotentialStatus = "loading" | "ready" | "empty" | "failed";
type ProjectDescriptionStatus = "idle" | "generating" | "ready" | "failed";
type ProjectDescriptionSource = "llm" | "static" | null;

async function getAllOpengrepTaskFindings(taskId: string): Promise<OpengrepFinding[]> {
	const findings: OpengrepFinding[] = [];
	let skip = 0;

	while (true) {
		const page = await getOpengrepScanFindings({
			taskId,
			skip,
			limit: DETAIL_POTENTIAL_FINDINGS_FETCH_LIMIT,
		});
		if (!Array.isArray(page) || page.length === 0) break;
		findings.push(...page);
		if (page.length < DETAIL_POTENTIAL_FINDINGS_FETCH_LIMIT) break;
		skip += page.length;
	}

	return findings;
}

interface ProjectDescriptionSectionProps {
	description: string;
	status: ProjectDescriptionStatus;
	source: ProjectDescriptionSource;
	unsupported: boolean;
	onRetry: () => void;
}

interface ShouldAutoGenerateProjectDescriptionArgs {
	projectId: string | null;
	description: string | null | undefined;
	status: ProjectDescriptionStatus;
	isPageLoading: boolean;
	unsupported: boolean;
	lastRequestedProjectId: string | null;
}

export function shouldAutoGenerateProjectDescription({
	projectId,
	description,
	status,
	isPageLoading,
	unsupported,
	lastRequestedProjectId,
}: ShouldAutoGenerateProjectDescriptionArgs) {
	if (isPageLoading || !projectId || unsupported) return false;
	if (String(description || "").trim()) return false;
	if (status !== "idle") return false;
	if (lastRequestedProjectId === projectId) return false;
	return true;
}

function splitProjectDescription(description: string) {
	return String(description || "")
		.split(/\n{2,}/)
		.map((item) => item.trim())
		.filter(Boolean)
		.slice(0, 2);
}

export function ProjectDescriptionSection({
	description,
	status,
	source,
	unsupported,
	onRetry,
}: ProjectDescriptionSectionProps) {
	const paragraphs = splitProjectDescription(description);
	const hasDescription = paragraphs.length > 0;

	return (
		<section className="cyber-card p-5">
			<div className="flex flex-wrap items-start justify-between gap-3">
				<div className="flex items-center gap-2">
					<FileText className="w-4 h-4 text-sky-400" />
					<h2 className="text-sm font-semibold uppercase tracking-wider text-foreground">
						项目简介
					</h2>
				</div>
				{status === "ready" && source ? (
					<Badge className="cyber-badge-muted">
						{source === "llm" ? "LLM 生成" : "静态生成"}
					</Badge>
				) : null}
			</div>

			<div className="mt-4 space-y-3">
				{status === "generating" ? (
					<div className="space-y-3">
						<div className="flex items-center gap-2 text-sm text-sky-200">
							<Loader2 className="w-4 h-4 animate-spin" />
							<span>正在整理项目简介...</span>
						</div>
						<div className="space-y-2">
							<Skeleton className="h-4 w-full bg-slate-700/60" />
							<Skeleton className="h-4 w-[92%] bg-slate-700/60" />
							<Skeleton className="h-4 w-[78%] bg-slate-700/60" />
						</div>
					</div>
				) : null}

				{status === "ready" && hasDescription ? (
					<div className="space-y-3">
						{paragraphs.map((paragraph, index) => (
							<p
								key={`${index}:${paragraph.slice(0, 24)}`}
								className="text-sm leading-7 text-slate-200/90"
							>
								{paragraph}
							</p>
						))}
					</div>
				) : null}

				{status === "failed" ? (
					<div className="space-y-3">
						<p className="text-sm leading-6 text-rose-200/85">
							项目简介生成失败，请稍后重试。
						</p>
						<Button
							type="button"
							size="sm"
							variant="outline"
							className="cyber-btn-ghost h-8 px-3"
							onClick={onRetry}
						>
							重新生成
						</Button>
					</div>
				) : null}

				{status === "idle" && !hasDescription ? (
					<div className="space-y-2">
						<p className="text-sm leading-6 text-slate-300/80">
							暂未生成项目简介。
						</p>
						<p className="text-xs leading-5 text-muted-foreground">
							{unsupported
								? "当前项目暂不支持自动生成简介。"
								: "系统会根据项目结构自动生成简要介绍。"}
						</p>
					</div>
				) : null}
			</div>

			<p className="mt-4 text-xs uppercase tracking-[0.22em] text-muted-foreground">
				内容基于项目结构自动整理
			</p>
		</section>
	);
}

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
	const [phpstanTasks, setPhpstanTasks] = useState<PhpstanScanTask[]>([]);
	const [potentialTree, setPotentialTree] = useState<
		ProjectDetailPotentialTaskNode[]
	>([]);
	const [potentialTotalFindings, setPotentialTotalFindings] = useState(0);
	const [potentialStatus, setPotentialStatus] =
		useState<PotentialStatus>("loading");
	const [projectDescriptionStatus, setProjectDescriptionStatus] =
		useState<ProjectDescriptionStatus>("idle");
	const [projectDescriptionSource, setProjectDescriptionSource] =
		useState<ProjectDescriptionSource>(null);
	const [projectDescriptionUnsupported, setProjectDescriptionUnsupported] =
		useState(false);
	const [lastDescriptionRequestProjectId, setLastDescriptionRequestProjectId] =
		useState<string | null>(null);
	const [recentTaskTimeKeyword, setRecentTaskTimeKeyword] = useState("");
	const [loading, setLoading] = useState(true);
	const [showCreateScanTaskDialog, setShowCreateScanTaskDialog] = useState(false);
	const [selectedTaskFindings, setSelectedTaskFindings] = useState<{
		taskId: string;
		taskCategory: ProjectCardTaskFindingCategory;
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
			projectName: string,
			sourceAgentTaskPool: AgentTask[],
			sourceOpengrepTaskPool: OpengrepScanTask[],
		) => {
			setPotentialStatus("loading");
			setPotentialTree([]);
			setPotentialTotalFindings(0);

			try {
				const sourceOpengrepTasks = sourceOpengrepTaskPool
					.filter((task) => task.project_id === projectId)
					.sort(
						(a, b) =>
							new Date(b.created_at).getTime() -
							new Date(a.created_at).getTime(),
					);

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
					);

				if (sourceOpengrepTasks.length === 0 && sourceAgentTasks.length === 0) {
					setPotentialStatus("empty");
					return;
				}

				const staticFindingsResult = await Promise.allSettled(
					sourceOpengrepTasks.map((task) => getAllOpengrepTaskFindings(task.id)),
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

				const nextTree = buildProjectDetailPotentialTree({
					projectName,
					agentTasks: sourceAgentTasks,
					opengrepTasks: sourceOpengrepTasks,
					agentFindings: verifiedAgentFindings,
					opengrepFindings: staticFindings,
				});

				setPotentialTree(nextTree.tasks);
				setPotentialTotalFindings(nextTree.totalFindings);
				setPotentialStatus(nextTree.totalFindings > 0 ? "ready" : "empty");
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
			setPotentialTree([]);
			setPotentialTotalFindings(0);

			const [
				projectRes,
				auditTasksRes,
				agentTasksRes,
				staticTasksRes,
				gitleaksTasksRes,
				banditTasksRes,
				phpstanTasksRes,
			] = await Promise.allSettled([
				api.getProjectById(id),
				api.getAuditTasks(id),
				getAgentTasks({ project_id: id }),
				getOpengrepScanTasks({ projectId: id }),
				getGitleaksScanTasks({ projectId: id }),
				getBanditScanTasks({ projectId: id }),
				getPhpstanScanTasks({ projectId: id }),
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
			const nextPhpstanTasks =
				phpstanTasksRes.status === "fulfilled" &&
				Array.isArray(phpstanTasksRes.value)
					? phpstanTasksRes.value
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
			if (phpstanTasksRes.status !== "fulfilled") {
				console.warn("Failed to load phpstan tasks:", phpstanTasksRes.reason);
			}

			setAuditTasks(nextAuditTasks);
			setAgentTasks(nextAgentTasks);
			setStaticTasks(nextStaticTasks);
			setGitleaksTasks(nextGitleaksTasks);
			setBanditTasks(nextBanditTasks);
			setPhpstanTasks(nextPhpstanTasks);

			const projectName =
				projectRes.status === "fulfilled"
					? String(projectRes.value?.name || "")
					: "";
			void fetchProjectPotentialVulnerabilities(
				id,
				projectName,
				nextAgentTasks,
				nextStaticTasks,
			);
		} catch (error) {
			console.error("Failed to load project data:", error);
			toast.error("加载项目数据失败");
			setPotentialStatus("failed");
			setPotentialTree([]);
			setPotentialTotalFindings(0);
		} finally {
			setLoading(false);
		}
	}, [fetchProjectPotentialVulnerabilities, id]);

	useEffect(() => {
		if (!id) return;
		void loadProjectData();
	}, [id, loadProjectData]);

	useEffect(() => {
		setProjectDescriptionStatus("idle");
		setProjectDescriptionSource(null);
		setProjectDescriptionUnsupported(false);
		setLastDescriptionRequestProjectId(null);
	}, [id]);

	useEffect(() => {
		if (!project) return;
		if (String(project.description || "").trim()) {
			setProjectDescriptionStatus("ready");
			setProjectDescriptionUnsupported(false);
		}
	}, [project]);

	const generateProjectDescription = useCallback(async () => {
		if (!project?.id) return;

		setProjectDescriptionStatus("generating");
		setProjectDescriptionSource(null);
		setProjectDescriptionUnsupported(false);
		setLastDescriptionRequestProjectId(project.id);

		try {
			const result = await api.generateStoredProjectDescription(project.id);
			setProject((previous) =>
				previous && previous.id === project.id
					? {
							...previous,
							description: result.description,
					  }
					: previous,
			);
			setProjectDescriptionSource(result.source);
			setProjectDescriptionStatus("ready");
		} catch (error) {
			const statusCode =
				typeof error === "object" &&
				error !== null &&
				"response" in error &&
				typeof (error as { response?: { status?: number } }).response?.status ===
					"number"
					? (error as { response?: { status?: number } }).response?.status
					: null;

			if (statusCode === 400 || statusCode === 404) {
				setProjectDescriptionUnsupported(true);
				setProjectDescriptionStatus("idle");
				return;
			}

			console.error("Failed to generate project description:", error);
			setProjectDescriptionStatus("failed");
		}
	}, [project]);

	useEffect(() => {
		if (
			!shouldAutoGenerateProjectDescription({
				projectId: project?.id ?? null,
				description: project?.description,
				status: projectDescriptionStatus,
				isPageLoading: loading,
				unsupported: projectDescriptionUnsupported,
				lastRequestedProjectId: lastDescriptionRequestProjectId,
			})
		) {
			return;
		}

		void generateProjectDescription();
	}, [
		generateProjectDescription,
		lastDescriptionRequestProjectId,
		loading,
		project?.description,
		project?.id,
		projectDescriptionStatus,
		projectDescriptionUnsupported,
	]);

	const recentTasks = useMemo(() => {
		if (!id) return [];
		return getProjectCardRecentTasks({
			projectId: id,
			auditTasks,
			agentTasks,
			opengrepTasks: staticTasks,
			gitleaksTasks,
			banditTasks,
			phpstanTasks,
			limit: DETAIL_RECENT_TASK_LIMIT,
		});
	}, [id, auditTasks, agentTasks, staticTasks, gitleaksTasks, banditTasks, phpstanTasks]);

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

	const openTaskFindingsDialog = useCallback(
		(
			taskId: string,
			taskCategory: ProjectCardTaskFindingCategory,
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
	const defaultExpandedPotentialKeys = useMemo(
		() => potentialTree.map((task) => task.nodeKey),
		[potentialTree],
	);

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
					<Badge className="cyber-badge-success">可用</Badge>
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
				<ProjectDescriptionSection
					description={project.description || ""}
					status={projectDescriptionStatus}
					source={projectDescriptionSource}
					unsupported={projectDescriptionUnsupported}
					onRetry={() => {
						void generateProjectDescription();
					}}
				/>

				{/* <div className="cyber-card p-5"> */}
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
												getProjectDetailPotentialTaskCategoryText(taskCategory),
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
				{/* </div> */}

				<ProjectPotentialVulnerabilitiesSection
					status={potentialStatus}
					tree={potentialTree}
					totalFindings={potentialTotalFindings}
					currentRoute={currentRoute}
					initialExpandedKeys={defaultExpandedPotentialKeys}
					formatDate={formatDate}
				/>
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
