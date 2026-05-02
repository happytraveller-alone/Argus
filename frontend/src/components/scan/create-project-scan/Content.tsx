import type { ChangeEvent } from "react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import {
	Dialog,
	DialogContent,
	DialogHeader,
	DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Brain, Loader2, Settings2, Shield, TerminalSquare, Upload } from "lucide-react";
import type { Project } from "@/shared/types";
import { SUPPORTED_ARCHIVE_INPUT_ACCEPT } from "@/features/projects/services/repoZipScan";
import type { StaticTool } from "@/components/agent/AgentModeSelector";
import StaticEngineConfigDialog from "@/components/scan/create-scan-task/StaticEngineConfigDialog";

type StaticEngineItem = {
	key: StaticTool;
	title: string;
	checked: boolean;
	setChecked: (enabled: boolean) => void;
};

export default function CreateProjectScanDialogContent({
	open,
	onOpenChange,
	dialogTitle,
	allowUploadProject,
	sourceMode,
	setSourceMode,
	creating,
	loadingProjects,
	lockProjectSelection,
	searchTerm,
	setSearchTerm,
	filteredProjects,
	visibleProjects,
	projectPage,
	projectTotalPages,
	setProjectPage,
	selectedProject,
	selectedProjectId,
	setSelectedProjectId,
	newProjectName,
	setNewProjectName,
	newProjectFile,
	handleNewProjectFileSelect,
	opengrepEnabled,
	setOpengrepEnabled,
	codeqlEnabled,
	setCodeqlEnabled,
	showReturnButton,
	onReturn,
	primaryCreateLabel,
	secondaryCreateLabel,
	createButtonVariant,
	canCreate,
	handleCreate,
	configEngine,
	setConfigEngine,
	onNavigateToEngineConfig,
	activeTab,
	setActiveTab,
	handleIntelligentCreate,
}: {
	open: boolean;
	onOpenChange: (open: boolean) => void;
	dialogTitle: string;
	allowUploadProject: boolean;
	sourceMode: "existing" | "upload";
	setSourceMode: (mode: "existing" | "upload") => void;
	creating: boolean;
	lockMode: boolean;
	loadingProjects: boolean;
	lockProjectSelection: boolean;
	searchTerm: string;
	setSearchTerm: (value: string) => void;
	filteredProjects: Project[];
	visibleProjects: Project[];
	projectPage: number;
	projectTotalPages: number;
	setProjectPage: (page: number) => void;
	selectedProject: Project | undefined;
	selectedProjectId: string;
	setSelectedProjectId: (id: string) => void;
	newProjectName: string;
	setNewProjectName: (value: string) => void;
	newProjectFile: File | null;
	handleNewProjectFileSelect: (event: ChangeEvent<HTMLInputElement>) => void;
	opengrepEnabled: boolean;
	setOpengrepEnabled: (enabled: boolean) => void;
	codeqlEnabled: boolean;
	setCodeqlEnabled: (enabled: boolean) => void;
	showReturnButton: boolean;
	onReturn?: () => void;
	primaryCreateLabel: string;
	secondaryCreateLabel: string;
	createButtonVariant: "single" | "dual";
	canCreate: boolean;
	handleCreate: (action?: "primary" | "secondary") => void | Promise<void>;
	configEngine: StaticTool | null;
	setConfigEngine: (engine: StaticTool | null) => void;
	onNavigateToEngineConfig: (engine: StaticTool) => void;
	activeTab: "static" | "intelligent";
	setActiveTab: (tab: "static" | "intelligent") => void;
	handleIntelligentCreate: () => void | Promise<void>;
}) {
	const staticEngineItems: StaticEngineItem[] = [
		{
			key: "opengrep",
			title: "Opengrep",
			checked: opengrepEnabled,
			setChecked: setOpengrepEnabled,
		},
		{
			key: "codeql",
			title: "CodeQL",
			checked: codeqlEnabled,
			setChecked: setCodeqlEnabled,
		},
	];

	const canIntelligentCreate = Boolean(selectedProjectId);

	return (
		<>
			<Dialog open={open} onOpenChange={onOpenChange}>
				<DialogContent
					aria-describedby={undefined}
					className="!w-[min(92vw,760px)] !max-w-none max-h-[88vh] p-0 gap-0 flex flex-col cyber-dialog border border-border rounded-lg"
				>
					<DialogHeader className="px-6 py-4 border-b border-border bg-muted">
						<DialogTitle className="flex items-center gap-3 font-mono">
							<div className="p-2 rounded border border-sky-500/30 bg-sky-500/10">
								<TerminalSquare className="w-5 h-5 text-sky-300" />
							</div>
							<p className="text-base font-bold uppercase tracking-wider text-foreground">
								{dialogTitle}
							</p>
						</DialogTitle>
					</DialogHeader>

					{/* Tab bar */}
					<div className="flex border-b border-border bg-muted px-6">
						<button
							type="button"
							onClick={() => setActiveTab("static")}
							className={`relative px-4 py-3 text-xs font-semibold uppercase tracking-wider transition-colors ${
								activeTab === "static"
									? "text-sky-300 after:absolute after:bottom-0 after:left-0 after:right-0 after:h-0.5 after:bg-sky-400"
									: "text-muted-foreground hover:text-foreground"
							}`}
						>
							<Shield className="inline-block w-3.5 h-3.5 mr-1.5 -mt-0.5" />
							静态扫描
						</button>
						<button
							type="button"
							onClick={() => setActiveTab("intelligent")}
							className={`relative px-4 py-3 text-xs font-semibold uppercase tracking-wider transition-colors ${
								activeTab === "intelligent"
									? "text-violet-300 after:absolute after:bottom-0 after:left-0 after:right-0 after:h-0.5 after:bg-violet-400"
									: "text-muted-foreground hover:text-foreground"
							}`}
						>
							<Brain className="inline-block w-3.5 h-3.5 mr-1.5 -mt-0.5" />
							智能扫描
						</button>
					</div>

					<div className="p-6 space-y-5 overflow-y-auto flex-1">
						{/* ── Static tab content ── */}
						{activeTab === "static" ? (
							<>
								{allowUploadProject ? (
									<div className="space-y-2">
										<p className="text-xs uppercase tracking-wider text-muted-foreground">
											项目来源
										</p>
										<div className="grid grid-cols-2 gap-2">
											<Button
												type="button"
												variant={sourceMode === "existing" ? "default" : "outline"}
												className={
													sourceMode === "existing"
														? "cyber-btn-primary h-10"
														: "cyber-btn-outline h-10"
												}
												onClick={() => setSourceMode("existing")}
												disabled={creating}
											>
												选择已有项目
											</Button>
											<Button
												type="button"
												variant={sourceMode === "upload" ? "default" : "outline"}
												className={
													sourceMode === "upload"
														? "cyber-btn-primary h-10"
														: "cyber-btn-outline h-10"
												}
												onClick={() => setSourceMode("upload")}
												disabled={creating}
											>
												上传新项目
											</Button>
										</div>
									</div>
								) : null}

								{sourceMode === "existing" ? (
									<div className="space-y-3">
										{lockProjectSelection ? null : (
											<Input
												value={searchTerm}
												onChange={(event) => setSearchTerm(event.target.value)}
												placeholder="搜索项目..."
												className="h-9 cyber-input"
												disabled={creating}
											/>
										)}
										<div className="border border-border rounded-lg p-2 space-y-2">
											{loadingProjects ? (
												<div className="py-10 flex items-center justify-center text-sm text-muted-foreground">
													<Loader2 className="w-4 h-4 animate-spin mr-2" />
													加载项目中...
												</div>
											) : lockProjectSelection ? (
												selectedProject ? (
													<ProjectChoice
														project={selectedProject}
														selected
														onSelect={() => {}}
														disabled
													/>
												) : (
													<div className="py-10 text-center text-sm text-muted-foreground">
														目标项目不可用，请返回项目管理页重试
													</div>
												)
											) : filteredProjects.length > 0 ? (
												visibleProjects.map((project) => (
													<ProjectChoice
														key={project.id}
														project={project}
														selected={project.id === selectedProjectId}
														onSelect={() => setSelectedProjectId(project.id)}
														disabled={creating}
													/>
												))
											) : (
												<div className="py-10 text-center text-sm text-muted-foreground">
													未找到可用项目
												</div>
											)}
										</div>
										{!lockProjectSelection && filteredProjects.length > 0 ? (
											<div className="flex items-center justify-between gap-3 text-xs text-muted-foreground">
												<span>每页 3 个项目卡片</span>
												<div className="flex items-center gap-2">
													<Button
														type="button"
														variant="outline"
														className="cyber-btn-outline h-8 px-3"
														onClick={() => setProjectPage(Math.max(1, projectPage - 1))}
														disabled={creating || projectPage <= 1}
													>
														上一页
													</Button>
													<span>
														第 {projectPage} / {projectTotalPages} 页
													</span>
													<Button
														type="button"
														variant="outline"
														className="cyber-btn-outline h-8 px-3"
														onClick={() =>
															setProjectPage(Math.min(projectTotalPages, projectPage + 1))
														}
														disabled={creating || projectPage >= projectTotalPages}
													>
														下一页
													</Button>
												</div>
											</div>
										) : null}
									</div>
								) : (
									<div className="space-y-4 border border-border rounded-lg p-4 bg-background">
										<div className="space-y-2">
											<p className="text-xs uppercase tracking-wider text-muted-foreground">
												项目名称
											</p>
											<Input
												value={newProjectName}
												onChange={(event) => setNewProjectName(event.target.value)}
												placeholder="输入项目名称"
												className="h-9 cyber-input"
												disabled={creating}
											/>
										</div>
										<div className="space-y-2">
											<p className="text-xs uppercase tracking-wider text-muted-foreground">
												源码压缩包
											</p>
											<label className="inline-flex">
												<input
													type="file"
													accept={SUPPORTED_ARCHIVE_INPUT_ACCEPT}
													onChange={handleNewProjectFileSelect}
													className="hidden"
													disabled={creating}
												/>
												<span className="inline-flex h-9 cursor-pointer items-center rounded-sm border border-border px-3 text-sm hover:bg-muted">
													<Upload className="w-4 h-4 mr-2" />
													选择压缩包
												</span>
											</label>
											{newProjectFile ? (
												<p className="text-xs text-emerald-300">
													已选择: {newProjectFile.name}
												</p>
											) : null}
										</div>
									</div>
								)}

								<div className="border border-border rounded-lg p-4 space-y-3">
									<div className="flex items-center justify-between">
										<p className="text-sm font-semibold text-foreground">
											静态审计引擎
										</p>
										<p className="text-xs text-muted-foreground">
											Opengrep 与 CodeQL 互斥
										</p>
									</div>
									<div className="grid grid-cols-1 md:grid-cols-2 gap-2">
										{staticEngineItems.map((item) => (
											<div
												key={item.key}
												className="border border-border rounded p-3 flex items-center justify-between gap-3 hover:border-sky-500/30"
											>
												<label className="flex min-w-0 items-center gap-3 cursor-pointer">
													<Checkbox
														checked={item.checked}
														onCheckedChange={(checked) => item.setChecked(Boolean(checked))}
														disabled={creating}
														className="data-[state=checked]:bg-sky-500 data-[state=checked]:border-sky-500"
													/>
													<p className="text-sm text-foreground font-semibold">
														{item.title}
													</p>
												</label>
												<Button
													type="button"
													variant="ghost"
													size="icon"
													className="h-8 w-8 shrink-0 text-muted-foreground hover:text-foreground hover:bg-sky-500/10"
													onClick={() => setConfigEngine(item.key)}
													disabled={creating}
													aria-label={`配置 ${item.title} 引擎`}
												>
													<Settings2 className="h-4 w-4" />
												</Button>
											</div>
										))}
									</div>
								</div>
							</>
						) : (
							/* ── Intelligent tab content ── */
							<div className="space-y-3">
								<p className="text-xs uppercase tracking-wider text-muted-foreground">
									选择项目
								</p>
								<div className="border border-border rounded-lg p-2 space-y-2">
									{loadingProjects ? (
										<div className="py-10 flex items-center justify-center text-sm text-muted-foreground">
											<Loader2 className="w-4 h-4 animate-spin mr-2" />
											加载项目中...
										</div>
									) : filteredProjects.length > 0 ? (
										visibleProjects.map((project) => (
											<ProjectChoice
												key={project.id}
												project={project}
												selected={project.id === selectedProjectId}
												onSelect={() => setSelectedProjectId(project.id)}
												disabled={creating}
											/>
										))
									) : (
										<div className="py-10 text-center text-sm text-muted-foreground">
											未找到可用项目
										</div>
									)}
								</div>
								{filteredProjects.length > 0 ? (
									<div className="flex items-center justify-between gap-3 text-xs text-muted-foreground">
										<span>每页 3 个项目卡片</span>
										<div className="flex items-center gap-2">
											<Button
												type="button"
												variant="outline"
												className="cyber-btn-outline h-8 px-3"
												onClick={() => setProjectPage(Math.max(1, projectPage - 1))}
												disabled={creating || projectPage <= 1}
											>
												上一页
											</Button>
											<span>
												第 {projectPage} / {projectTotalPages} 页
											</span>
											<Button
												type="button"
												variant="outline"
												className="cyber-btn-outline h-8 px-3"
												onClick={() =>
													setProjectPage(Math.min(projectTotalPages, projectPage + 1))
												}
												disabled={creating || projectPage >= projectTotalPages}
											>
												下一页
											</Button>
										</div>
									</div>
								) : null}
								<div className="rounded-lg border border-violet-500/20 bg-violet-500/5 p-3">
									<p className="text-xs text-violet-300/80">
										智能扫描由 LLM 驱动，将对项目进行深度语义分析并生成审计报告。
									</p>
								</div>
							</div>
						)}
					</div>

					<div className="px-6 py-4 border-t border-border bg-muted flex justify-end gap-2">
						{showReturnButton && onReturn ? (
							<Button
								type="button"
								variant="outline"
								className="cyber-btn-outline"
								onClick={onReturn}
								disabled={creating}
							>
								返回
							</Button>
						) : null}
						<Button
							type="button"
							variant="outline"
							className="cyber-btn-outline"
							onClick={() => onOpenChange(false)}
							disabled={creating}
						>
							取消
						</Button>
						{activeTab === "static" ? (
							<>
								<Button
									type="button"
									className="cyber-btn-primary"
									onClick={() => handleCreate("primary")}
									disabled={!canCreate || creating}
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
								{createButtonVariant === "dual" ? (
									<Button
										type="button"
										className="cyber-btn-primary"
										onClick={() => handleCreate("secondary")}
										disabled={!canCreate || creating}
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
								) : null}
							</>
						) : (
							<Button
								type="button"
								className="cyber-btn-primary bg-violet-600 hover:bg-violet-500 border-violet-500"
								onClick={() => void handleIntelligentCreate()}
								disabled={!canIntelligentCreate || creating}
							>
								{creating ? (
									<>
										<Loader2 className="w-4 h-4 animate-spin mr-2" />
										创建中...
									</>
								) : (
									<>
										<Brain className="w-4 h-4 mr-2" />
										创建智能审计任务
									</>
								)}
							</Button>
						)}
					</div>
				</DialogContent>
			</Dialog>
			<StaticEngineConfigDialog
				engine={configEngine ?? "opengrep"}
				open={configEngine !== null}
				onOpenChange={(nextOpen) => {
					if (!nextOpen) setConfigEngine(null);
				}}
				scanMode="static"
				enabled={
					configEngine
						? (staticEngineItems.find((item) => item.key === configEngine)?.checked ?? false)
						: false
				}
				creating={creating}
				blockedReason={null}
				onNavigateToEngineConfig={onNavigateToEngineConfig}
			/>
		</>
	);
}

function ProjectChoice({
	project,
	selected,
	onSelect,
	disabled,
}: {
	project: Project;
	selected: boolean;
	onSelect: () => void;
	disabled: boolean;
}) {
	return (
		<button
			type="button"
			onClick={onSelect}
			className={`w-full text-left p-3 rounded border transition-colors ${
				selected
					? "border-sky-500/50 bg-sky-500/10"
					: "border-border hover:border-sky-500/30 bg-background"
			}`}
			disabled={disabled}
		>
			<div className="flex items-start justify-between gap-3">
				<div className="min-w-0">
					<p className="text-sm font-semibold text-foreground">{project.name}</p>
					{project.description ? (
						<p className="text-xs text-muted-foreground mt-1 line-clamp-1">
							{project.description}
						</p>
					) : null}
				</div>
				<Badge
					className={
						project.source_type === "zip"
							? "cyber-badge-warning"
							: "cyber-badge-info"
					}
				>
					{project.source_type === "zip" ? "ZIP" : "仓库"}
				</Badge>
			</div>
		</button>
	);
}
