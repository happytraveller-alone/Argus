import { useCallback, useEffect, useMemo, useState } from "react";
import {
	ArrowLeft,
	ChevronDown,
	ChevronRight,
	FileCode2,
	Folder,
	FolderOpen,
} from "lucide-react";
import { useLocation, useNavigate, useParams } from "react-router-dom";
import FindingCodeWindow from "@/pages/AgentAudit/components/FindingCodeWindow";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { api } from "@/shared/config/database";
import type { Project } from "@/shared/types";
import { cn } from "@/shared/utils/utils";
import {
	buildProjectCodeBrowserTree,
	PROJECT_CODE_BROWSER_EMPTY_MESSAGE,
	PROJECT_CODE_BROWSER_FAILED_MESSAGE,
	PROJECT_CODE_BROWSER_UNAVAILABLE_MESSAGE,
	resolveProjectCodeBrowserBackTarget,
	resolveProjectCodeBrowserFileFailure,
	resolveProjectCodeBrowserFileSuccess,
	toggleProjectCodeBrowserFolder,
	type ProjectCodeBrowserFileViewState,
	type ProjectCodeBrowserTreeNode,
} from "@/pages/project-code-browser/model";

interface ProjectCodeBrowserContentProps {
	project: Project | null;
	loading: boolean;
	error: string | null;
	filesCount: number;
	tree: ProjectCodeBrowserTreeNode[];
	expandedFolders: Set<string>;
	selectedFilePath: string | null;
	selectedFileState: ProjectCodeBrowserFileViewState;
	onBack: () => void;
	onToggleFolder: (folderPath: string) => void;
	onSelectFile: (filePath: string) => void;
}

interface ProjectCodeBrowserTreeProps {
	nodes: ProjectCodeBrowserTreeNode[];
	expandedFolders: Set<string>;
	selectedFilePath: string | null;
	onToggleFolder: (folderPath: string) => void;
	onSelectFile: (filePath: string) => void;
	depth?: number;
}

function renderFileSize(size?: number) {
	if (typeof size !== "number" || !Number.isFinite(size)) return null;
	return `${size.toLocaleString()} B`;
}

function ProjectCodeBrowserTree({
	nodes,
	expandedFolders,
	selectedFilePath,
	onToggleFolder,
	onSelectFile,
	depth = 0,
}: ProjectCodeBrowserTreeProps) {
	return (
		<div className={cn("space-y-1", depth > 0 && "mt-1")}>
			{nodes.map((node) => {
				if (node.kind === "directory") {
					const isExpanded = expandedFolders.has(node.path);
					return (
						<div key={node.path}>
							<button
								type="button"
								onClick={() => onToggleFolder(node.path)}
								className="flex w-full items-center gap-2 rounded-md border border-transparent px-3 py-2 text-left text-sm text-slate-100 transition-colors hover:border-sky-500/20 hover:bg-sky-500/10 cursor-pointer"
								style={{ paddingLeft: `${depth * 16 + 12}px` }}
							>
								{isExpanded ? (
									<ChevronDown className="h-4 w-4 text-sky-300" />
								) : (
									<ChevronRight className="h-4 w-4 text-slate-400" />
								)}
								{isExpanded ? (
									<FolderOpen className="h-4 w-4 text-sky-300" />
								) : (
									<Folder className="h-4 w-4 text-slate-300" />
								)}
								<span className="truncate font-mono">{node.name}</span>
							</button>
							{isExpanded && node.children?.length ? (
								<ProjectCodeBrowserTree
									nodes={node.children}
									expandedFolders={expandedFolders}
									selectedFilePath={selectedFilePath}
									onToggleFolder={onToggleFolder}
									onSelectFile={onSelectFile}
									depth={depth + 1}
								/>
							) : null}
						</div>
					);
				}

				const isSelected = selectedFilePath === node.path;
				return (
					<button
						key={node.path}
						type="button"
						onClick={() => onSelectFile(node.path)}
						className={cn(
							"flex w-full items-center justify-between gap-3 rounded-md border px-3 py-2 text-left transition-colors cursor-pointer",
							isSelected
								? "border-sky-400/40 bg-sky-500/12 text-white"
								: "border-transparent text-slate-200 hover:border-sky-500/20 hover:bg-sky-500/8",
						)}
						style={{ paddingLeft: `${depth * 16 + 32}px` }}
					>
						<span className="flex min-w-0 items-center gap-2">
							<FileCode2 className="h-4 w-4 shrink-0 text-sky-300" />
							<span className="truncate font-mono text-sm">{node.name}</span>
						</span>
						{node.size ? (
							<span className="shrink-0 font-mono text-[10px] uppercase tracking-[0.18em] text-slate-400">
								{renderFileSize(node.size)}
							</span>
						) : null}
					</button>
				);
			})}
		</div>
	);
}

