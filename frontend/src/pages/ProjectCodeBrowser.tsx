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
import FindingCodeWindow, {
	type FindingCodeWindowAppearance,
} from "@/pages/AgentAudit/components/FindingCodeWindow";
import { Button } from "@/components/ui/button";
import { api } from "@/shared/api/database";
import type { Project } from "@/shared/types";
import { cn } from "@/shared/utils/utils";
import {
	buildProjectCodeBrowserTree,
	PROJECT_CODE_BROWSER_EMPTY_MESSAGE,
	PROJECT_CODE_BROWSER_FAILED_MESSAGE,
	resolveProjectCodeBrowserBackTarget,
	resolveProjectCodeBrowserFileFailure,
	resolveProjectCodeBrowserFileSuccess,
	toggleProjectCodeBrowserFolder,
	type ProjectCodeBrowserFileViewState,
	type ProjectCodeBrowserTreeNode,
} from "@/pages/project-code-browser/model";

type ProjectCodeBrowserPreviewDecoration = {
	focusLine?: number | null;
	highlightStartLine?: number | null;
	highlightEndLine?: number | null;
};

interface ProjectCodeBrowserWorkspaceProps {
	tree: ProjectCodeBrowserTreeNode[];
	expandedFolders: Set<string>;
	selectedFilePath: string | null;
	selectedFileState: ProjectCodeBrowserFileViewState;
	onToggleFolder: (folderPath: string) => void;
	onSelectFile: (filePath: string) => void;
	appearance?: FindingCodeWindowAppearance;
	previewDecorations?: Record<string, ProjectCodeBrowserPreviewDecoration | undefined>;
	className?: string;
}

interface ProjectCodeBrowserContentProps extends ProjectCodeBrowserWorkspaceProps {
	project: Project | null;
	loading: boolean;
	error: string | null;
	filesCount: number;
	onBack: () => void;
}

interface ProjectCodeBrowserTreeProps {
	nodes: ProjectCodeBrowserTreeNode[];
	expandedFolders: Set<string>;
	selectedFilePath: string | null;
	onToggleFolder: (folderPath: string) => void;
	onSelectFile: (filePath: string) => void;
	appearance: FindingCodeWindowAppearance;
	depth?: number;
}

function renderFileSize(size?: number) {
	if (typeof size !== "number" || !Number.isFinite(size)) return null;
	return `${size.toLocaleString()} B`;
}

function getPaneShellClasses(appearance: FindingCodeWindowAppearance) {
	if (appearance === "terminal-flat") {
		return "rounded-md border border-white/8 bg-black";
	}
	if (appearance === "dense-ide") {
		return "rounded-lg border border-white/10 bg-[#030303]";
	}
	return "rounded-2xl border border-white/10 bg-[#020202]";
}

function getEmptyStateClasses() {
	return "flex h-full min-h-0 items-center justify-center rounded-lg border border-dashed border-white/10 bg-white/[0.02] px-6 py-10 text-center font-mono text-sm text-white/48";
}

