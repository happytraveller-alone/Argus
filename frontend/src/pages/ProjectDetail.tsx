/**
 * Project Detail Page
 * Cyberpunk Terminal Aesthetic
 */

import {
	Activity,
	AlertTriangle,
	ArrowLeft,
	FileText,
	Loader2,
} from "lucide-react";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import type { ColumnDef } from "@tanstack/react-table";
import { Link, useLocation, useNavigate, useParams } from "react-router-dom";
import { toast } from "sonner";
import CreateScanTaskDialog from "@/components/scan/CreateScanTaskDialog";
import {
	DataTable,
	type AppColumnDef,
	type DataTableQueryState,
} from "@/components/data-table";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import ProjectTaskFindingsDialog from "@/pages/project-detail/components/ProjectTaskFindingsDialog";
import ProjectPotentialVulnerabilitiesSection from "@/pages/project-detail/components/ProjectPotentialVulnerabilitiesSection";
import {
	buildProjectDetailPotentialTree,
	flattenProjectDetailPotentialFindings,
	getProjectDetailPotentialTaskCategoryText,
	type ProjectDetailPotentialListItem,
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
import type { Project } from "@/shared/types";
import { appendReturnTo } from "@/shared/utils/findingRoute";

const DETAIL_RECENT_TASK_LIMIT = 10;
const DETAIL_POTENTIAL_FINDINGS_FETCH_LIMIT = 200;
const DETAIL_POTENTIAL_FINDINGS_PAGE_SIZE = 10;

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
	unsupported,
	onRetry,
}: ProjectDescriptionSectionProps) {
	const paragraphs = splitProjectDescription(description);
	const hasDescription = paragraphs.length > 0;

	return (
		<section className="mb-3 space-y-4">
			<div className="flex flex-wrap items-center justify-between gap-3">
				<div className="flex items-center gap-2">
					<FileText className="w-4 h-4 text-sky-400" />
					<h2 className="text-sm font-semibold uppercase tracking-wider text-foreground">
						项目简介
					</h2>
				</div>
			</div>

			<div className="space-y-3">
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
		</section>
	);
}