function ProjectCodeBrowserPreview({
	selectedFilePath,
	selectedFileState,
}: Pick<
	ProjectCodeBrowserContentProps,
	"selectedFilePath" | "selectedFileState"
>) {
	if (selectedFileState.status === "loading") {
		return (
			<div className="flex min-h-[360px] items-center justify-center rounded-xl border border-dashed border-sky-500/20 bg-black/20 px-6 py-10 text-center font-mono text-sm text-slate-300">
				正在加载文件内容...
			</div>
		);
	}

	if (selectedFileState.status === "failed") {
		return (
			<div className="flex min-h-[360px] items-center justify-center rounded-xl border border-dashed border-rose-500/20 bg-rose-500/5 px-6 py-10 text-center font-mono text-sm text-rose-200">
				{selectedFileState.message}
			</div>
		);
	}

	if (selectedFileState.status === "unavailable") {
		return (
			<div className="flex min-h-[360px] items-center justify-center rounded-xl border border-dashed border-amber-500/20 bg-amber-500/5 px-6 py-10 text-center font-mono text-sm text-amber-100">
				{selectedFileState.message}
			</div>
		);
	}

	if (selectedFileState.status === "ready") {
		const lineEnd = selectedFileState.content.replace(/\r\n/g, "\n").split("\n")
			.length;
		return (
			<FindingCodeWindow
				title="代码浏览"
				filePath={selectedFileState.filePath}
				code={selectedFileState.content}
				lineStart={1}
				lineEnd={lineEnd}
				chrome="editor"
				variant="detail"
				meta={[
					`${selectedFileState.size.toLocaleString()} B`,
					`编码 ${selectedFileState.encoding}`,
				]}
			/>
		);
	}

	return (
		<div className="flex min-h-[360px] items-center justify-center rounded-xl border border-dashed border-slate-700/70 bg-black/20 px-6 py-10 text-center font-mono text-sm text-slate-400">
			{selectedFilePath ? PROJECT_CODE_BROWSER_FAILED_MESSAGE : PROJECT_CODE_BROWSER_EMPTY_MESSAGE}
		</div>
	);
}

export function ProjectCodeBrowserContent({
	project,
	loading,
	error,
	filesCount,
	tree,
	expandedFolders,
	selectedFilePath,
	selectedFileState,
	onBack,
	onToggleFolder,
	onSelectFile,
}: ProjectCodeBrowserContentProps) {
	const currentFileLabel = selectedFilePath || "未选择文件";
	const filesCountLabel = `${filesCount} 个文件`;
	const isZipProject = project?.source_type === "zip";

	return (
		<div className="p-6 bg-background min-h-screen font-mono relative flex flex-col gap-6">
			<div className="absolute inset-0 cyber-grid-subtle pointer-events-none" />

			<section className="cyber-card relative z-10 overflow-hidden p-5">
				<div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
					<div className="flex min-w-0 items-start gap-3">
						<Button
							type="button"
							size="sm"
							variant="outline"
							className="cyber-btn-ghost h-9 px-3"
							onClick={onBack}
						>
							<ArrowLeft className="h-4 w-4" />
							返回
						</Button>
						<div className="min-w-0 space-y-2">
							<div className="text-xs uppercase tracking-[0.28em] text-sky-300">
								代码浏览
							</div>
							<h1 className="truncate text-2xl font-bold text-white">
								{project?.name || "项目代码浏览"}
							</h1>
							<p className="truncate text-xs text-slate-400">
								当前文件: {currentFileLabel}
							</p>
						</div>
					</div>
					<div className="flex flex-wrap items-center gap-2">
						<Badge className="bg-sky-500/12 text-sky-100 border-sky-500/25">
							{project?.source_type === "zip" ? "ZIP 项目" : "仓库项目"}
						</Badge>
						<Badge className="bg-white/5 text-slate-200 border-white/10">
							{filesCountLabel}
						</Badge>
					</div>
				</div>
			</section>

			{loading ? (
				<section className="cyber-card relative z-10 flex min-h-[240px] items-center justify-center p-6 text-sm text-slate-300">
					正在加载项目代码浏览数据...
				</section>
			) : error ? (
				<section className="cyber-card relative z-10 flex min-h-[240px] items-center justify-center p-6 text-sm text-rose-300">
					{error}
				</section>
			) : !project ? (
				<section className="cyber-card relative z-10 flex min-h-[240px] items-center justify-center p-6 text-sm text-slate-300">
					项目不存在或已被删除
				</section>
			) : !isZipProject ? (
				<section className="cyber-card relative z-10 flex min-h-[240px] items-center justify-center p-6 text-sm text-slate-300">
					仅 ZIP 类型项目支持代码浏览
				</section>
			) : (
				<section className="relative z-10 grid min-h-[65vh] grid-cols-1 gap-6 xl:grid-cols-[320px_minmax(0,1fr)]">
					<div className="cyber-card min-h-[320px] p-4">
						<div className="mb-4 flex items-center justify-between gap-3">
							<div>
								<div className="text-xs uppercase tracking-[0.24em] text-sky-300">
									文件树
								</div>
								<p className="mt-1 text-xs text-slate-400">
									默认全部折叠，点击目录展开
								</p>
							</div>
							<Badge className="bg-white/5 text-slate-200 border-white/10">
								{filesCountLabel}
							</Badge>
						</div>
						<div className="max-h-[70vh] overflow-y-auto pr-1 custom-scrollbar-dark">
							{tree.length > 0 ? (
								<ProjectCodeBrowserTree
									nodes={tree}
									expandedFolders={expandedFolders}
									selectedFilePath={selectedFilePath}
									onToggleFolder={onToggleFolder}
									onSelectFile={onSelectFile}
								/>
							) : (
								<div className="rounded-xl border border-dashed border-slate-700/70 bg-black/20 px-4 py-8 text-center text-sm text-slate-400">
									当前项目没有可浏览的文本文件
								</div>
							)}
						</div>
					</div>

					<div className="cyber-card min-h-[320px] p-4">
						<div className="mb-4">
							<div className="text-xs uppercase tracking-[0.24em] text-sky-300">
								预览窗口
							</div>
							<p className="mt-1 truncate text-xs text-slate-400">
								{selectedFilePath || PROJECT_CODE_BROWSER_EMPTY_MESSAGE}
							</p>
						</div>
						<ProjectCodeBrowserPreview
							selectedFilePath={selectedFilePath}
							selectedFileState={selectedFileState}
						/>
					</div>
				</section>
			)}
		</div>
	);
}

