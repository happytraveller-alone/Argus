import {
	useCallback,
	useEffect,
	useMemo,
	useRef,
	useState,
	type ReactNode,
	type RefObject,
} from "react";
import {
	ArrowLeft,
	ChevronDown,
	ChevronRight,
	FileCode2,
	Folder,
	FolderOpen,
	Search,
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
	buildProjectCodeBrowserContentSearchResults,
	buildProjectCodeBrowserFileSearchResults,
	buildProjectCodeBrowserTree,
	filterProjectCodeBrowserFilesByPath,
	mergeProjectCodeBrowserSearchResults,
	normalizeProjectCodeBrowserSearchQuery,
	PROJECT_CODE_BROWSER_EMPTY_MESSAGE,
	PROJECT_CODE_BROWSER_FAILED_MESSAGE,
	PROJECT_CODE_BROWSER_SEARCH_EMPTY_MESSAGE,
	PROJECT_CODE_BROWSER_SEARCH_LOADING_MESSAGE,
	PROJECT_CODE_BROWSER_SEARCH_NO_RESULTS_MESSAGE,
	resolveProjectCodeBrowserBackTarget,
	resolveProjectCodeBrowserFileFailure,
	resolveProjectCodeBrowserFileSuccess,
	resolveProjectCodeBrowserPreviewDecorationForSearchResult,
	shouldProjectCodeBrowserSearchContent,
	toggleProjectCodeBrowserFolder,
	type ProjectCodeBrowserFileEntry,
	type ProjectCodeBrowserFileViewState,
	type ProjectCodeBrowserMode,
	type ProjectCodeBrowserPreviewDecoration,
	type ProjectCodeBrowserSearchHighlightPart,
	type ProjectCodeBrowserSearchResult,
	type ProjectCodeBrowserSearchStatus,
	type ProjectCodeBrowserTreeNode,
} from "@/pages/project-code-browser/model";

const SEARCH_CONTENT_CONCURRENCY = 4;
const MAX_CONTENT_MATCHES_PER_FILE = 3;
const MAX_TOTAL_SEARCH_RESULTS = 50;