export default function ProjectDetail() {
	const { id } = useParams<{ id: string }>();
	const location = useLocation();
	const navigate = useNavigate();
	const [project, setProject] = useState<Project | null>(null);
	const [agentTasks, setAgentTasks] = useState<AgentTask[]>([]);
	const [staticTasks, setStaticTasks] = useState<OpengrepScanTask[]>([]);
	const [gitleaksTasks, setGitleaksTasks] = useState<GitleaksScanTask[]>([]);
	const [banditTasks, setBanditTasks] = useState<BanditScanTask[]>([]);
	const [phpstanTasks, setPhpstanTasks] = useState<PhpstanScanTask[]>([]);
	const [potentialFindings, setPotentialFindings] = useState<
		ProjectDetailPotentialListItem[]
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
	const [loading, setLoading] = useState(true);
	const [showCreateScanTaskDialog, setShowCreateScanTaskDialog] = useState(false);
	const [selectedTaskFindings, setSelectedTaskFindings] = useState<{
		taskId: string;
		taskCategory: ProjectCardTaskFindingCategory;
		taskLabel: string;
	} | null>(null);
	const [recentTasksTableState, setRecentTasksTableState] =
		useState<DataTableQueryState>({
			globalFilter: "",
			columnFilters: [],
			sorting: [],
			pagination: {
				pageIndex: 0,
				pageSize: 10,
			},
			columnVisibility: {},
			rowSelection: {},
			density: "comfortable",
		});

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
			setPotentialFindings([]);
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

				const flattenedFindings = flattenProjectDetailPotentialFindings(
					nextTree,
				);
				setPotentialFindings(flattenedFindings);
				setPotentialTotalFindings(flattenedFindings.length);
				setPotentialStatus(flattenedFindings.length > 0 ? "ready" : "empty");
			} catch {
				setPotentialStatus("failed");
				setPotentialFindings([]);
			}
		},
		[],
	);

	const loadProjectData = useCallback(async () => {
		if (!id) return;

		try {
			setLoading(true);
			setPotentialStatus("loading");
			setPotentialFindings([]);
			setPotentialTotalFindings(0);

			const [
				projectRes,
				agentTasksRes,
				staticTasksRes,
				gitleaksTasksRes,
				banditTasksRes,
				phpstanTasksRes,
			] = await Promise.allSettled([
				api.getProjectById(id),
				getAgentTasks({ project_id: id }),
				getOpengrepScanTasks({ projectId: id }),
				getGitleaksScanTasks({ projectId: id }),
				getBanditScanTasks({ projectId: id }),
				getPhpstanScanTasks({ projectId: id }),
			]);

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
			setPotentialFindings([]);
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

	const nexusIframeRef = useRef<HTMLIFrameElement>(null);
	const iframeReadyRef = useRef(false);
	const archiveSentRef = useRef(false);  // 新增

	const sendArchiveToIframe = useCallback(async (projectId: string) => {
		if (archiveSentRef.current) return;  // 已发过，跳过
		archiveSentRef.current = true;       // 标记已发
		try {
			const archive = await api.downloadProjectArchive(projectId);
			const arrayBuffer = await archive.blob.arrayBuffer();
			nexusIframeRef.current?.contentWindow?.postMessage(
				{ type: 'LOAD_PROJECT_ZIP', filename: archive.filename, buffer: arrayBuffer },
				'*',
				[arrayBuffer],
			);
		} catch (error) {
			archiveSentRef.current = false;    // 失败时重置，允许重试
			console.error('Failed to fetch project archive:', error);
			toast.error('获取项目压缩包失败');
		}
	}, []);

	// iframe onLoad 时标记 ready，如果 project 已经有了就直接发
	const handleIframeLoad = useCallback(() => {
		iframeReadyRef.current = true;
		if (project?.id) {
			void sendArchiveToIframe(project.id);
		}
	}, [project, sendArchiveToIframe]);

	// project 加载完成后，如果 iframe 已经 ready 就补发
	useEffect(() => {
		if (project?.id && iframeReadyRef.current) {
			void sendArchiveToIframe(project.id);
		}
	}, [project?.id, sendArchiveToIframe]);

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
			agentTasks,
			opengrepTasks: staticTasks,
			gitleaksTasks,
			banditTasks,
			phpstanTasks,
			limit: DETAIL_RECENT_TASK_LIMIT,
		});
	}, [id, agentTasks, staticTasks, gitleaksTasks, banditTasks, phpstanTasks]);

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
				return <Badge className="cyber-badge-success font-normal">完成</Badge>;
			case "running":
				return <Badge className="cyber-badge-info font-normal">运行中</Badge>;
			case "failed":
				return <Badge className="cyber-badge-danger font-normal">失败</Badge>;
			case "interrupted":
				return (
					<Badge className="bg-orange-500/20 text-orange-300 border-orange-500/30 font-normal">
						中断
					</Badge>
				);
			case "cancelled":
				return <Badge className="cyber-badge-muted font-normal">已取消</Badge>;
			default:
				return <Badge className="cyber-badge-muted font-normal">等待中</Badge>;
		}
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
	const recentTaskColumns = useMemo<ColumnDef<(typeof recentTasks)[number]>[]>(
		() =>
			[
				{
					id: "sequence",
					header: "序号",
					enableSorting: false,
					meta: {
						label: "序号",
						plainHeader: true,
						width: "6%",
						headerClassName: "w-[6%] border-r border-border/50 text-center",
						cellClassName:
							"border-r border-border/30 text-center text-sm text-muted-foreground whitespace-nowrap",
					},
					cell: ({ row, table }) => {
						const pageRowIndex = table
							.getRowModel()
							.rows.findIndex((candidateRow) => candidateRow.id === row.id);
						const pagination = table.getState().pagination;
						return pagination.pageIndex * pagination.pageSize + pageRowIndex + 1;
					},
				},
				{
					id: "taskId",
					accessorFn: (row) => row.id,
					header: "任务ID",
					meta: {
						label: "任务ID",
						plainHeader: true,
						minWidth: "24%",
						headerClassName: "w-[24%] border-r border-border/50 text-center",
						cellClassName:
							"border-r border-border/30 text-center text-sm text-foreground whitespace-nowrap",
					},
					cell: ({ row }) => `#${row.original.id}`,
				},
				{
					id: "scanTypeLabel",
					accessorFn: (row) => row.scanTypeLabel,
					header: "类型",
					meta: {
						label: "类型",
						plainHeader: true,
						width: "14%",
						headerClassName: "w-[14%] border-r border-border/50 text-center",
						cellClassName: "border-r border-border/30 text-center text-sm text-foreground",
					},
				},
				{
					id: "createdAt",
					accessorFn: (row) => `${row.createdAt} ${formatDate(row.createdAt)}`,
					header: "创建时间",
					meta: {
						label: "创建时间",
						plainHeader: true,
						width: "16%",
						headerClassName: "w-[16%] border-r border-border/50 text-center",
						cellClassName:
							"border-r border-border/30 text-center text-sm text-muted-foreground",
					},
					cell: ({ row }) => formatDate(row.original.createdAt),
				},
				{
					id: "status",
					accessorFn: (row) => row.status,
					header: "状态",
					meta: {
						label: "状态",
						plainHeader: true,
						width: "10%",
						headerClassName: "w-[10%] border-r border-border/50 text-center",
						cellClassName: "border-r border-border/30 text-center",
					},
					cell: ({ row }) => <div className="flex justify-center">{getStatusBadge(row.original.status)}</div>,
				},
				{
					id: "vulnerabilities",
					accessorFn: (row) => formatRecentTaskMetricValue(row.vulnerabilities),
					header: "漏洞",
					meta: {
						label: "漏洞",
						plainHeader: true,
						width: "8%",
						headerClassName: "w-[8%] border-r border-border/50 text-center",
						cellClassName:
							"border-r border-border/30 text-center text-sm text-muted-foreground",
					},
				},
				{
					id: "actions",
					header: "操作",
					enableSorting: false,
					meta: {
						label: "操作",
						plainHeader: true,
						width: "22%",
						headerClassName: "w-[22%] text-center",
						cellClassName: "text-center",
					},
					cell: ({ row }) => (
						<div className="flex items-center justify-center gap-2 whitespace-nowrap">
							<Button
								asChild
								size="sm"
								variant="outline"
								className="cyber-btn-ghost h-7 px-3"
							>
								<Link to={withStaticReturnTo(row.original.route, row.original.kind)}>
									任务详情
								</Link>
							</Button>
							{row.original.supportsFindingsDetail && row.original.taskCategory ? (
								<Button
									type="button"
									size="sm"
									variant="outline"
									className="cyber-btn-ghost h-7 px-3"
									onClick={() => {
										const taskCategory = row.original.taskCategory;
										if (!taskCategory) return;
										openTaskFindingsDialog(
											row.original.id,
											taskCategory,
											getProjectDetailPotentialTaskCategoryText(taskCategory),
										);
									}}
								>
									漏洞详情
								</Button>
							) : (
								<span title={row.original.findingsButtonDisabledReason || undefined}>
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
					),
				},
			] satisfies AppColumnDef<(typeof recentTasks)[number], unknown>[],
		[
			formatDate,
			getStatusBadge,
			openTaskFindingsDialog,
			withStaticReturnTo,
			recentTasks,
		],
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
			<div className="relative z-10">
				<iframe
					ref={nexusIframeRef}
					src="http://localhost:5175"
					title="Nexus-itemDetail"
					className="w-full border-0 rounded-lg"
					style={{ height: '600px' }}
					onLoad={handleIframeLoad}
				/>
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

					<div className="flex flex-wrap items-center justify-between gap-3 mb-3">
						<div className="flex items-center gap-2">
							<Activity className="w-4 h-4 text-sky-400" />
							<h3 className="text-sm font-semibold uppercase tracking-wider">
								最近任务
							</h3>
						</div>
					</div>

					<DataTable
						data={recentTasks}
						columns={recentTaskColumns}
						state={recentTasksTableState}
						onStateChange={setRecentTasksTableState}
						emptyState={{
							title: "暂无任务",
						}}
						toolbar={{
							searchPlaceholder: "搜索任务 ID、类型或创建时间",
							showColumnVisibility: false,
							showDensityToggle: false,
							showReset: false,
						}}
						pagination={{
							enabled: true,
							pageSizeOptions: [10, 20, 50],
							infoLabel: ({ table, filteredCount }) =>
								`共 ${filteredCount.toLocaleString()} 条，第 ${
									table.getState().pagination.pageIndex + 1
								} / ${Math.max(1, table.getPageCount())} 页`,
						}}
						tableClassName="table-fixed"
					/>

				<ProjectPotentialVulnerabilitiesSection
					status={potentialStatus}
					findings={potentialFindings}
					totalFindings={potentialTotalFindings}
					currentRoute={currentRoute}
					pageSize={DETAIL_POTENTIAL_FINDINGS_PAGE_SIZE}
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
