/**
 * Create Task Dialog
 * Cyberpunk Terminal Aesthetic
 */

import { useState, useEffect, useMemo, useRef } from "react";
import { useLocation, useNavigate } from "react-router-dom";
import {
	Dialog,
	DialogContent,
	DialogHeader,
	DialogTitle,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import { Label } from "@/components/ui/label";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Checkbox } from "@/components/ui/checkbox";
import { BranchSelector } from "@/components/ui/branch-selector";
import {
	Collapsible,
	CollapsibleContent,
	CollapsibleTrigger,
} from "@/components/ui/collapsible";
import {
	Search,
	ChevronRight,
	GitBranch,
	Upload,
	FolderOpen,
	Settings2,
	Package,
	Globe,
	Shield,
	Loader2,
	Zap,
	Bot,
} from "lucide-react";
import { toast } from "sonner";
import { api } from "@/shared/config/database";
import { createAgentTask } from "@/shared/api/agentTasks";
import {
	createOpengrepScanTask,
	getOpengrepRules,
	type OpengrepRule,
} from "@/shared/api/opengrep";
import { createGitleaksScanTask } from "@/shared/api/gitleaks";
import {
	getOpengrepActiveRules,
	setOpengrepActiveRules,
	subscribeOpengrepActiveRules,
} from "@/shared/stores/opengrepRulesStore";

import { useProjects } from "./hooks/useTaskForm";
import { useZipFile, formatFileSize } from "./hooks/useZipFile";
import FileSelectionDialog from "./FileSelectionDialog";
import AgentModeSelector, {
	type ScanMode,
	type StaticToolSelection,
} from "@/components/agent/AgentModeSelector";

import { validateZipFile } from "@/features/projects/services/repoZipScan";
import { uploadZipFile } from "@/shared/utils/zipStorage";
import { isRepositoryProject, isZipProject } from "@/shared/utils/projectUtils";
import type { Project } from "@/shared/types";
import { INTELLIGENT_TASK_NAME_MARKER } from "@/features/tasks/services/taskActivities";
import { appendReturnTo } from "@/shared/utils/findingRoute";

interface CreateScanTaskDialogProps {
	open: boolean;
	onOpenChange: (open: boolean) => void;
	onTaskCreated: () => void;
	preselectedProjectId?: string;
	initialScanMode?: ScanMode;
	navigateOnSuccess?: boolean;
	showReturnButton?: boolean;
	onReturn?: () => void;
	allowUploadProject?: boolean;
}

const DEFAULT_EXCLUDES = [
	"node_modules/**",
	".git/**",
	"dist/**",
	"build/**",
	"*.log",
];

const ARCHIVE_SUFFIXES = [
	".tar.gz",
	".tar.bz2",
	".tar.xz",
	".tgz",
	".tbz2",
	".zip",
	".tar",
	".7z",
	".rar",
];