function ProjectCodeBrowserTree({
	nodes,
	expandedFolders,
	selectedFilePath,
	onToggleFolder,
	onSelectFile,
	appearance,
	depth = 0,
}: ProjectCodeBrowserTreeProps) {
	return (
		<div className={cn("space-y-1.5", depth > 0 && "mt-1.5")}>
			{nodes.map((node) => {
				if (node.kind === "directory") {
					const isExpanded = expandedFolders.has(node.path);
					return (
						<div key={node.path}>
							<button
								type="button"
								onClick={() => onToggleFolder(node.path)}
								className={cn(
									"flex w-full items-center gap-2 rounded-md border border-transparent px-3 py-2 text-left text-sm transition-colors cursor-pointer",
									"text-white/82 hover:border-white/10 hover:bg-white/[0.04]",
									appearance === "terminal-flat" && "rounded-sm",
								)}
								style={{ paddingLeft: `${depth * 16 + 12}px` }}
							>
								{isExpanded ? (
									<ChevronDown className="h-4 w-4 text-white/56" />
								) : (
									<ChevronRight className="h-4 w-4 text-white/38" />
								)}
								{isExpanded ? (
									<FolderOpen className="h-4 w-4 text-white/70" />
								) : (
									<Folder className="h-4 w-4 text-white/56" />
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
									appearance={appearance}
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
							"flex w-full items-center justify-between gap-3 border px-3 py-2 text-left transition-colors cursor-pointer",
							appearance === "terminal-flat" ? "rounded-sm" : "rounded-md",
							isSelected
								? "border-white/14 bg-white/[0.08] text-white"
								: "border-transparent text-white/74 hover:border-white/10 hover:bg-white/[0.04]",
						)}
						style={{ paddingLeft: `${depth * 16 + 32}px` }}
					>
						<span className="flex min-w-0 items-center gap-2">
							<FileCode2 className="h-4 w-4 shrink-0 text-white/62" />
							<span className="truncate font-mono text-sm">{node.name}</span>
						</span>
						{node.size ? (
							<span className="shrink-0 font-mono text-[10px] uppercase tracking-[0.18em] text-white/34">
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
	appearance,
	previewDecorations,
}: Pick<
	ProjectCodeBrowserWorkspaceProps,
	"selectedFilePath" | "selectedFileState" | "appearance" | "previewDecorations"
>) {
	const filePath =
		selectedFileState.status === "ready" ? selectedFileState.filePath : selectedFilePath || "";
	const previewDecoration = filePath ? previewDecorations?.[filePath] : undefined;

	if (selectedFileState.status === "loading") {
		return (
			<div className={getEmptyStateClasses()}>
				正在加载文件内容...
			</div>
		);
	}

	if (selectedFileState.status === "failed") {
		return <div className={getEmptyStateClasses()}>{selectedFileState.message}</div>;
	}

	if (selectedFileState.status === "unavailable") {
		return <div className={getEmptyStateClasses()}>{selectedFileState.message}</div>;
	}

	if (selectedFileState.status === "ready") {
		const lineEnd = selectedFileState.content.replace(/\r\n/g, "\n").split("\n")
			.length;
		return (
			<FindingCodeWindow
				filePath={selectedFileState.filePath}
				code={selectedFileState.content}
				lineStart={1}
				lineEnd={lineEnd}
				highlightStartLine={previewDecoration?.highlightStartLine ?? undefined}
				highlightEndLine={previewDecoration?.highlightEndLine ?? undefined}
				focusLine={previewDecoration?.focusLine ?? undefined}
				variant="detail"
				appearance={appearance}
				displayPreset="project-browser"
			/>
		);
	}

	return (
		<div className={getEmptyStateClasses()}>
			{selectedFilePath ? PROJECT_CODE_BROWSER_FAILED_MESSAGE : PROJECT_CODE_BROWSER_EMPTY_MESSAGE}
		</div>
	);
}

export function ProjectCodeBrowserWorkspace({
	tree,
	expandedFolders,
	selectedFilePath,
	selectedFileState,
	onToggleFolder,
	onSelectFile,
	appearance = "native-explorer",
	previewDecorations,
	className,
}: ProjectCodeBrowserWorkspaceProps) {
	return (
			<section
				className={cn(
					"grid min-h-0 grid-cols-1 gap-4 overflow-hidden xl:grid-cols-[minmax(280px,360px)_minmax(0,1fr)]",
					className,
				)}
			>
			<div
				className={cn(
					getPaneShellClasses(appearance),
					"min-h-[360px] overflow-hidden xl:min-h-0",
				)}
			>
				<div className="flex h-full min-h-0 flex-col">
					<div className="min-h-0 flex-1 overflow-y-auto px-3 py-3 custom-scrollbar-dark">
						{tree.length > 0 ? (
							<ProjectCodeBrowserTree
								nodes={tree}
								expandedFolders={expandedFolders}
								selectedFilePath={selectedFilePath}
								onToggleFolder={onToggleFolder}
								onSelectFile={onSelectFile}
								appearance={appearance}
							/>
						) : (
							<div className="px-3 py-8 text-center text-sm text-white/42">
								当前项目没有可浏览的文本文件
							</div>
						)}
					</div>
				</div>
			</div>

			<div
				className={cn(
					getPaneShellClasses(appearance),
					"min-h-[360px] overflow-hidden xl:min-h-0",
				)}
			>
				<div className="flex h-full min-h-0 flex-col">
					<div className="flex min-h-0 flex-1 flex-col p-3">
						<ProjectCodeBrowserPreview
							selectedFilePath={selectedFilePath}
							selectedFileState={selectedFileState}
							appearance={appearance}
							previewDecorations={previewDecorations}
						/>
					</div>
				</div>
			</div>
		</section>
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
	appearance = "native-explorer",
	previewDecorations,
}: ProjectCodeBrowserContentProps) {
	const filesCountLabel = `${filesCount} 个文件`;
	const isZipProject = project?.source_type === "zip";

	return (
		<div className="relative flex h-[100dvh] max-h-[100dvh] min-h-0 flex-col gap-4 overflow-hidden bg-background p-6 font-mono">
			<section className="rounded-2xl border border-white/10 bg-black/80 px-5 py-4">
				<div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
					<div className="flex min-w-0 items-start gap-3">
						<Button
							type="button"
							size="sm"
							variant="outline"
							className="h-9 border-white/10 bg-black px-3 text-white/80 hover:bg-white/[0.04] hover:text-white"
							onClick={onBack}
						>
							<ArrowLeft className="h-4 w-4" />
							返回
						</Button>
						<div className="min-w-0 space-y-1">
							<h1 className="truncate text-2xl font-bold text-white">
								{project?.name || "项目代码浏览"}
							</h1>
						</div>
					</div>
					<div className="flex flex-wrap items-center gap-2 text-[11px] uppercase tracking-[0.18em] text-white/40">
						<span className="rounded-md border border-white/10 bg-white/[0.03] px-2.5 py-1">
							{project?.source_type === "zip" ? "ZIP 项目" : "仓库项目"}
						</span>
						<span className="rounded-md border border-white/10 bg-white/[0.03] px-2.5 py-1">
							{filesCountLabel}
						</span>
					</div>
				</div>
			</section>

			{loading ? (
				<section className="flex flex-1 items-center justify-center rounded-2xl border border-white/10 bg-black/80 p-6 text-sm text-white/56">
					正在加载项目代码浏览数据...
				</section>
			) : error ? (
				<section className="flex flex-1 items-center justify-center rounded-2xl border border-white/10 bg-black/80 p-6 text-sm text-white/56">
					{error}
				</section>
			) : !project ? (
				<section className="flex flex-1 items-center justify-center rounded-2xl border border-white/10 bg-black/80 p-6 text-sm text-white/56">
					项目不存在或已被删除
				</section>
			) : !isZipProject ? (
				<section className="flex flex-1 items-center justify-center rounded-2xl border border-white/10 bg-black/80 p-6 text-sm text-white/56">
					仅 ZIP 类型项目支持代码浏览
				</section>
			) : (
				<ProjectCodeBrowserWorkspace
					tree={tree}
					expandedFolders={expandedFolders}
					selectedFilePath={selectedFilePath}
					selectedFileState={selectedFileState}
					onToggleFolder={onToggleFolder}
					onSelectFile={onSelectFile}
					appearance={appearance}
					previewDecorations={previewDecorations}
					className="flex-1 min-h-0 overflow-hidden"
				/>
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
