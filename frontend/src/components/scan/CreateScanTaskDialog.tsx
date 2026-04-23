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
import {
	Search,
	Upload,
	Package,
	Shield,
	Loader2,
	Zap,
	Bot,
} from "lucide-react";
import { toast } from "sonner";
import { api } from "@/shared/api/database";
import { createAgentTask } from "@/shared/api/agentTasks";
import {
	createOpengrepScanTask,
	getOpengrepRules,
	type OpengrepRule,
} from "@/shared/api/opengrep";
import {
	getOpengrepActiveRules,
	setOpengrepActiveRules,
	subscribeOpengrepActiveRules,
} from "@/shared/stores/opengrepRulesStore";

import { useProjects } from "./hooks/useTaskForm";
import { useZipFile } from "./hooks/useZipFile";
import FileSelectionDialog from "./FileSelectionDialog";
import AgentModeSelector, {
	type ScanMode,
	type StaticTool,
	type StaticToolSelection,
} from "@/components/agent/AgentModeSelector";
import AdvancedOptionsSection from "./create-scan-task/AdvancedOptionsSection";
import ProjectCard from "./create-scan-task/ProjectCard";
import ZipUploadCard from "./create-scan-task/ZipUploadCard";
import {
	DEFAULT_SCAN_EXCLUDES,
	extractCreateScanTaskApiErrorMessage,
	stripScanArchiveSuffix,
} from "./create-scan-task/utils";