export default function ProjectCodeBrowser() {
	const navigate = useNavigate();
	const location = useLocation();
	const { id } = useParams<{ id: string }>();
	const [project, setProject] = useState<Project | null>(null);
	const [loading, setLoading] = useState(true);
	const [error, setError] = useState<string | null>(null);
	const [tree, setTree] = useState<ProjectCodeBrowserTreeNode[]>([]);
	const [filesCount, setFilesCount] = useState(0);
	const [expandedFolders, setExpandedFolders] = useState<Set<string>>(
		() => new Set(),
	);
	const [selectedFilePath, setSelectedFilePath] = useState<string | null>(null);
	const [fileStates, setFileStates] = useState<
		Record<string, ProjectCodeBrowserFileViewState>
	>({});

	const from =
		typeof (location.state as { from?: unknown } | null)?.from === "string"
			? ((location.state as { from?: string }).from ?? "")
			: "";

	useEffect(() => {
		let cancelled = false;

		async function load() {
			setLoading(true);
			setError(null);
			setProject(null);
			setTree([]);
			setFilesCount(0);
			setExpandedFolders(new Set());
			setSelectedFilePath(null);
			setFileStates({});

			if (!id) {
				setError("项目不存在或已被删除");
				setLoading(false);
				return;
			}

			try {
				const currentProject = await api.getProjectById(id);
				if (cancelled) return;

				if (!currentProject) {
					setError("项目不存在或已被删除");
					setLoading(false);
					return;
				}

				setProject(currentProject);

				if (currentProject.source_type !== "zip") {
					setLoading(false);
					return;
				}

				const files = await api.getProjectFiles(id);
				if (cancelled) return;

				setFilesCount(files.length);
				setTree(buildProjectCodeBrowserTree(files));
			} catch (_error) {
				if (cancelled) return;
				setError("加载项目代码浏览数据失败");
			} finally {
				if (!cancelled) {
					setLoading(false);
				}
			}
		}

		void load();

		return () => {
			cancelled = true;
		};
	}, [id]);

	const selectedFileState = useMemo<ProjectCodeBrowserFileViewState>(() => {
		if (!selectedFilePath) {
			return { status: "idle" };
		}
		return fileStates[selectedFilePath] ?? { status: "idle" };
	}, [fileStates, selectedFilePath]);

	const handleBack = useCallback(() => {
		const target = resolveProjectCodeBrowserBackTarget({
			from,
			hasHistory: typeof window !== "undefined" && window.history.length > 1,
		});
		if (typeof target === "number") {
			navigate(target);
			return;
		}
		navigate(target);
	}, [from, navigate]);

	const handleToggleFolder = useCallback((folderPath: string) => {
		setExpandedFolders((current) =>
			toggleProjectCodeBrowserFolder(current, folderPath),
		);
	}, []);

	const handleSelectFile = useCallback(
		async (filePath: string) => {
			if (!id || project?.source_type !== "zip") return;
			setSelectedFilePath(filePath);

			const cachedState = fileStates[filePath];
			if (cachedState && cachedState.status !== "idle") {
				return;
			}

			setFileStates((current) => ({
				...current,
				[filePath]: { status: "loading" },
			}));

			try {
				const response = await api.getProjectFileContent(id, filePath);
				setFileStates((current) => ({
					...current,
					[filePath]: resolveProjectCodeBrowserFileSuccess(response),
				}));
			} catch (error) {
				setFileStates((current) => ({
					...current,
					[filePath]: resolveProjectCodeBrowserFileFailure(error),
				}));
			}
		},
		[fileStates, id, project?.source_type],
	);

	return (
		<ProjectCodeBrowserContent
			project={project}
			loading={loading}
			error={error}
			filesCount={filesCount}
			tree={tree}
			expandedFolders={expandedFolders}
			selectedFilePath={selectedFilePath}
			selectedFileState={selectedFileState}
			onBack={handleBack}
			onToggleFolder={handleToggleFolder}
			onSelectFile={handleSelectFile}
		/>
	);
}