interface ProjectCodeBrowserWorkspaceProps {
	tree: ProjectCodeBrowserTreeNode[];
	expandedFolders: Set<string>;
	selectedFilePath: string | null;
	selectedFileState: ProjectCodeBrowserFileViewState;
	browserMode?: ProjectCodeBrowserMode;
	searchQuery?: string;
	includeFileQuery?: string;
	excludeFileQuery?: string;
	searchStatus?: ProjectCodeBrowserSearchStatus;
	searchResults?: ProjectCodeBrowserSearchResult[];
	onToggleFolder: (folderPath: string) => void;
	onSelectFile: (filePath: string) => void;
	onSelectMode?: (mode: ProjectCodeBrowserMode) => void;
	onSearchQueryChange?: (query: string) => void;
	onIncludeFileQueryChange?: (query: string) => void;
	onExcludeFileQueryChange?: (query: string) => void;
	onSelectSearchResult?: (result: ProjectCodeBrowserSearchResult) => void;
	appearance?: FindingCodeWindowAppearance;
	previewDecorations?: Record<string, ProjectCodeBrowserPreviewDecoration | undefined>;
	searchInputRef?: RefObject<HTMLInputElement | null>;
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

interface ProjectCodeBrowserModeRailProps {
	browserMode: ProjectCodeBrowserMode;
	onSelectMode: (mode: ProjectCodeBrowserMode) => void;
	appearance: FindingCodeWindowAppearance;
}

interface ProjectCodeBrowserSearchPanelProps {
	searchQuery: string;
	includeFileQuery: string;
	excludeFileQuery: string;
	searchStatus: ProjectCodeBrowserSearchStatus;
	searchResults: ProjectCodeBrowserSearchResult[];
	selectedFilePath: string | null;
	onSearchQueryChange: (query: string) => void;
	onIncludeFileQueryChange: (query: string) => void;
	onExcludeFileQueryChange: (query: string) => void;
	onSelectSearchResult: (result: ProjectCodeBrowserSearchResult) => void;
	inputRef?: RefObject<HTMLInputElement | null>;
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
	return "flex h-full min-h-0 items-center justify-center rounded-lg border border-dashed border-white/10 bg-white/[0.02] px-6 py-10 text-center font-mono text-base text-white/48";
}

function renderHighlightedParts(
	parts: ProjectCodeBrowserSearchHighlightPart[],
	fallbackText: string,
): ReactNode {
	if (!parts.length) return fallbackText;
	return parts.map((part, index) =>
		part.matched ? (
			<mark
				key={`${part.text}-${index}`}
				className="rounded bg-[#c7ff6a]/20 px-1 text-[#efffc3]"
			>
				{part.text}
			</mark>
		) : (
			<span key={`${part.text}-${index}`}>{part.text}</span>
		),
	);
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

function ProjectCodeBrowserModeRail({
	browserMode,
	onSelectMode,
	appearance,
}: ProjectCodeBrowserModeRailProps) {
	const items = [
		{
			mode: "files" as const,
			label: "文件",
			ariaLabel: "切换到文件浏览",
			icon: FileCode2,
		},
		{
			mode: "search" as const,
			label: "搜索",
			ariaLabel: "切换到搜索",
			icon: Search,
		},
	];

	return (
		<div
			className={cn(
				getPaneShellClasses(appearance),
				"min-h-[52px] overflow-hidden xl:min-h-0",
			)}
		>
			<div className="flex h-full items-center justify-center gap-2 p-2 xl:flex-col xl:justify-start xl:gap-3 xl:p-3">
				{items.map((item) => {
					const Icon = item.icon;
					const isActive = browserMode === item.mode;
					return (
						<button
							key={item.mode}
							type="button"
							aria-label={item.ariaLabel}
							aria-pressed={isActive}
							title={item.label}
							onClick={() => onSelectMode(item.mode)}
							className={cn(
								"group flex h-11 w-11 items-center justify-center rounded-xl border transition-all duration-200 cursor-pointer",
								isActive
									? "border-[#c7ff6a]/40 bg-[#c7ff6a]/10 text-[#efffc3] shadow-[0_0_30px_rgba(199,255,106,0.08)]"
									: "border-white/8 bg-white/[0.02] text-white/55 hover:border-white/14 hover:bg-white/[0.05] hover:text-white/84",
							)}
						>
							<Icon className="h-4.5 w-4.5" />
						</button>
					);
				})}
			</div>
		</div>
	);
}

function ProjectCodeBrowserSearchPanel({
	searchQuery,
	includeFileQuery,
	excludeFileQuery,
	searchStatus,
	searchResults,
	selectedFilePath,
	onSearchQueryChange,
	onIncludeFileQueryChange,
	onExcludeFileQueryChange,
	onSelectSearchResult,
	inputRef,
}: ProjectCodeBrowserSearchPanelProps) {
	const normalizedQuery = normalizeProjectCodeBrowserSearchQuery(searchQuery);

	let body: ReactNode = (
		<div className={getEmptyStateClasses()}>{PROJECT_CODE_BROWSER_SEARCH_EMPTY_MESSAGE}</div>
	);

	if (normalizedQuery) {
		if (searchResults.length > 0) {
			body = (
				<div className="space-y-2">
					{searchResults.map((result) => {
						const isSelected = selectedFilePath === result.filePath;
						return (
							<button
								key={result.id}
								type="button"
								onClick={() => onSelectSearchResult(result)}
								className={cn(
									"w-full rounded-xl border px-3 py-3 text-left transition-all cursor-pointer",
									isSelected
										? "border-[#c7ff6a]/28 bg-[#c7ff6a]/[0.07]"
										: "border-white/8 bg-white/[0.02] hover:border-white/14 hover:bg-white/[0.05]",
								)}
							>
								<div className="flex items-start justify-between gap-3">
									<div className="min-w-0 space-y-1.5">
										<div className="flex flex-wrap items-center gap-2 text-[10px] uppercase tracking-[0.22em] text-white/34">
											<span className="rounded-full border border-white/10 px-2 py-0.5 text-[9px] tracking-[0.18em] text-white/45">
												{result.kind === "file" ? "文件" : "内容"}
											</span>
											{result.lineNumber ? <span>第 {result.lineNumber} 行</span> : null}
										</div>
										<div className="truncate text-sm font-semibold text-white/88">
											{renderHighlightedParts(
												result.fileNameParts,
												result.fileName,
											)}
										</div>
										<div className="truncate text-xs text-white/46">
											{renderHighlightedParts(result.pathParts, result.filePath)}
										</div>
										{result.kind === "content" ? (
											<p className="line-clamp-2 text-xs leading-6 text-white/68">
												{renderHighlightedParts(
													result.excerptParts,
													result.excerpt,
												)}
											</p>
										) : null}
									</div>
								</div>
							</button>
						);
					})}
				</div>
			);
		} else if (searchStatus.state === "scanning") {
			body = (
				<div className={getEmptyStateClasses()}>
					{PROJECT_CODE_BROWSER_SEARCH_LOADING_MESSAGE}
				</div>
			);
		} else {
			body = (
				<div className={getEmptyStateClasses()}>
					{PROJECT_CODE_BROWSER_SEARCH_NO_RESULTS_MESSAGE}
				</div>
			);
		}
	}

	return (
		<div className="flex h-full min-h-0 flex-col">
			<div className="border-b border-white/8 px-4 py-4">
				<div className="mt-3 grid grid-cols-1 gap-2">
					<label className="space-y-1">
						<span className="text-[13px] uppercase tracking-[0.18em] text-white/34">
							内容搜索
						</span>
						<input
							ref={inputRef}
							type="search"
							value={searchQuery}
							onChange={(event) => onSearchQueryChange(event.target.value)}
							placeholder="输入文件名或代码片段"
							className="w-full rounded-lg border border-white/10 bg-white/[0.02] px-3 py-2 text-xs text-white outline-none transition-colors placeholder:text-white/28 focus:border-[#c7ff6a]/28 focus:bg-black/50"
						/>
					</label>
					<label className="space-y-1">
						<span className="text-[13px] uppercase tracking-[0.18em] text-white/34">
							包含文件
						</span>
						<input
							type="text"
							value={includeFileQuery}
							onChange={(event) => onIncludeFileQueryChange(event.target.value)}
							placeholder="例如 src/, api"
							className="w-full rounded-lg border border-white/10 bg-white/[0.02] px-3 py-2 text-xs text-white outline-none transition-colors placeholder:text-white/28 focus:border-[#c7ff6a]/28 focus:bg-black/50"
						/>
					</label>
					<label className="space-y-1">
						<span className="text-[13px] uppercase tracking-[0.18em] text-white/34">
							排除文件
						</span>
						<input
							type="text"
							value={excludeFileQuery}
							onChange={(event) => onExcludeFileQueryChange(event.target.value)}
							placeholder="例如 dist, mock"
							className="w-full rounded-lg border border-white/10 bg-white/[0.02] px-3 py-2 text-xs text-white outline-none transition-colors placeholder:text-white/28 focus:border-[#c7ff6a]/28 focus:bg-black/50"
						/>
					</label>
				</div>
				
			</div>

			<div className="min-h-0 flex-1 overflow-y-auto px-3 py-3 custom-scrollbar-dark">
				{body}
			</div>
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
		return <div className={getEmptyStateClasses()}>正在加载文件内容...</div>;
	}

	if (selectedFileState.status === "failed") {
		return <div className={getEmptyStateClasses()}>{selectedFileState.message}</div>;
	}

	if (selectedFileState.status === "unavailable") {
		return <div className={getEmptyStateClasses()}>{selectedFileState.message}</div>;
	}

	if (selectedFileState.status === "ready") {
		const lineEnd = selectedFileState.content.replace(/\r\n/g, "\n").split("\n").length;
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

function ProjectCodeBrowserSidePanel({
	tree,
	expandedFolders,
	selectedFilePath,
	browserMode,
	searchQuery,
	includeFileQuery,
	excludeFileQuery,
	searchStatus,
	searchResults,
	onToggleFolder,
	onSelectFile,
	onSearchQueryChange,
	onIncludeFileQueryChange,
	onExcludeFileQueryChange,
	onSelectSearchResult,
	appearance,
	searchInputRef,
}: Pick<
	ProjectCodeBrowserWorkspaceProps,
	| "tree"
	| "expandedFolders"
	| "selectedFilePath"
	| "browserMode"
	| "searchQuery"
	| "includeFileQuery"
	| "excludeFileQuery"
	| "searchStatus"
	| "searchResults"
	| "onToggleFolder"
	| "onSelectFile"
	| "onSearchQueryChange"
	| "onIncludeFileQueryChange"
	| "onExcludeFileQueryChange"
	| "onSelectSearchResult"
	| "appearance"
	| "searchInputRef"
>) {
	if (
		browserMode === "search" &&
		searchStatus &&
		searchResults &&
		onSearchQueryChange &&
		onSelectSearchResult
	) {
		return (
			<ProjectCodeBrowserSearchPanel
				searchQuery={searchQuery ?? ""}
				includeFileQuery={includeFileQuery ?? ""}
				excludeFileQuery={excludeFileQuery ?? ""}
				searchStatus={searchStatus}
				searchResults={searchResults}
				selectedFilePath={selectedFilePath}
				onSearchQueryChange={onSearchQueryChange}
				onIncludeFileQueryChange={onIncludeFileQueryChange ?? (() => {})}
				onExcludeFileQueryChange={onExcludeFileQueryChange ?? (() => {})}
				onSelectSearchResult={onSelectSearchResult}
				inputRef={searchInputRef}
			/>
		);
	}

	return (
		<div className="flex h-full min-h-0 flex-col">
			{/* <div className="border-b border-white/8 px-4 py-4">
				<p className="text-[11px] uppercase tracking-[0.24em] text-white/34">
					文件浏览
				</p>
				<p className="mt-1 text-xs text-white/44">按目录浏览项目文本文件</p>
			</div> */}
			<div className="min-h-0 flex-1 overflow-y-auto px-3 py-3 custom-scrollbar-dark">
				{tree.length > 0 ? (
					<ProjectCodeBrowserTree
						nodes={tree}
						expandedFolders={expandedFolders}
						selectedFilePath={selectedFilePath}
						onToggleFolder={onToggleFolder}
						onSelectFile={onSelectFile}
						appearance={appearance ?? "native-explorer"}
					/>
				) : (
					<div className="px-3 py-8 text-center text-sm text-white/42">
						当前项目没有可浏览的文本文件
					</div>
				)}
			</div>
		</div>
	);
}

export function ProjectCodeBrowserWorkspace({
	tree,
	expandedFolders,
	selectedFilePath,
	selectedFileState,
	browserMode = "files",
	searchQuery = "",
	includeFileQuery = "",
	excludeFileQuery = "",
	searchStatus = { state: "idle", scanned: 0, total: 0 },
	searchResults = [],
	onToggleFolder,
	onSelectFile,
	onSelectMode = () => {},
	onSearchQueryChange = () => {},
	onIncludeFileQueryChange = () => {},
	onExcludeFileQueryChange = () => {},
	onSelectSearchResult = () => {},
	appearance = "native-explorer",
	previewDecorations,
	searchInputRef,
	className,
}: ProjectCodeBrowserWorkspaceProps) {
	return (
		<section
			className={cn(
				"grid min-h-0 grid-cols-1 gap-4 overflow-hidden xl:grid-cols-[52px_minmax(280px,320px)_minmax(0,1fr)]",
				className,
			)}
		>
			<ProjectCodeBrowserModeRail
				browserMode={browserMode}
				onSelectMode={onSelectMode}
				appearance={appearance}
			/>

			<div
				className={cn(
					getPaneShellClasses(appearance),
					"min-h-[360px] overflow-hidden xl:min-h-0",
				)}
			>
				<ProjectCodeBrowserSidePanel
					tree={tree}
					expandedFolders={expandedFolders}
					selectedFilePath={selectedFilePath}
					browserMode={browserMode}
					searchQuery={searchQuery}
					includeFileQuery={includeFileQuery}
					excludeFileQuery={excludeFileQuery}
					searchStatus={searchStatus}
					searchResults={searchResults}
					onToggleFolder={onToggleFolder}
					onSelectFile={onSelectFile}
					onSearchQueryChange={onSearchQueryChange}
					onIncludeFileQueryChange={onIncludeFileQueryChange}
					onExcludeFileQueryChange={onExcludeFileQueryChange}
					onSelectSearchResult={onSelectSearchResult}
					appearance={appearance}
					searchInputRef={searchInputRef}
				/>
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
	browserMode = "files",
	searchQuery = "",
	includeFileQuery = "",
	excludeFileQuery = "",
	searchStatus = { state: "idle", scanned: 0, total: 0 },
	searchResults = [],
	onBack,
	onToggleFolder,
	onSelectFile,
	onSelectMode = () => {},
	onSearchQueryChange = () => {},
	onIncludeFileQueryChange = () => {},
	onExcludeFileQueryChange = () => {},
	onSelectSearchResult = () => {},
	appearance = "native-explorer",
	previewDecorations,
	searchInputRef,
}: ProjectCodeBrowserContentProps) {
	void filesCount;
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
					browserMode={browserMode}
					searchQuery={searchQuery}
					includeFileQuery={includeFileQuery}
					excludeFileQuery={excludeFileQuery}
					searchStatus={searchStatus}
					searchResults={searchResults}
					onToggleFolder={onToggleFolder}
					onSelectFile={onSelectFile}
					onSelectMode={onSelectMode}
					onSearchQueryChange={onSearchQueryChange}
					onIncludeFileQueryChange={onIncludeFileQueryChange}
					onExcludeFileQueryChange={onExcludeFileQueryChange}
					onSelectSearchResult={onSelectSearchResult}
					appearance={appearance}
					previewDecorations={previewDecorations}
					searchInputRef={searchInputRef}
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
	const [projectFiles, setProjectFiles] = useState<ProjectCodeBrowserFileEntry[]>([]);
	const [tree, setTree] = useState<ProjectCodeBrowserTreeNode[]>([]);
	const [filesCount, setFilesCount] = useState(0);
	const [expandedFolders, setExpandedFolders] = useState<Set<string>>(
		() => new Set(),
	);
	const [selectedFilePath, setSelectedFilePath] = useState<string | null>(null);
	const [fileStates, setFileStates] = useState<
		Record<string, ProjectCodeBrowserFileViewState>
	>({});
	const [browserMode, setBrowserMode] = useState<ProjectCodeBrowserMode>("files");
	const [searchQuery, setSearchQuery] = useState("");
	const [includeFileQuery, setIncludeFileQuery] = useState("");
	const [excludeFileQuery, setExcludeFileQuery] = useState("");
	const [searchStatus, setSearchStatus] = useState<ProjectCodeBrowserSearchStatus>({
		state: "idle",
		scanned: 0,
		total: 0,
	});
	const [searchResults, setSearchResults] = useState<ProjectCodeBrowserSearchResult[]>([]);
	const [previewDecorations, setPreviewDecorations] = useState<
		Record<string, ProjectCodeBrowserPreviewDecoration | undefined>
	>({});
	const searchInputRef = useRef<HTMLInputElement | null>(null);
	const fileStatesRef = useRef<Record<string, ProjectCodeBrowserFileViewState>>({});
	const pendingFileLoadsRef = useRef<
		Record<string, Promise<ProjectCodeBrowserFileViewState>>
	>({});
	const searchSessionRef = useRef(0);

	const from =
		typeof (location.state as { from?: unknown } | null)?.from === "string"
			? ((location.state as { from?: string }).from ?? "")
			: "";

	const updateFileState = useCallback(
		(filePath: string, nextState: ProjectCodeBrowserFileViewState) => {
			setFileStates((current) => {
				const next = {
					...current,
					[filePath]: nextState,
				};
				fileStatesRef.current = next;
				return next;
			});
		},
		[],
	);

	useEffect(() => {
		fileStatesRef.current = fileStates;
	}, [fileStates]);

	useEffect(() => {
		return () => {
			searchSessionRef.current += 1;
		};
	}, []);

	useEffect(() => {
		if (browserMode !== "search") return;
		const frame = window.requestAnimationFrame(() => {
			searchInputRef.current?.focus();
		});
		return () => window.cancelAnimationFrame(frame);
	}, [browserMode]);

	const loadFileState = useCallback(
		async (filePath: string, options?: { selectFile?: boolean }) => {
			if (!id || project?.source_type !== "zip") {
				return { status: "idle" } as ProjectCodeBrowserFileViewState;
			}

			if (options?.selectFile) {
				setSelectedFilePath(filePath);
			}

			const cachedState = fileStatesRef.current[filePath];
			if (cachedState && cachedState.status !== "idle" && cachedState.status !== "loading") {
				return cachedState;
			}

			const pending = pendingFileLoadsRef.current[filePath];
			if (pending) {
				return pending;
			}

			updateFileState(filePath, { status: "loading" });
			const request = api
				.getProjectFileContent(id, filePath)
				.then((response) => {
					const nextState = resolveProjectCodeBrowserFileSuccess(response);
					updateFileState(filePath, nextState);
					return nextState;
				})
				.catch((requestError) => {
					const nextState = resolveProjectCodeBrowserFileFailure(requestError);
					updateFileState(filePath, nextState);
					return nextState;
				})
				.finally(() => {
					delete pendingFileLoadsRef.current[filePath];
				});

			pendingFileLoadsRef.current[filePath] = request;
			return request;
		},
		[id, project?.source_type, updateFileState],
	);

	useEffect(() => {
		let cancelled = false;

		async function load() {
			setLoading(true);
			setError(null);
			setProject(null);
			setProjectFiles([]);
			setTree([]);
			setFilesCount(0);
			setExpandedFolders(new Set());
			setSelectedFilePath(null);
			setFileStates({});
			fileStatesRef.current = {};
			pendingFileLoadsRef.current = {};
			setBrowserMode("files");
			setSearchQuery("");
			setIncludeFileQuery("");
			setExcludeFileQuery("");
			setSearchStatus({ state: "idle", scanned: 0, total: 0 });
			setSearchResults([]);
			setPreviewDecorations({});

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

				setProjectFiles(files);
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

	const filteredProjectFiles = useMemo(
		() =>
			filterProjectCodeBrowserFilesByPath(projectFiles, {
				include: includeFileQuery,
				exclude: excludeFileQuery,
			}),
		[excludeFileQuery, includeFileQuery, projectFiles],
	);

	useEffect(() => {
		const normalizedQuery = normalizeProjectCodeBrowserSearchQuery(searchQuery);
		const sessionId = searchSessionRef.current + 1;
		searchSessionRef.current = sessionId;
		const totalFiles = filteredProjectFiles.length;

		if (!normalizedQuery) {
			setSearchResults([]);
			setSearchStatus({ state: "idle", scanned: 0, total: totalFiles });
			return;
		}

		const fileResults = buildProjectCodeBrowserFileSearchResults(
			filteredProjectFiles,
			normalizedQuery,
		);
		setSearchResults(fileResults.slice(0, MAX_TOTAL_SEARCH_RESULTS));

		if (!shouldProjectCodeBrowserSearchContent(normalizedQuery)) {
			setSearchStatus({ state: "done", scanned: 0, total: 0 });
			return;
		}

		let cancelled = false;
		const contentResults: ProjectCodeBrowserSearchResult[] = [];
		let scanned = 0;
		setSearchStatus({ state: "scanning", scanned: 0, total: totalFiles });

		const applyProgress = () => {
			if (cancelled || searchSessionRef.current !== sessionId) return;
			setSearchResults(
				mergeProjectCodeBrowserSearchResults(fileResults, contentResults, {
					maxResults: MAX_TOTAL_SEARCH_RESULTS,
				}),
			);
			setSearchStatus({
				state: "scanning",
				scanned,
				total: totalFiles,
			});
		};

		const scanFile = async (file: ProjectCodeBrowserFileEntry) => {
			const state = await loadFileState(file.path);
			if (cancelled || searchSessionRef.current !== sessionId) return;

			if (state.status === "ready") {
				contentResults.push(
					...buildProjectCodeBrowserContentSearchResults(
						file.path,
						state.content,
						normalizedQuery,
						{ maxMatchesPerFile: MAX_CONTENT_MATCHES_PER_FILE },
					),
				);
			}

			scanned += 1;
			applyProgress();
		};

		const workerCount = Math.min(SEARCH_CONTENT_CONCURRENCY, Math.max(totalFiles, 1));
		void Promise.all(
			Array.from({ length: workerCount }, async (_, workerIndex) => {
				for (let index = workerIndex; index < filteredProjectFiles.length; index += workerCount) {
					if (cancelled || searchSessionRef.current !== sessionId) return;
					await scanFile(filteredProjectFiles[index]);
				}
			}),
		)
			.then(() => {
				if (cancelled || searchSessionRef.current !== sessionId) return;
				setSearchResults(
					mergeProjectCodeBrowserSearchResults(fileResults, contentResults, {
						maxResults: MAX_TOTAL_SEARCH_RESULTS,
					}),
				);
				setSearchStatus({
					state: "done",
					scanned,
					total: totalFiles,
				});
			})
			.catch(() => {
				if (cancelled || searchSessionRef.current !== sessionId) return;
				setSearchStatus({
					state: "failed",
					scanned,
					total: totalFiles,
					error: "搜索失败，请稍后重试",
				});
			});

			return () => {
				cancelled = true;
			};
	}, [excludeFileQuery, filteredProjectFiles, includeFileQuery, loadFileState, searchQuery]);

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

	const handleSelectMode = useCallback((mode: ProjectCodeBrowserMode) => {
		setBrowserMode(mode);
	}, []);

	const handleSelectFile = useCallback(
		async (filePath: string) => {
			setPreviewDecorations({});
			await loadFileState(filePath, { selectFile: true });
		},
		[loadFileState],
	);

	const handleSelectSearchResult = useCallback(
		async (result: ProjectCodeBrowserSearchResult) => {
			setPreviewDecorations(
				resolveProjectCodeBrowserPreviewDecorationForSearchResult(result),
			);
			await loadFileState(result.filePath, { selectFile: true });
		},
		[loadFileState],
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
			browserMode={browserMode}
			searchQuery={searchQuery}
			includeFileQuery={includeFileQuery}
			excludeFileQuery={excludeFileQuery}
			searchStatus={searchStatus}
			searchResults={searchResults}
			onBack={handleBack}
			onToggleFolder={handleToggleFolder}
			onSelectFile={handleSelectFile}
			onSelectMode={handleSelectMode}
			onSearchQueryChange={setSearchQuery}
			onIncludeFileQueryChange={setIncludeFileQuery}
			onExcludeFileQueryChange={setExcludeFileQuery}
			onSelectSearchResult={handleSelectSearchResult}
			previewDecorations={previewDecorations}
			searchInputRef={searchInputRef}
		/>
	);
}