import { validateZipFile } from "@/features/projects/services/repoZipScan";
import { isZipProject } from "@/shared/utils/projectUtils";
import { INTELLIGENT_TASK_NAME_MARKER } from "@/features/tasks/services/taskActivities";
import { appendReturnTo } from "@/shared/utils/findingRoute";
import {
	appendStaticScanBatchMarker,
	createStaticScanBatchId,
} from "@/shared/utils/staticScanBatch";
import StaticEngineConfigDialog from "@/components/scan/create-scan-task/StaticEngineConfigDialog";
import { buildScanEngineConfigRoute } from "@/shared/constants/scanEngines";

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
	const [excludePatterns, setExcludePatterns] = useState(DEFAULT_SCAN_EXCLUDES);
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
		bandit: false,
		phpstan: false,
		pmd: false,
	});
	const [staticRules, setStaticRules] = useState<OpengrepRule[]>([]);
	const [selectedRuleIds, setSelectedRuleIds] = useState<string[]>([]);
	const [configEngine, setConfigEngine] = useState<StaticTool | null>(null);

	const { projects, loading, loadProjects } = useProjects();
	const selectedProject = projects.find((p) => p.id === selectedProjectId);
	const zipState = useZipFile(selectedProject, projects);

	const filteredProjects = useMemo(() => {
		const visibleProjects = projects.filter((project) => isZipProject(project));
		if (!searchTerm) return visibleProjects;
		const term = searchTerm.toLowerCase();
		return visibleProjects.filter(
			(p) =>
				p.name.toLowerCase().includes(term) ||
				p.description?.toLowerCase().includes(term),
		);
	}, [projects, searchTerm]);

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
			setStaticTools({ opengrep: true, gitleaks: false, bandit: false, phpstan: false, pmd: false });
			setConfigEngine(null);
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

		const inferredName = stripScanArchiveSuffix(file.name).trim();
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
	const canSelectFiles = useMemo(() => {
		if (!selectedProject) return false;
		const isZip = isZipProject(selectedProject);
		const hasStoredZip = Boolean(zipState.storedZipInfo?.has_file);
		const useStored = zipState.useStoredZip;
		return isZip && useStored && hasStoredZip;
	}, [selectedProject, zipState.storedZipInfo?.has_file, zipState.useStoredZip]);

	const createStaticScanTasksForProject = async (
		projectId: string,
		projectName: string,
	) => {
		if (!staticTools.opengrep) {
			throw new Error("请选择至少一个静态分析工具");
		}

		let opengrepTask: { id: string } | null = null;
		const staticBatchId = createStaticScanBatchId();

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
					name: appendStaticScanBatchMarker(
						`静态分析-Opengrep-${projectName}`,
						staticBatchId,
					),
					rule_ids: activeRuleIds,
					target_path: ".",
				});
			} catch (error) {
				const apiMsg = extractCreateScanTaskApiErrorMessage(error);
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
					name: appendStaticScanBatchMarker(
						`静态分析-Opengrep-${projectName}`,
						staticBatchId,
					),
					rule_ids: retryRuleIds,
					target_path: ".",
				});
			}
		}
		const primaryTaskId = opengrepTask?.id;
		if (!primaryTaskId) {
			throw new Error("静态分析任务创建失败");
		}

		const params = new URLSearchParams();
		if (opengrepTask) {
			params.set("opengrepTaskId", opengrepTask.id);
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

				try {
					const createdProject = await api.createProjectWithZip({
						name: newProjectName.trim(),
						source_type: "zip",
						repository_type: "other",
						repository_url: undefined,
						default_branch: "main",
						programming_languages: [],
					} as any, newProjectFile);

					if (scanMode === "agent") {
						const agentTask = await createAgentTask({
							project_id: createdProject.id,
							name: `智能审计-${createdProject.name}`,
							description: `${INTELLIGENT_TASK_NAME_MARKER}智能审计任务`,
							target_files:
								effectiveTargetFiles.length > 0
									? effectiveTargetFiles
									: undefined,
							use_prompt_skills: true,
							verification_level: "analysis_with_poc_plan",
						});

						onOpenChange(false);
						onTaskCreated();
						toast.success("智能审计任务已创建");
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
					name: `智能审计-${selectedProject.name}`,
					description: `${INTELLIGENT_TASK_NAME_MARKER}智能审计任务`,
					exclude_patterns: excludePatterns,
					target_files:
						effectiveTargetFiles.length > 0 ? effectiveTargetFiles : undefined,
					use_prompt_skills: true,
					verification_level: "analysis_with_poc_plan",
				});

				onOpenChange(false);
				onTaskCreated();
				toast.success("智能审计任务已创建");
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
			const msg = extractCreateScanTaskApiErrorMessage(error);
			toast.error(`启动失败: ${msg}`);
		} finally {
			setCreating(false);
			setSelectedFiles(undefined);
			setExcludePatterns(DEFAULT_SCAN_EXCLUDES);
		}
	};

		const canStart = useMemo(() => {
		if (sourceMode === "upload") {
			if (!newProjectName.trim() || !newProjectFile) return false;
			if (scanMode === "static") {
				return staticTools.opengrep;
			}
			return true;
		}
		if (!selectedProject) return false;
		if (scanMode === "static") {
			return (
				isZipProject(selectedProject) &&
				!!zipState.storedZipInfo?.has_file &&
				staticTools.opengrep
			);
		}
		if (!isZipProject(selectedProject)) return false;
		const ready =
			(zipState.useStoredZip && zipState.storedZipInfo?.has_file) ||
			!!zipState.zipFile;
		if (!ready) return false;
		return true;
	}, [
		sourceMode,
		newProjectName,
		newProjectFile,
		selectedProject,
		zipState,
		scanMode,
		effectiveTargetFiles,
		staticTools.opengrep,
	]);

	const handleOpenEngineConfig = (engine: StaticTool) => {
		setConfigEngine(engine);
	};

	const handleNavigateToEngineConfig = (engine: StaticTool) => {
		onOpenChange(false);
		navigate(buildScanEngineConfigRoute(engine));
	};

	return (
		<>
			<Dialog open={open} onOpenChange={onOpenChange}>
				<DialogContent
					aria-describedby={undefined}
					className="!w-[min(90vw,520px)] !max-w-none max-h-[85vh] flex flex-col p-0 gap-0 cyber-dialog border border-border rounded-lg"
				>
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
								onOpenStaticToolConfig={handleOpenEngineConfig}
							/>
						)}

						{/* 配置区域 */}
						{sourceMode === "existing" && selectedProject && (
							<div className="space-y-4">
								<span className="text-sm font-mono font-bold uppercase text-muted-foreground">
									配置
								</span>

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

								{scanMode === "static" && null}

								<AdvancedOptionsSection
									open={showAdvanced}
									onOpenChange={setShowAdvanced}
									excludePatterns={excludePatterns}
									onResetExcludes={() =>
										setExcludePatterns(DEFAULT_SCAN_EXCLUDES)
									}
									onRemoveExclude={(pattern) =>
										setExcludePatterns((prev) =>
											prev.filter((item) => item !== pattern),
										)
									}
									onAddExclude={(pattern) => {
										if (!excludePatterns.includes(pattern)) {
											setExcludePatterns((prev) => [...prev, pattern]);
										}
									}}
									onCustomExcludeEnter={(value) => {
										const trimmed = value.trim();
										if (trimmed && !excludePatterns.includes(trimmed)) {
											setExcludePatterns((prev) => [...prev, trimmed]);
										}
									}}
									canSelectFiles={canSelectFiles}
									selectedFiles={selectedFiles}
									onResetSelectedFiles={() => setSelectedFiles(undefined)}
									onOpenFileSelection={() => setShowFileSelection(true)}
								/>
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
									启动智能审计
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
			<StaticEngineConfigDialog
				engine={configEngine ?? "opengrep"}
				open={configEngine !== null}
				onOpenChange={(open) => {
					if (!open) setConfigEngine(null);
				}}
				scanMode="static"
				enabled={configEngine ? staticTools[configEngine] : false}
				creating={creating}
				blockedReason={null}
				onNavigateToEngineConfig={(engine) => handleNavigateToEngineConfig(engine)}
			/>

			{sourceMode === "existing" && selectedProjectId ? (
				<FileSelectionDialog
					open={showFileSelection}
					onOpenChange={setShowFileSelection}
					projectId={selectedProjectId}
					excludePatterns={excludePatterns}
					onConfirm={setSelectedFiles}
				/>
			) : null}
		</>
	);
}