const stripArchiveSuffix = (filename: string) => {
	const lower = filename.toLowerCase();
	const matched = ARCHIVE_SUFFIXES.find((suffix) => lower.endsWith(suffix));
	if (!matched) return filename;
	return filename.slice(0, filename.length - matched.length);
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

const isSevereRule = (rule: OpengrepRule) =>
	String(rule.severity || "").toUpperCase() === "ERROR";

export default function CreateScanTaskDialog({
	open,
	onOpenChange,
	onTaskCreated,
	preselectedProjectId,
	initialScanMode,
	navigateOnSuccess = true,
	showReturnButton = false,
	onReturn,
	allowUploadProject = false,
}: CreateScanTaskDialogProps) {
	const navigate = useNavigate();
	const location = useLocation();
	const currentRoute = `${location.pathname}${location.search}`;
	const [sourceMode, setSourceMode] = useState<"existing" | "upload">(
		"existing",
	);
	const [selectedProjectId, setSelectedProjectId] = useState<string>("");
	const [searchTerm, setSearchTerm] = useState("");
	const [branch, setBranch] = useState("main");
	const [branches, setBranches] = useState<string[]>([]);
	const [loadingBranches, setLoadingBranches] = useState(false);
	const [excludePatterns, setExcludePatterns] = useState(DEFAULT_EXCLUDES);
	const [selectedFiles, setSelectedFiles] = useState<string[] | undefined>();
	const [showAdvanced, setShowAdvanced] = useState(false);
	const [showFileSelection, setShowFileSelection] = useState(false);
	const [creating, setCreating] = useState(false);
	const [uploading, setUploading] = useState(false);
	const [newProjectName, setNewProjectName] = useState("");
	const [newProjectFile, setNewProjectFile] = useState<File | null>(null);
	const newProjectFileInputRef = useRef<HTMLInputElement>(null);

	const [scanMode, setScanMode] = useState<ScanMode>("agent");
	const [staticTools, setStaticTools] = useState<StaticToolSelection>({
		opengrep: true,
		gitleaks: false,
	});
	const [staticRules, setStaticRules] = useState<OpengrepRule[]>([]);
	const [selectedRuleIds, setSelectedRuleIds] = useState<string[]>([]);
	const [loadingStaticRules, setLoadingStaticRules] = useState(false);

	const { projects, loading, loadProjects } = useProjects();
	const selectedProject = projects.find((p) => p.id === selectedProjectId);
	const zipState = useZipFile(selectedProject, projects);

	useEffect(() => {
		const loadBranches = async () => {
			const project = projects.find((p) => p.id === selectedProjectId);
			if (!project || !isRepositoryProject(project)) {
				setBranches([]);
				return;
			}

			setLoadingBranches(true);
			try {
				const result = await api.getProjectBranches(project.id);
				if (result.error) {
					toast.error(`加载分支失败: ${result.error}`);
				}
				setBranches(result.branches);
				if (result.default_branch) {
					setBranch(result.default_branch);
				}
			} catch (error) {
				const msg = error instanceof Error ? error.message : "未知错误";
				toast.error(`加载分支失败: ${msg}`);
				setBranches([project.default_branch || "main"]);
			} finally {
				setLoadingBranches(false);
			}
		};

		loadBranches();
	}, [selectedProjectId, projects]);

	const filteredProjects = useMemo(() => {
		if (!searchTerm) return projects;
		const term = searchTerm.toLowerCase();
		return projects.filter(
			(p) =>
				p.name.toLowerCase().includes(term) ||
				p.description?.toLowerCase().includes(term),
		);
	}, [projects, searchTerm]);

	const staticRuleOptions = useMemo(
		() =>
			staticRules.map((rule) => ({
				value: rule.id,
				label: `${rule.name} (${rule.language.toUpperCase()} · ${rule.severity})`,
			})),
		[staticRules],
	);

	useEffect(() => {
		const cached = getOpengrepActiveRules().filter(isSevereRule);
		if (cached.length > 0) {
			setStaticRules(cached);
		}
		const unsubscribe = subscribeOpengrepActiveRules((rules) => {
			setStaticRules(rules.filter(isSevereRule));
		});
		return () => {
			unsubscribe();
		};
	}, []);

	useEffect(() => {
		const loadStaticRules = async () => {
			if (!open || scanMode !== "static" || !staticTools.opengrep) return;
			setLoadingStaticRules(true);
			try {
				const rules = (await getOpengrepRules({ is_active: true })).filter(
					isSevereRule,
				);
				setStaticRules(rules);
				setOpengrepActiveRules(rules);
				setSelectedRuleIds((prev) => {
					if (prev.length === 0) return prev;
					const validRuleIds = new Set(rules.map((rule) => rule.id));
					return prev.filter((id) => validRuleIds.has(id));
				});
			} catch (error) {
				console.error("加载静态分析规则失败:", error);
			} finally {
				setLoadingStaticRules(false);
			}
		};
		loadStaticRules();
	}, [open, scanMode, staticTools.opengrep]);

	useEffect(() => {
		if (open) {
			loadProjects();
			setSelectedProjectId(preselectedProjectId || "");
			setSearchTerm("");
			setShowAdvanced(false);
			setSelectedRuleIds([]);
			setScanMode(initialScanMode || "agent");
			setStaticTools({ opengrep: true, gitleaks: false });
			setSourceMode("existing");
			setNewProjectName("");
			setNewProjectFile(null);
			zipState.reset();
			}
		}, [open, preselectedProjectId, initialScanMode, loadProjects]);

	useEffect(() => {
		if (!open || sourceMode !== "existing") return;
		if (selectedProjectId) return;
		if (projects.length === 0) return;
		setSelectedProjectId(projects[0].id);
	}, [open, sourceMode, selectedProjectId, projects]);

	const excludePatternsRef = useRef(excludePatterns);
	useEffect(() => {
		if (excludePatternsRef.current !== excludePatterns && selectedFiles) {
			setSelectedFiles(undefined);
			toast.info("排除模式已更改，请重新选择文件");
		}
		excludePatternsRef.current = excludePatterns;
	}, [excludePatterns]);

	const handleNewProjectFileSelect = (
		event: React.ChangeEvent<HTMLInputElement>,
	) => {
		const file = event.target.files?.[0] || null;
		if (!file) return;
		const validation = validateZipFile(file);
		if (!validation.valid) {
			toast.error(validation.error || "文件无效");
			event.target.value = "";
			return;
		}

		const inferredName = stripArchiveSuffix(file.name).trim();
		if (inferredName) {
			setNewProjectName(inferredName);
		}
		setNewProjectFile(file);
		event.target.value = "";
	};

	const handleSourceModeChange = (mode: "existing" | "upload") => {
		setSourceMode(mode);
		setSelectedFiles(undefined);
		if (mode === "upload") {
			setSelectedProjectId("");
			setBranch("main");
			zipState.reset();
			return;
		}

		if (!selectedProjectId && projects.length > 0) {
			setSelectedProjectId(projects[0].id);
		}
	};

	const effectiveTargetFiles = useMemo(() => {
		if (selectedFiles && selectedFiles.length > 0) {
			return selectedFiles;
		}
		return [];
	}, [selectedFiles]);

	const createStaticScanTasksForProject = async (
		projectId: string,
		projectName: string,
	) => {
		if (!staticTools.opengrep && !staticTools.gitleaks) {
			throw new Error("请选择至少一个静态分析工具");
		}

		let opengrepTask: { id: string } | null = null;
		let gitleaksTask: { id: string } | null = null;

		if (staticTools.opengrep) {
			const pickActiveRuleIds = (rules: OpengrepRule[]) => {
				const severeRules = rules.filter(isSevereRule);
				const validRuleIds = new Set(severeRules.map((rule) => rule.id));
				const selected = selectedRuleIds.filter((id) => validRuleIds.has(id));
				return selected.length > 0
					? selected
					: severeRules.map((rule) => rule.id);
			};

			const activeRuleIds = pickActiveRuleIds(staticRules);
			if (activeRuleIds.length === 0) {
				throw new Error("未找到启用的规则，请先在规则管理中启用规则");
			}
			try {
				opengrepTask = await createOpengrepScanTask({
					project_id: projectId,
					name: `静态分析-Opengrep-${projectName}`,
					rule_ids: activeRuleIds,
					target_path: ".",
				});
			} catch (error) {
				const apiMsg = extractApiErrorMessage(error);
				const shouldReloadRules =
					apiMsg.includes("部分规则不存在") || apiMsg.includes("规则不存在");
				if (!shouldReloadRules) throw error;

				const freshRules = (await getOpengrepRules({ is_active: true })).filter(
					isSevereRule,
				);
				setStaticRules(freshRules);
				setOpengrepActiveRules(freshRules);

				const retryRuleIds = pickActiveRuleIds(freshRules);
				if (retryRuleIds.length === 0) {
					throw new Error("规则已更新，请刷新规则后重试");
				}

				opengrepTask = await createOpengrepScanTask({
					project_id: projectId,
					name: `静态分析-Opengrep-${projectName}`,
					rule_ids: retryRuleIds,
					target_path: ".",
				});
			}
		}

		if (staticTools.gitleaks) {
			gitleaksTask = await createGitleaksScanTask({
				project_id: projectId,
				name: `静态分析-Gitleaks-${projectName}`,
				target_path: ".",
				no_git: true,
			});
		}

		const primaryTaskId = opengrepTask?.id || gitleaksTask?.id;
		if (!primaryTaskId) {
			throw new Error("静态分析任务创建失败");
		}

		const params = new URLSearchParams();
		if (opengrepTask && gitleaksTask) {
			params.set("gitleaksTaskId", gitleaksTask.id);
			params.set("opengrepTaskId", opengrepTask.id);
		}
		if (!opengrepTask && gitleaksTask) {
			params.set("tool", "gitleaks");
		}

		return {
			primaryTaskId,
			query: params.toString(),
		};
	};

	const handleStartScan = async () => {
		try {
			setCreating(true);
			if (sourceMode === "upload") {
				if (!newProjectName.trim()) {
					toast.error("请输入项目名称");
					return;
				}
				if (!newProjectFile) {
					toast.error("请先选择项目压缩包");
					return;
				}

				let createdProject: Project | null = null;
				try {
					createdProject = await api.createProject({
						name: newProjectName.trim(),
						source_type: "zip",
						repository_type: "other",
						repository_url: undefined,
						default_branch: "main",
						programming_languages: [],
					} as any);

					const uploadResult = await uploadZipFile(
						createdProject.id,
						newProjectFile,
					);
					if (!uploadResult.success) {
						throw new Error(uploadResult.message || "压缩包上传失败");
					}

					if (scanMode === "agent") {
						const agentTask = await createAgentTask({
							project_id: createdProject.id,
							name: `智能扫描-${createdProject.name}`,
							description: `${INTELLIGENT_TASK_NAME_MARKER}智能扫描任务`,
							audit_scope: {
								static_bootstrap: {
									mode: "disabled",
									opengrep_enabled: false,
									gitleaks_enabled: false,
								},
							},
							target_files:
								effectiveTargetFiles.length > 0
									? effectiveTargetFiles
									: undefined,
							verification_level: "analysis_with_poc_plan",
						});

						onOpenChange(false);
						onTaskCreated();
						toast.success("智能扫描任务已创建");
						if (navigateOnSuccess) {
							navigate(`/agent-audit/${agentTask.id}`);
						}
						loadProjects();
						return;
					}

					const staticResult = await createStaticScanTasksForProject(
						createdProject.id,
						createdProject.name,
					);
					onOpenChange(false);
					onTaskCreated();
					toast.success("静态分析任务已创建");
					if (navigateOnSuccess) {
						navigate(
							appendReturnTo(
								`/static-analysis/${staticResult.primaryTaskId}${staticResult.query ? `?${staticResult.query}` : ""
								}`,
								currentRoute,
							),
						);
					}
					loadProjects();
					return;
				} catch (error) {
					if (createdProject) {
						try {
							await api.deleteProject(createdProject.id);
						} catch (rollbackError) {
							console.error("回滚失败项目失败:", rollbackError);
						}
					}
					throw error;
				}
			}

			if (!selectedProject) {
				toast.error("请选择项目");
				return;
			}

			if (scanMode === "agent") {
				const agentTask = await createAgentTask({
					project_id: selectedProject.id,
					name: `智能扫描-${selectedProject.name}`,
					description: `${INTELLIGENT_TASK_NAME_MARKER}智能扫描任务`,
					audit_scope: {
						static_bootstrap: {
							mode: "disabled",
							opengrep_enabled: false,
							gitleaks_enabled: false,
						},
					},
					branch_name: isRepositoryProject(selectedProject)
						? branch
						: undefined,
					exclude_patterns: excludePatterns,
					target_files:
						effectiveTargetFiles.length > 0 ? effectiveTargetFiles : undefined,
					verification_level: "analysis_with_poc_plan",
				});

				onOpenChange(false);
				onTaskCreated();
				toast.success("智能扫描任务已创建");
				if (navigateOnSuccess) {
					navigate(`/agent-audit/${agentTask.id}`);
				}
				return;
			}

			if (!isZipProject(selectedProject)) {
				toast.error("静态分析仅支持源码归档项目");
				return;
			}
			if (!zipState.storedZipInfo?.has_file) {
				toast.error("请先上传源码归档");
				return;
			}

			const staticResult = await createStaticScanTasksForProject(
				selectedProject.id,
				selectedProject.name,
			);
			onOpenChange(false);
			onTaskCreated();
			toast.success("静态分析任务已创建");
			if (navigateOnSuccess) {
				navigate(
					appendReturnTo(
						`/static-analysis/${staticResult.primaryTaskId}${staticResult.query ? `?${staticResult.query}` : ""
						}`,
						currentRoute,
					),
				);
			}
		} catch (error) {
			const msg = extractApiErrorMessage(error);
			toast.error(`启动失败: ${msg}`);
		} finally {
			setCreating(false);
			setSelectedFiles(undefined);
			setExcludePatterns(DEFAULT_EXCLUDES);
		}
	};

		const canStart = useMemo(() => {
			if (sourceMode === "upload") {
				if (!newProjectName.trim() || !newProjectFile) return false;
				if (scanMode === "static") {
					return staticTools.opengrep || staticTools.gitleaks;
				}
				return true;
			}
			if (!selectedProject) return false;
			if (scanMode === "static") {
				return (
					isZipProject(selectedProject) &&
				!!zipState.storedZipInfo?.has_file &&
				(staticTools.opengrep || staticTools.gitleaks)
			);
		}
			if (isZipProject(selectedProject)) {
				const ready =
					(zipState.useStoredZip && zipState.storedZipInfo?.has_file) ||
					!!zipState.zipFile;
				if (!ready) return false;
				return true;
			}
			if (!selectedProject.repository_url || !branch.trim()) return false;
			return true;
		}, [
			sourceMode,
			newProjectName,
			newProjectFile,
			selectedProject,
			zipState,
			branch,
			scanMode,
			effectiveTargetFiles,
			staticTools.opengrep,
			staticTools.gitleaks,
		]);

	return (
		<>
			<Dialog open={open} onOpenChange={onOpenChange}>
				<DialogContent className="!w-[min(90vw,520px)] !max-w-none max-h-[85vh] flex flex-col p-0 gap-0 cyber-dialog border border-border rounded-lg">
					{/* Header */}
					<DialogHeader className="px-5 py-4 border-b border-border flex-shrink-0 bg-muted">
						<DialogTitle className="flex items-center gap-3 font-mono text-foreground">
							<div className="p-2 bg-primary/20 rounded border border-primary/30">
								<Shield className="w-5 h-5 text-primary" />
							</div>
							<div>
								<span className="text-base font-bold uppercase tracking-wider">
									开始代码扫描
								</span>
								<p className="text-xs text-muted-foreground font-normal mt-0.5">
									Code Security Analysis
								</p>
							</div>
						</DialogTitle>
					</DialogHeader>

					<div className="flex-1 overflow-y-auto p-5 space-y-5">
						{allowUploadProject && (
							<div className="space-y-2">
								<span className="text-sm font-mono font-bold uppercase text-muted-foreground">
									项目来源
								</span>
								<div className="grid grid-cols-2 gap-2">
									<Button
										variant={sourceMode === "existing" ? "default" : "outline"}
										className={
											sourceMode === "existing"
												? "cyber-btn-primary"
							: "cyber-btn-outline"
						}
						onClick={() => handleSourceModeChange("existing")}
						disabled={creating}
					>
						选择已有项目
					</Button>
									<Button
										variant={sourceMode === "upload" ? "default" : "outline"}
										className={
											sourceMode === "upload"
												? "cyber-btn-primary"
							: "cyber-btn-outline"
						}
						onClick={() => handleSourceModeChange("upload")}
						disabled={creating}
					>
						上传新项目
					</Button>
								</div>
							</div>
						)}

						{sourceMode === "existing" ? (
							<div className="space-y-3">
								<div className="flex items-center justify-between">
									<span className="text-sm font-mono font-bold uppercase text-muted-foreground">
										选择项目
									</span>
									<Badge className="cyber-badge-muted font-mono text-xs">
										{filteredProjects.length} 个
									</Badge>
								</div>

								<div className="relative mt-1.5">
									<Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground" />
									<Input
										placeholder="搜索项目..."
										value={searchTerm}
										onChange={(e) => setSearchTerm(e.target.value)}
										className="!pl-10 h-10 cyber-input"
									/>
								</div>

								<ScrollArea className="h-[180px] border border-border rounded bg-muted/50">
									{loading ? (
										<div className="flex items-center justify-center h-full">
											<Loader2 className="w-5 h-5 animate-spin text-primary" />
										</div>
									) : filteredProjects.length === 0 ? (
										<div className="flex flex-col items-center justify-center h-full text-muted-foreground font-mono">
											<Package className="w-8 h-8 mb-2 opacity-50" />
											<span className="text-sm">
												{searchTerm ? "未找到" : "暂无项目"}
											</span>
										</div>
									) : (
										<div className="p-1">
											{filteredProjects.map((project) => (
												<ProjectCard
													key={project.id}
													project={project}
													selected={selectedProjectId === project.id}
													onSelect={() => setSelectedProjectId(project.id)}
												/>
											))}
										</div>
									)}
								</ScrollArea>
							</div>
						) : (
							<div className="space-y-3 border border-border rounded p-3 bg-muted/40">
								<div className="space-y-1.5">
									<Label className="font-mono font-bold uppercase text-xs text-muted-foreground">
										项目名称
									</Label>
					<Input
						value={newProjectName}
						onChange={(e) => setNewProjectName(e.target.value)}
						placeholder="输入项目名称"
						className="h-10 cyber-input"
						disabled={creating}
					/>
				</div>
				<div className="rounded-lg border border-dashed border-sky-500/30 bg-sky-500/8 p-3">
					<p className="text-xs font-mono font-bold uppercase text-sky-100 mb-1">
						自动生成简介
					</p>
					<p className="text-xs leading-5 text-sky-50/85">
						上传完成后，系统会基于项目结构自动生成 1-2 句项目使用场景简介。
					</p>
				</div>
				<div className="space-y-2">
					<Label className="font-mono font-bold uppercase text-xs text-muted-foreground">
						源码压缩包
									</Label>
									<input
										ref={newProjectFileInputRef}
										type="file"
						accept=".zip,.tar,.tar.gz,.tar.bz2,.7z,.rar"
						onChange={handleNewProjectFileSelect}
						className="hidden"
						disabled={creating}
					/>
					<Button
						variant="outline"
						className="cyber-btn-outline h-9"
						onClick={() => newProjectFileInputRef.current?.click()}
						disabled={creating}
					>
										<Upload className="w-4 h-4 mr-2" />
										选择压缩包
									</Button>
									{newProjectFile && (
										<p className="text-xs text-emerald-400 font-mono">
											已选择: {newProjectFile.name}
										</p>
									)}
								</div>
							</div>
						)}

						{/* 扫描模式选择 */}
							{(sourceMode === "upload" || selectedProject) && (
								<AgentModeSelector
									value={scanMode}
									onChange={setScanMode}
								disabled={creating}
								staticTools={staticTools}
								onStaticToolsChange={setStaticTools}
								/>
							)}

							{/* 配置区域 */}
						{sourceMode === "existing" && selectedProject && (
							<div className="space-y-4">
								<span className="text-sm font-mono font-bold uppercase text-muted-foreground">
									配置
								</span>

								{isRepositoryProject(selectedProject) ? (
									<div className="flex items-center gap-3 p-3 border border-border rounded bg-blue-50 dark:bg-blue-950/20">
										<GitBranch className="w-5 h-5 text-blue-600 dark:text-blue-400" />
										<span className="font-mono text-base text-muted-foreground w-12">
											分支
										</span>
										{loadingBranches ? (
											<div className="flex items-center gap-2 flex-1">
												<Loader2 className="w-4 h-4 animate-spin text-blue-600 dark:text-blue-400" />
												<span className="text-sm text-blue-600 dark:text-blue-400 font-mono">
													加载中...
												</span>
											</div>
										) : (
											<BranchSelector
												value={branch}
												onChange={setBranch}
												branches={branches}
												placeholder="选择分支"
												className="flex-1"
											/>
										)}
									</div>
								) : (
									<ZipUploadCard
										zipState={zipState}
										onUpload={async () => {
											if (!zipState.zipFile || !selectedProject) return;
											setUploading(true);
											try {
												await api.uploadProjectZip(
													selectedProject.id,
													zipState.zipFile,
												);
												toast.success("文件上传成功");
												zipState.switchToStored();
												loadProjects();
											} catch (error) {
												const msg =
													error instanceof Error ? error.message : "上传失败";
												toast.error(msg);
											} finally {
												setUploading(false);
											}
										}}
										uploading={uploading}
									/>
								)}

								{scanMode === "static" && null}

								{/* 高级选项 */}
								<Collapsible open={showAdvanced} onOpenChange={setShowAdvanced}>
									<CollapsibleTrigger className="flex items-center gap-2 text-xs font-mono text-muted-foreground hover:text-foreground transition-colors">
										<ChevronRight
											className={`w-4 h-4 transition-transform ${showAdvanced ? "rotate-90" : ""}`}
										/>
										<Settings2 className="w-4 h-4" />
										<span className="uppercase font-bold">高级选项</span>
									</CollapsibleTrigger>
									<CollapsibleContent className="mt-3 space-y-3">
										{/* 排除模式 */}
										<div className="p-3 border border-dashed border-border rounded bg-muted/50 space-y-3">
											<div className="flex items-center justify-between">
												<span className="font-mono text-xs uppercase font-bold text-muted-foreground">
													排除模式
												</span>
												<button
													type="button"
													onClick={() => setExcludePatterns(DEFAULT_EXCLUDES)}
													className="text-xs font-mono text-primary hover:text-primary/80"
												>
													重置为默认
												</button>
											</div>

											<div className="flex flex-wrap gap-1.5">
												{excludePatterns.map((p) => (
													<Badge
														key={p}
														className="bg-muted text-foreground border-0 font-mono text-xs cursor-pointer hover:bg-rose-100 dark:hover:bg-rose-900/50 hover:text-rose-600 dark:hover:text-rose-400"
														onClick={() =>
															setExcludePatterns((prev) =>
																prev.filter((x) => x !== p),
															)
														}
													>
														{p} ×
													</Badge>
												))}
												{excludePatterns.length === 0 && (
													<span className="text-xs text-muted-foreground font-mono">
														无排除模式
													</span>
												)}
											</div>

											<div className="flex flex-wrap gap-1">
												<span className="text-xs text-muted-foreground font-mono mr-1">
													快捷添加:
												</span>
												{[
													".test.",
													".spec.",
													".min.",
													"coverage/",
													"docs/",
													".md",
												].map((pattern) => (
													<button
														key={pattern}
														type="button"
														disabled={excludePatterns.includes(pattern)}
														onClick={() => {
															if (!excludePatterns.includes(pattern)) {
																setExcludePatterns((prev) => [
																	...prev,
																	pattern,
																]);
															}
														}}
														className="text-xs font-mono px-1.5 py-0.5 border border-border bg-muted hover:bg-muted text-muted-foreground hover:text-foreground disabled:opacity-40 disabled:cursor-not-allowed rounded"
													>
														+{pattern}
													</button>
												))}
											</div>

											<Input
												placeholder="添加自定义排除模式，回车确认"
												className="h-8 cyber-input text-sm"
												onKeyDown={(e) => {
													if (e.key === "Enter" && e.currentTarget.value) {
														const val = e.currentTarget.value.trim();
														if (val && !excludePatterns.includes(val)) {
															setExcludePatterns((prev) => [...prev, val]);
														}
														e.currentTarget.value = "";
													}
												}}
											/>
										</div>

										{/* 文件选择 */}
										{(() => {
											const isRepo = isRepositoryProject(selectedProject);
											const isZip = isZipProject(selectedProject);
											const hasStoredZip = zipState.storedZipInfo?.has_file;
											const useStored = zipState.useStoredZip;
											const canSelectFiles =
												isRepo || (isZip && useStored && hasStoredZip);

											return (
												<div className="flex items-center justify-between p-3 border border-dashed border-border rounded bg-muted/50">
													<div>
														<p className="font-mono text-xs uppercase font-bold text-muted-foreground">
															扫描范围
														</p>
														<p className="text-sm font-bold text-foreground mt-1">
															{selectedFiles
																? `已选 ${selectedFiles.length} 个文件`
																: "全部文件"}
														</p>
													</div>
													<div className="flex gap-2">
														{selectedFiles && canSelectFiles && (
															<Button
																size="sm"
																variant="ghost"
																onClick={() => setSelectedFiles(undefined)}
																className="h-8 text-xs text-rose-600 dark:text-rose-400 hover:bg-rose-100 dark:hover:bg-rose-900/30 hover:text-rose-700 dark:hover:text-rose-300"
															>
																重置
															</Button>
														)}
														<Button
															size="sm"
															variant="outline"
															onClick={() => setShowFileSelection(true)}
															disabled={!canSelectFiles}
															className="h-8 text-xs cyber-btn-outline font-mono font-bold disabled:opacity-50"
														>
															<FolderOpen className="w-3 h-3 mr-1" />
															选择文件
														</Button>
													</div>
												</div>
											);
										})()}
									</CollapsibleContent>
								</Collapsible>
							</div>
						)}
					</div>

					{/* Footer */}
					<div className="flex-shrink-0 flex justify-end gap-3 px-5 py-4 bg-muted border-t border-border">
						{showReturnButton && (
							<Button
								variant="outline"
								onClick={() => {
								onOpenChange(false);
								onReturn?.();
							}}
							disabled={creating}
							className="px-4 h-10 cyber-btn-outline font-mono"
						>
								返回
							</Button>
						)}
					<Button
						variant="ghost"
						onClick={() => onOpenChange(false)}
						disabled={creating}
						className="px-4 h-10 font-mono text-muted-foreground hover:text-foreground hover:bg-muted"
					>
							取消
						</Button>
					<Button
						onClick={handleStartScan}
						disabled={!canStart || creating}
						className="px-5 h-10 cyber-btn-primary font-mono font-bold uppercase"
					>
							{creating ? (
								<>
									<Loader2 className="w-4 h-4 animate-spin mr-2" />
									启动中...
								</>
							) : scanMode === "agent" ? (
								<>
									<Bot className="w-4 h-4 mr-2" />
									启动智能扫描
								</>
							) : (
								<>
									<Zap className="w-4 h-4 mr-2" />
									开始静态分析
								</>
							)}
						</Button>
					</div>
				</DialogContent>
			</Dialog>

			{sourceMode === "existing" && selectedProjectId ? (
				<FileSelectionDialog
					open={showFileSelection}
					onOpenChange={setShowFileSelection}
					projectId={selectedProjectId}
					branch={branch}
					excludePatterns={excludePatterns}
					onConfirm={setSelectedFiles}
				/>
			) : null}
		</>
	);
}

function ProjectCard({
	project,
	selected,
	onSelect,
}: {
	project: Project;
	selected: boolean;
	onSelect: () => void;
}) {
	const isRepo = isRepositoryProject(project);

	return (
		<div
			className={`flex items-center gap-3 p-3 cursor-pointer rounded transition-all ${selected
					? "bg-primary/10 border border-primary/50"
					: "hover:bg-muted border border-transparent"
				}`}
			onClick={onSelect}
		>
			<Checkbox
				checked={selected}
				className="border-border data-[state=checked]:bg-primary data-[state=checked]:border-primary"
			/>

			<div
				className={`p-1.5 rounded ${isRepo ? "bg-blue-500/20" : "bg-amber-500/20"}`}
			>
				{isRepo ? (
					<Globe className="w-4 h-4 text-blue-600 dark:text-blue-400" />
				) : (
					<Package className="w-4 h-4 text-amber-600 dark:text-amber-400" />
				)}
			</div>

			<div className="flex-1 min-w-0 overflow-hidden">
				<div className="flex items-center gap-2">
					<span
						className={`font-mono text-base truncate ${selected ? "text-foreground font-bold" : "text-foreground"}`}
					>
						{project.name}
					</span>
					<Badge
						className={`text-xs px-1 py-0 font-mono ${isRepo
								? "bg-blue-500/20 text-blue-600 dark:text-blue-400 border-blue-500/30"
								: "bg-amber-500/20 text-amber-600 dark:text-amber-400 border-amber-500/30"
							}`}
					>
						{isRepo ? "REPO" : "ZIP"}
					</Badge>
				</div>
				{project.description && (
					<p
						className="text-sm text-muted-foreground mt-0.5 font-mono line-clamp-2"
						title={project.description}
					>
						{project.description}
					</p>
				)}
			</div>
		</div>
	);
}

function ZipUploadCard({
	zipState,
	onUpload,
	uploading,
}: {
	zipState: ReturnType<typeof useZipFile>;
	onUpload: () => void;
	uploading: boolean;
}) {
	if (zipState.loading) {
		return (
			<div className="flex items-center gap-3 p-3 border border-border rounded bg-blue-50 dark:bg-blue-950/20">
				<Loader2 className="w-5 h-5 animate-spin text-blue-600 dark:text-blue-400" />
				<span className="text-sm font-mono text-blue-600 dark:text-blue-400">
					检查文件中...
				</span>
			</div>
		);
	}

	if (zipState.storedZipInfo?.has_file) {
		return (
			<div className="p-3 border border-border rounded bg-emerald-50 dark:bg-emerald-950/20 space-y-3">
				<div className="flex items-center gap-3">
					<div className="p-1.5 bg-emerald-500/20 rounded">
						<Package className="w-4 h-4 text-emerald-600 dark:text-emerald-400" />
					</div>
					<div className="flex-1">
						<p className="text-sm font-bold text-emerald-700 dark:text-emerald-300 font-mono">
							{zipState.storedZipInfo.original_filename}
						</p>
						<p className="text-xs text-emerald-600 dark:text-emerald-500 font-mono">
							{zipState.storedZipInfo.file_size &&
								formatFileSize(zipState.storedZipInfo.file_size)}
							{zipState.storedZipInfo.uploaded_at &&
								` · ${new Date(zipState.storedZipInfo.uploaded_at).toLocaleDateString("zh-CN")}`}
						</p>
					</div>
				</div>

				<div className="flex gap-4 pt-2 border-t border-emerald-500/20 hidden">
					<label className="flex items-center gap-2 cursor-pointer font-mono text-sm">
						<input
							type="radio"
							checked={zipState.useStoredZip}
							onChange={() => zipState.switchToStored()}
							className="w-4 h-4 accent-emerald-500"
						/>
						<span className="text-emerald-700 dark:text-emerald-300">
							使用此文件
						</span>
					</label>
					<label className="flex items-center gap-2 cursor-pointer font-mono text-sm">
						<input
							type="radio"
							checked={!zipState.useStoredZip}
							onChange={() => zipState.switchToUpload()}
							className="w-4 h-4 accent-emerald-500"
						/>
						<span className="text-emerald-700 dark:text-emerald-300">
							上传新文件
						</span>
					</label>
				</div>

				{!zipState.useStoredZip && (
					<div className="flex gap-2 items-center">
						<Input
							type="file"
							accept=".zip,.tar,.tar.gz,.tar.bz2,.7z,.rar"
							onChange={(e) => {
								const file = e.target.files?.[0];
								if (file) {
									const v = validateZipFile(file);
									if (!v.valid) {
										toast.error(v.error || "文件无效");
										e.target.value = "";
										return;
									}
									zipState.handleFileSelect(file, e.target);
								}
							}}
							className="h-9 flex-1 border border-border rounded bg-background px-3 py-1.5 text-sm font-mono file:mr-3 file:py-1 file:px-3 file:rounded file:border-0 file:text-xs file:font-mono file:bg-primary/20 file:text-primary hover:file:bg-primary/30 focus:outline-none focus:ring-1 focus:ring-primary/50"
						/>
						{zipState.zipFile && (
							<Button
								size="sm"
								onClick={onUpload}
								disabled={uploading}
								className="h-9 px-3 cyber-btn-primary"
							>
								{uploading ? (
									<Loader2 className="w-4 h-4 animate-spin" />
								) : (
									<Upload className="w-4 h-4" />
								)}
							</Button>
						)}
					</div>
				)}
			</div>
		);
	}

	return (
		<div className="p-3 border border-dashed border-amber-500/50 rounded bg-amber-50 dark:bg-amber-950/20">
			<div className="flex items-start gap-3">
				<div className="p-1.5 bg-amber-500/20 rounded">
					<Upload className="w-4 h-4 text-amber-600 dark:text-amber-400" />
				</div>
				<div className="flex-1">
					<p className="text-sm font-bold text-amber-700 dark:text-amber-300 font-mono uppercase">
						上传源码归档
					</p>
					<div className="flex gap-2 items-center mt-2">
						<Input
							type="file"
							accept=".zip,.tar,.tar.gz,.tar.bz2,.7z,.rar"
							onChange={(e) => {
								const file = e.target.files?.[0];
								if (file) {
									const v = validateZipFile(file);
									if (!v.valid) {
										toast.error(v.error || "文件无效");
										e.target.value = "";
										return;
									}
									zipState.handleFileSelect(file, e.target);
								}
							}}
							className="h-9 flex-1 border border-border rounded bg-background px-3 py-1.5 text-sm font-mono file:mr-3 file:py-1 file:px-3 file:rounded file:border-0 file:text-xs file:font-mono file:bg-primary/20 file:text-primary hover:file:bg-primary/30 focus:outline-none focus:ring-1 focus:ring-primary/50"
						/>
						{zipState.zipFile && (
							<Button
								size="sm"
								onClick={onUpload}
								disabled={uploading}
								className="h-9 px-3 cyber-btn-primary"
							>
								{uploading ? (
									<Loader2 className="w-4 h-4 animate-spin" />
								) : (
									<Upload className="w-4 h-4" />
								)}
							</Button>
						)}
					</div>
					{zipState.zipFile && (
						<p className="text-xs text-amber-600 dark:text-amber-400 mt-2 font-mono">
							已选: {zipState.zipFile.name} (
							{formatFileSize(zipState.zipFile.size)})
						</p>
					)}
				</div>
			</div>
		</div>
	);
}
