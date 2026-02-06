import { useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { toast } from "sonner";
import {
	Dialog,
	DialogContent,
	DialogHeader,
	DialogTitle,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { Checkbox } from "@/components/ui/checkbox";
import { Badge } from "@/components/ui/badge";
import {
	Bot,
	CheckCircle2,
	Loader2,
	Search,
	Shield,
	TerminalSquare,
	Upload,
	Zap,
	Sparkles,
} from "lucide-react";
import { api } from "@/shared/config/database";
import type { Project } from "@/shared/types";
import { isRepositoryProject, isZipProject } from "@/shared/utils/projectUtils";
import { createAgentTask } from "@/shared/api/agentTasks";
import { runAgentPreflightCheck } from "@/shared/api/agentPreflight";
import {
	createOpengrepScanTask,
	getOpengrepRules,
	type OpengrepRule,
} from "@/shared/api/opengrep";
import { createGitleaksScanTask } from "@/shared/api/gitleaks";
import { getZipFileInfo, uploadZipFile } from "@/shared/utils/zipStorage";
import { validateZipFile } from "@/features/projects/services/repoZipScan";

export type AuditCreateMode = "static" | "agent";

interface CreateProjectAuditDialogProps {
	open: boolean;
	onOpenChange: (open: boolean) => void;
	onTaskCreated?: () => void;
	preselectedProjectId?: string;
	initialMode?: AuditCreateMode;
	lockMode?: boolean;
	allowUploadProject?: boolean;
	navigateOnSuccess?: boolean;
	createButtonVariant?: "single" | "dual";
	primaryCreateLabel?: string;
	secondaryCreateLabel?: string;
	onSecondaryCreateSuccess?: () => void;
	showReturnButton?: boolean;
	onReturn?: () => void;
}

const extractApiErrorMessage = (error: unknown): string => {
	if (error instanceof Error) {
		const detail = (error as any)?.response?.data?.detail;
		if (typeof detail === "string" && detail.trim()) return detail;
		return error.message || "未知错误";
	}
	const detail = (error as any)?.response?.data?.detail;
	if (typeof detail === "string" && detail.trim()) return detail;
	return "未知错误";
};

export default function CreateProjectAuditDialog({
	open,
	onOpenChange,
	onTaskCreated,
	preselectedProjectId,
	initialMode = "static",
	lockMode = false,
	allowUploadProject = false,
	navigateOnSuccess = true,
	createButtonVariant = "single",
	primaryCreateLabel = "创建审计任务",
	secondaryCreateLabel = "创建并返回",
	onSecondaryCreateSuccess,
	showReturnButton = false,
	onReturn,
}: CreateProjectAuditDialogProps) {
	const navigate = useNavigate();
	const [projects, setProjects] = useState<Project[]>([]);
	const [loadingProjects, setLoadingProjects] = useState(false);
	const [creating, setCreating] = useState(false);
	const [searchTerm, setSearchTerm] = useState("");
	const [sourceMode, setSourceMode] = useState<"existing" | "upload">("existing");
	const [selectedProjectId, setSelectedProjectId] = useState("");
	const [newProjectName, setNewProjectName] = useState("");
	const [newProjectDescription, setNewProjectDescription] = useState("");
	const [newProjectFile, setNewProjectFile] = useState<File | null>(null);
	const [generatingDescription, setGeneratingDescription] = useState(false);
	const [mode, setMode] = useState<AuditCreateMode>("static");
	const [branchName, setBranchName] = useState("main");
	const [opengrepEnabled, setOpengrepEnabled] = useState(true);
	const [gitleaksEnabled, setGitleaksEnabled] = useState(false);
	const [activeRules, setActiveRules] = useState<OpengrepRule[]>([]);
	const [loadingRules, setLoadingRules] = useState(false);

	const activeProjects = useMemo(
		() => projects.filter((project) => project.is_active),
		[projects],
	);

	const filteredProjects = useMemo(() => {
		if (!searchTerm.trim()) return activeProjects;
		const keyword = searchTerm.trim().toLowerCase();
		return activeProjects.filter(
			(project) =>
				project.name.toLowerCase().includes(keyword) ||
				(project.description || "").toLowerCase().includes(keyword),
		);
	}, [activeProjects, searchTerm]);

	const selectedProject = activeProjects.find(
		(project) => project.id === selectedProjectId,
	);
	const dialogTitle =
		lockMode && initialMode === "agent" ? "创建智能审计" : lockMode ? "创建静态审计" : "创建审计";
	const dialogSubtitle =
		lockMode && initialMode === "agent"
			? "Create Intelligent Audit Task"
			: lockMode
				? "Create Static Audit Task"
				: "Create Audit Task";

	useEffect(() => {
		if (!open) return;
		setSearchTerm("");
		setSourceMode("existing");
		setSelectedProjectId(preselectedProjectId || "");
		setNewProjectName("");
		setNewProjectDescription("");
		setNewProjectFile(null);
		setGeneratingDescription(false);
		setMode(initialMode || "static");
		setBranchName("main");
		setOpengrepEnabled(true);
		setGitleaksEnabled(false);

		const loadProjects = async () => {
			try {
				setLoadingProjects(true);
				const data = await api.getProjects();
				setProjects(data);
			} catch (error) {
				console.error("加载项目失败:", error);
				toast.error("加载项目失败");
			} finally {
				setLoadingProjects(false);
			}
		};

		const loadRules = async () => {
			try {
				setLoadingRules(true);
				const rules = await getOpengrepRules({ is_active: true });
				setActiveRules(rules);
			} catch (error) {
				console.error("加载启用规则失败:", error);
				toast.error("加载启用规则失败");
			} finally {
				setLoadingRules(false);
			}
		};

		loadProjects();
		loadRules();
	}, [open, preselectedProjectId, initialMode]);

	useEffect(() => {
		if (!open) return;
		if (selectedProjectId) return;
		if (activeProjects.length === 0) return;
		setSelectedProjectId(activeProjects[0].id);
	}, [open, selectedProjectId, activeProjects]);

	useEffect(() => {
		if (!selectedProject) return;
		setBranchName(selectedProject.default_branch || "main");
	}, [selectedProject?.id]);

	const canCreate = useMemo(() => {
		if (sourceMode === "upload") {
			if (!newProjectName.trim() || !newProjectFile) return false;
			if (mode === "static") {
				return opengrepEnabled || gitleaksEnabled;
			}
			return true;
		}
		if (!selectedProject) return false;
		if (mode === "static") {
			return opengrepEnabled || gitleaksEnabled;
		}
		if (isRepositoryProject(selectedProject)) {
			return Boolean(branchName.trim());
		}
		return true;
	}, [
		sourceMode,
		newProjectName,
		newProjectFile,
		selectedProject,
		mode,
		opengrepEnabled,
		gitleaksEnabled,
		branchName,
	]);

	const createStaticTasksForProject = async (project: Project) => {
		let opengrepTask: { id: string } | null = null;
		let gitleaksTask: { id: string } | null = null;

		if (opengrepEnabled) {
			const ruleIds = activeRules.map((rule) => rule.id);
			if (ruleIds.length === 0) {
				throw new Error("当前没有启用规则，请先启用规则");
			}
			opengrepTask = await createOpengrepScanTask({
				project_id: project.id,
				name: `静态分析-Opengrep-${project.name}`,
				rule_ids: ruleIds,
				target_path: ".",
			});
		}

		if (gitleaksEnabled) {
			gitleaksTask = await createGitleaksScanTask({
				project_id: project.id,
				name: `静态分析-Gitleaks-${project.name}`,
				target_path: ".",
				no_git: true,
			});
		}

		const primaryTaskId = opengrepTask?.id || gitleaksTask?.id;
		if (!primaryTaskId) {
			throw new Error("静态审计任务创建失败");
		}
		const params = new URLSearchParams();
		if (opengrepTask && gitleaksTask) {
			params.set("opengrepTaskId", opengrepTask.id);
			params.set("gitleaksTaskId", gitleaksTask.id);
		} else if (!opengrepTask && gitleaksTask) {
			params.set("tool", "gitleaks");
		}
		return { primaryTaskId, params };
	};

	const runAgentTaskForProject = async (project: Project) => {
		const checkToast = toast.loading("正在检查智能审计配置（LLM / RAG）...");
		const preflight = await runAgentPreflightCheck();
		toast.dismiss(checkToast);
		if (!preflight.ok) {
			throw new Error(preflight.message || "智能审计配置检查未通过");
		}
		return createAgentTask({
			project_id: project.id,
			name: `智能审计-${project.name}`,
			branch_name: isRepositoryProject(project)
				? branchName.trim() || project.default_branch || "main"
				: undefined,
			verification_level: "sandbox",
		});
	};

	const stripArchiveSuffix = (fileName: string) =>
		fileName.replace(/\.(tar\.gz|tar\.bz2|tar\.xz|tgz|tbz2|zip|tar|7z|rar)$/i, "");

	const handleNewProjectFileSelect = (event: React.ChangeEvent<HTMLInputElement>) => {
		const file = event.target.files?.[0] || null;
		if (!file) return;
		const validation = validateZipFile(file);
		if (!validation.valid) {
			toast.error(validation.error || "文件无效");
			event.target.value = "";
			return;
		}
		setNewProjectFile(file);
		setGeneratingDescription(false);
		const inferredName = stripArchiveSuffix(file.name).trim();
		if (inferredName) setNewProjectName(inferredName);
		event.target.value = "";
	};

	const handleGenerateNewProjectDescription = async () => {
		if (!newProjectFile) {
			toast.error("请先选择项目压缩包");
			return;
		}

		try {
			setGeneratingDescription(true);
			const result = await api.generateProjectDescription({
				file: newProjectFile,
				project_name: newProjectName,
			});
			setNewProjectDescription(result.description || "");
			if (result.source === "llm") {
				toast.success("已生成项目描述");
			} else {
				toast.success("LLM不可用，已回退静态描述");
			}
		} catch (error) {
			toast.error(`生成失败: ${extractApiErrorMessage(error)}`);
		} finally {
			setGeneratingDescription(false);
		}
	};

	const handleCreate = async (action: "primary" | "secondary" = "primary") => {
		try {
			setCreating(true);
			if (sourceMode === "upload") {
				if (!newProjectName.trim() || !newProjectFile) {
					toast.error("请先上传项目并填写项目名");
					return;
				}
				let createdProject: Project | null = null;
				try {
					createdProject = await api.createProject({
						name: newProjectName.trim(),
						description: newProjectDescription.trim() || undefined,
						source_type: "zip",
						repository_type: "other",
						repository_url: undefined,
						default_branch: "main",
						programming_languages: [],
					} as any);
					const uploadResult = await uploadZipFile(createdProject.id, newProjectFile);
					if (!uploadResult.success) {
						throw new Error(uploadResult.message || "压缩包上传失败");
					}

						if (mode === "static") {
							const result = await createStaticTasksForProject(createdProject);
							onOpenChange(false);
							onTaskCreated?.();
							toast.success("静态审计任务已创建");
							if (action === "secondary") {
								onSecondaryCreateSuccess?.();
							} else if (navigateOnSuccess) {
								navigate(
									`/static-analysis/${result.primaryTaskId}${result.params.toString() ? `?${result.params.toString()}` : ""
									}`,
								);
							}
						} else {
							const agentTask = await runAgentTaskForProject(createdProject);
							onOpenChange(false);
							onTaskCreated?.();
							toast.success("智能审计任务已创建");
							if (action === "secondary") {
								onSecondaryCreateSuccess?.();
							} else if (navigateOnSuccess) {
								navigate(`/agent-audit/${agentTask.id}`);
							}
						}
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

			if (mode === "static") {
				if (!isZipProject(selectedProject)) {
					toast.error("静态审计仅支持源码压缩包项目");
					return;
				}
				const zipInfo = await getZipFileInfo(selectedProject.id);
				if (!zipInfo.has_file) {
					toast.error("该项目未上传源码压缩包");
					return;
				}
				if (!opengrepEnabled && !gitleaksEnabled) {
					toast.error("请至少启用一个扫描引擎");
					return;
				}

				const result = await createStaticTasksForProject(selectedProject);

				onOpenChange(false);
				onTaskCreated?.();
				toast.success("静态审计任务已创建");
				if (action === "secondary") {
					onSecondaryCreateSuccess?.();
				} else if (navigateOnSuccess) {
					navigate(
						`/static-analysis/${result.primaryTaskId}${result.params.toString() ? `?${result.params.toString()}` : ""
						}`,
					);
				}
				return;
			}

			if (isZipProject(selectedProject)) {
				const zipInfo = await getZipFileInfo(selectedProject.id);
				if (!zipInfo.has_file) {
					toast.error("该项目未上传源码压缩包");
					return;
				}
			}

			const agentTask = await runAgentTaskForProject(selectedProject);

			onOpenChange(false);
			onTaskCreated?.();
			toast.success("智能审计任务已创建");
			if (action === "secondary") {
				onSecondaryCreateSuccess?.();
			} else if (navigateOnSuccess) {
				navigate(`/agent-audit/${agentTask.id}`);
			}
		} catch (error) {
			toast.error(`创建失败: ${extractApiErrorMessage(error)}`);
		} finally {
			setCreating(false);
		}
	};

	return (
		<Dialog open={open} onOpenChange={onOpenChange}>
			<DialogContent className="!w-[min(92vw,760px)] !max-w-none max-h-[88vh] p-0 gap-0 flex flex-col cyber-dialog border border-border rounded-lg">
				<DialogHeader className="px-6 py-4 border-b border-border bg-muted">
					<DialogTitle className="flex items-center gap-3 font-mono">
						<div className="p-2 rounded border border-sky-500/30 bg-sky-500/10">
							<TerminalSquare className="w-5 h-5 text-sky-300" />
						</div>
						<div>
							<p className="text-base font-bold uppercase tracking-wider text-foreground">
								{dialogTitle}
							</p>
							{/* <p className="text-xs text-muted-foreground">{dialogSubtitle}</p> */}
						</div>
					</DialogTitle>
				</DialogHeader>

				<div className="p-6 space-y-5 overflow-y-auto flex-1">
					{allowUploadProject && (
						<div className="space-y-2">
							<p className="text-xs uppercase tracking-wider text-muted-foreground">项目来源</p>
							<div className="grid grid-cols-2 gap-2">
								<Button
									type="button"
									variant={sourceMode === "existing" ? "default" : "outline"}
									className={sourceMode === "existing" ? "cyber-btn-primary h-10" : "cyber-btn-outline h-10"}
									onClick={() => {
										setSourceMode("existing");
										setGeneratingDescription(false);
									}}
									disabled={creating || generatingDescription}
								>
									选择已有项目
								</Button>
								<Button
									type="button"
									variant={sourceMode === "upload" ? "default" : "outline"}
									className={sourceMode === "upload" ? "cyber-btn-primary h-10" : "cyber-btn-outline h-10"}
									onClick={() => {
										setSourceMode("upload");
										setGeneratingDescription(false);
									}}
									disabled={creating || generatingDescription}
								>
									上传新项目
								</Button>
							</div>
						</div>
					)}
					{!lockMode && (
						<div className="space-y-2">
							<p className="text-xs uppercase tracking-wider text-muted-foreground">
								审计方式
							</p>
							<div className="grid grid-cols-2 gap-2">
								<Button
									type="button"
									variant={mode === "static" ? "default" : "outline"}
									className={
										mode === "static"
											? "cyber-btn-primary h-10 justify-start"
											: "cyber-btn-outline h-10 justify-start"
									}
									onClick={() => setMode("static")}
									disabled={creating || generatingDescription}
								>
									<Zap className="w-4 h-4 mr-2" />
									静态审计
								</Button>
								<Button
									type="button"
									variant={mode === "agent" ? "default" : "outline"}
									className={
										mode === "agent"
											? "h-10 justify-start border border-violet-500/40 bg-violet-500/20 text-violet-100 hover:bg-violet-500/30"
											: "cyber-btn-outline h-10 justify-start"
									}
									onClick={() => setMode("agent")}
									disabled={creating || generatingDescription}
								>
									<Bot className="w-4 h-4 mr-2" />
									智能审计
								</Button>
							</div>
						</div>
					)}

					{sourceMode === "existing" ? (
						<div className="space-y-3">
							<div className="relative">
								{/* <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground" /> */}
								<Input
									value={searchTerm}
									onChange={(event) => setSearchTerm(event.target.value)}
									placeholder="搜索项目..."
									className="pl-12 h-9 cyber-input"
									disabled={creating || generatingDescription}
								/>
							</div>
							<div className="border border-border rounded-lg max-h-[280px] overflow-y-auto p-2 space-y-2">
								{loadingProjects ? (
									<div className="py-10 flex items-center justify-center text-sm text-muted-foreground">
										<Loader2 className="w-4 h-4 animate-spin mr-2" />
										加载项目中...
									</div>
								) : filteredProjects.length > 0 ? (
									filteredProjects.map((project) => (
										<button
											key={project.id}
											type="button"
											onClick={() => setSelectedProjectId(project.id)}
											className={`w-full text-left p-3 rounded border transition-colors ${project.id === selectedProjectId
													? "border-sky-500/50 bg-sky-500/10"
													: "border-border hover:border-sky-500/30 bg-background"
												}`}
											disabled={creating || generatingDescription}
										>
											<div className="flex items-start justify-between gap-3">
												<div className="min-w-0">
													<p className="text-sm font-semibold text-foreground">
														{project.name}
													</p>
													{project.description && (
														<p className="text-xs text-muted-foreground mt-1 line-clamp-1">
															{project.description}
														</p>
													)}
												</div>
												<div className="flex items-center gap-2 shrink-0">
													<Badge
														className={
															project.source_type === "zip"
																? "cyber-badge-warning"
																: "cyber-badge-info"
														}
													>
														{project.source_type === "zip" ? "ZIP" : "仓库"}
													</Badge>
													{project.id === selectedProjectId && (
														<CheckCircle2 className="w-4 h-4 text-sky-400" />
													)}
												</div>
											</div>
										</button>
									))
								) : (
									<div className="py-10 text-center text-sm text-muted-foreground">
										未找到可用项目
									</div>
								)}
							</div>
						</div>
					) : (
						<div className="space-y-3 border border-border rounded-lg p-4">
							<div>
								<p className="text-xs uppercase tracking-wider text-muted-foreground mb-1">项目名称</p>
								<Input
									value={newProjectName}
									onChange={(event) => setNewProjectName(event.target.value)}
									placeholder="请输入项目名称"
									className="h-9 cyber-input"
									disabled={creating || generatingDescription}
								/>
							</div>
							<div>
								<div className="mb-1 flex items-center justify-between gap-2">
									<p className="text-xs uppercase tracking-wider text-muted-foreground">
										项目描述（可选）
									</p>
									<Button
										type="button"
										variant="outline"
										className="cyber-btn-outline h-8 text-xs"
										onClick={handleGenerateNewProjectDescription}
										disabled={
											creating ||
											generatingDescription ||
											!newProjectFile
										}
									>
										<Sparkles className="w-3 h-3 mr-1.5" />
										{generatingDescription ? "生成中..." : "一键生成"}
									</Button>
								</div>
								<Textarea
									value={newProjectDescription}
									onChange={(event) => setNewProjectDescription(event.target.value)}
									placeholder="请输入项目描述"
									rows={2}
									className="cyber-input min-h-[72px]"
									disabled={creating || generatingDescription}
								/>
							</div>
							<div>
								<p className="text-xs uppercase tracking-wider text-muted-foreground mb-2">源码压缩包</p>
								<label className="inline-flex">
									<input
										type="file"
										accept=".zip,.tar,.tar.gz,.tar.bz2,.7z,.rar"
										className="hidden"
										onChange={handleNewProjectFileSelect}
										disabled={creating || generatingDescription}
									/>
									<span className="cyber-btn-outline h-9 px-3 inline-flex items-center cursor-pointer">
										<Upload className="w-4 h-4 mr-2" />
										选择压缩包
									</span>
								</label>
								{newProjectFile && (
									<p className="text-xs text-emerald-400 mt-2">{newProjectFile.name}</p>
								)}
							</div>
						</div>
					)}

					{mode === "static" ? (
						<div className="border border-border rounded-lg p-4 space-y-3">
							<div className="flex items-center justify-between">
								<p className="text-sm font-semibold text-foreground">静态扫描引擎</p>
								<p className="text-xs text-muted-foreground">
									{loadingRules ? "规则加载中..." : `已启用规则 ${activeRules.length}`}
								</p>
							</div>
							<div className="grid grid-cols-1 md:grid-cols-2 gap-2">
								<label className="border border-border rounded p-3 flex items-center gap-3 cursor-pointer hover:border-sky-500/30">
									<Checkbox
										checked={opengrepEnabled}
										onCheckedChange={(checked) => setOpengrepEnabled(Boolean(checked))}
										disabled={creating || generatingDescription}
										className="data-[state=checked]:bg-sky-500 data-[state=checked]:border-sky-500"
									/>
									<div>
										<p className="text-sm text-foreground font-semibold">Opengrep</p>
										<p className="text-xs text-muted-foreground">规则扫描</p>
									</div>
								</label>
								<label className="border border-border rounded p-3 flex items-center gap-3 cursor-pointer hover:border-sky-500/30">
									<Checkbox
										checked={gitleaksEnabled}
										onCheckedChange={(checked) => setGitleaksEnabled(Boolean(checked))}
										disabled={creating || generatingDescription}
										className="data-[state=checked]:bg-sky-500 data-[state=checked]:border-sky-500"
									/>
									<div>
										<p className="text-sm text-foreground font-semibold">Gitleaks</p>
										<p className="text-xs text-muted-foreground">密钥泄露扫描</p>
									</div>
								</label>
							</div>
						</div>
					) : (
						<div className="rounded-lg border border-violet-500/20 bg-violet-500/5 p-3">
							<p className="text-sm text-violet-200">执行前会自动校验 LLM / RAG 配置。</p>
							<p className="text-xs text-violet-300/80 mt-1">校验通过后开始智能审计。</p>
						</div>
					)}

					{mode === "agent" &&
						selectedProject &&
						isRepositoryProject(selectedProject) && (
							<div className="space-y-2">
								<p className="text-xs uppercase tracking-wider text-muted-foreground">审计分支</p>
								<Input
									value={branchName}
									onChange={(event) => setBranchName(event.target.value)}
									placeholder="main"
									className="h-9 cyber-input"
									disabled={creating || generatingDescription}
								/>
							</div>
						)}
				</div>

					<div className="px-6 py-4 border-t border-border bg-muted flex justify-end gap-2">
						
						<Button
							type="button"
							variant="outline"
						className="cyber-btn-outline"
						onClick={() => onOpenChange(false)}
						disabled={creating || generatingDescription}
					>
						取消
						</Button>
						<Button
							type="button"
							className="cyber-btn-primary"
							onClick={() => handleCreate("primary")}
							disabled={!canCreate || creating || generatingDescription}
						>
							{creating ? (
							<>
								<Loader2 className="w-4 h-4 animate-spin mr-2" />
								创建中...
							</>
							) : (
								<>
									<Shield className="w-4 h-4 mr-2" />
									{primaryCreateLabel}
								</>
							)}
						</Button>
						{createButtonVariant === "dual" && (
							<Button
								type="button"
								className="cyber-btn-primary"
								onClick={() => handleCreate("secondary")}
								disabled={!canCreate || creating || generatingDescription}
							>
								{creating ? (
									<>
										<Loader2 className="w-4 h-4 animate-spin mr-2" />
										创建中...
									</>
								) : (
									<>
										<Shield className="w-4 h-4 mr-2" />
										{secondaryCreateLabel}
									</>
								)}
							</Button>
						)}
					</div>
				</DialogContent>
			</Dialog>
	);
}
