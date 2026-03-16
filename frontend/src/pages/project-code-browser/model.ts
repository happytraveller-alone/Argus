import type { ProjectFileContentResponse } from "@/shared/api/database";

export interface ProjectCodeBrowserFileEntry {
	path: string;
	size: number;
}

export interface ProjectCodeBrowserTreeNode {
	name: string;
	path: string;
	kind: "file" | "directory";
	size?: number;
	children?: ProjectCodeBrowserTreeNode[];
}

export type ProjectCodeBrowserMode = "files" | "search";

export type ProjectCodeBrowserFileViewState =
	| { status: "idle" }
	| { status: "loading" }
	| {
			status: "ready";
			filePath: string;
			content: string;
			size: number;
			encoding: string;
	  }
	| { status: "unavailable"; message: string }
	| { status: "failed"; message: string };

export const PROJECT_CODE_BROWSER_EMPTY_MESSAGE =
	"从左侧文件树选择一个文件开始浏览";
export const PROJECT_CODE_BROWSER_UNAVAILABLE_MESSAGE =
	"当前文件不是文本文件，暂不支持预览";
export const PROJECT_CODE_BROWSER_FAILED_MESSAGE =
	"读取文件失败，请稍后重试";
export const PROJECT_CODE_BROWSER_FALLBACK_PATH = "/projects#project-browser";
export const PROJECT_CODE_BROWSER_SEARCH_EMPTY_MESSAGE =
	"输入文件名或代码片段开始搜索";
export const PROJECT_CODE_BROWSER_SEARCH_NO_RESULTS_MESSAGE =
	"未找到匹配结果，试试更短的关键词或不同片段";
export const PROJECT_CODE_BROWSER_SEARCH_LOADING_MESSAGE =
	"正在补充内容命中...";

export interface ProjectCodeBrowserSearchHighlightPart {
	text: string;
	matched: boolean;
}

export interface ProjectCodeBrowserPreviewDecoration {
	focusLine?: number | null;
	highlightStartLine?: number | null;
	highlightEndLine?: number | null;
}

export interface ProjectCodeBrowserSearchResult {
	id: string;
	kind: "file" | "content";
	filePath: string;
	fileName: string;
	directoryPath: string;
	lineNumber: number | null;
	excerpt: string;
	score: number;
	pathParts: ProjectCodeBrowserSearchHighlightPart[];
	fileNameParts: ProjectCodeBrowserSearchHighlightPart[];
	excerptParts: ProjectCodeBrowserSearchHighlightPart[];
}

export interface ProjectCodeBrowserSearchStatus {
	state: "idle" | "scanning" | "done" | "failed";
	scanned: number;
	total: number;
	error?: string;
}

type MutableTreeNode = ProjectCodeBrowserTreeNode & {
	children?: MutableTreeNode[];
};

function getProjectCodeBrowserFileName(filePath: string) {
	const normalized = String(filePath || "").trim();
	const index = normalized.lastIndexOf("/");
	return index >= 0 ? normalized.slice(index + 1) : normalized;
}

function getProjectCodeBrowserDirectoryPath(filePath: string) {
	const normalized = String(filePath || "").trim();
	const index = normalized.lastIndexOf("/");
	return index >= 0 ? normalized.slice(0, index) : "";
}

function getProjectCodeBrowserSearchScore(value: string, query: string) {
	const normalizedValue = String(value || "").toLowerCase();
	if (!normalizedValue || !query) return 0;
	if (normalizedValue === query) return 420;
	if (normalizedValue.startsWith(query)) return 320;
	if (normalizedValue.includes(query)) return 220;
	return 0;
}

function compareSearchResults(
	left: ProjectCodeBrowserSearchResult,
	right: ProjectCodeBrowserSearchResult,
) {
	if (left.kind !== right.kind) {
		return left.kind === "file" ? -1 : 1;
	}
	if (left.score !== right.score) {
		return right.score - left.score;
	}
	const pathCompare = left.filePath.localeCompare(right.filePath, "zh-CN", {
		numeric: true,
		sensitivity: "base",
	});
	if (pathCompare !== 0) return pathCompare;
	return (left.lineNumber ?? 0) - (right.lineNumber ?? 0);
}

function compareTreeNodes(
	left: ProjectCodeBrowserTreeNode,
	right: ProjectCodeBrowserTreeNode,
) {
	if (left.kind !== right.kind) {
		return left.kind === "directory" ? -1 : 1;
	}
	return left.name.localeCompare(right.name, "zh-CN", {
		numeric: true,
		sensitivity: "base",
	});
}

function sortTreeNodes(nodes: MutableTreeNode[]): ProjectCodeBrowserTreeNode[] {
	return nodes
		.sort(compareTreeNodes)
		.map((node) => ({
			...node,
			children: node.children ? sortTreeNodes(node.children) : undefined,
		}));
}

export function buildProjectCodeBrowserTree(
	files: ProjectCodeBrowserFileEntry[],
): ProjectCodeBrowserTreeNode[] {
	const root: MutableTreeNode[] = [];
	const nodeMap = new Map<string, MutableTreeNode>();

	for (const file of files) {
		const normalizedPath = String(file.path || "").trim();
		if (!normalizedPath) continue;

		const parts = normalizedPath.split("/").filter(Boolean);
		let currentChildren = root;
		let currentPath = "";

		for (let index = 0; index < parts.length; index += 1) {
			const name = parts[index];
			currentPath = currentPath ? `${currentPath}/${name}` : name;
			const isLeaf = index === parts.length - 1;
			let node = nodeMap.get(currentPath);

			if (!node) {
				node = {
					name,
					path: currentPath,
					kind: isLeaf ? "file" : "directory",
					size: isLeaf ? file.size : undefined,
					children: isLeaf ? undefined : [],
				};
				nodeMap.set(currentPath, node);
				currentChildren.push(node);
			}

			if (!isLeaf) {
				if (!node.children) {
					node.children = [];
				}
				currentChildren = node.children;
			}
		}
	}

	return sortTreeNodes(root);
}

export function normalizeProjectCodeBrowserSearchQuery(input: string): string {
	return String(input || "").trim().toLowerCase();
}

export function parseProjectCodeBrowserFileFilterTokens(input: string): string[] {
	return String(input || "")
		.split(/[\n,，]+/g)
		.map((token) => token.trim().toLowerCase())
		.filter(Boolean);
}

export function shouldProjectCodeBrowserSearchContent(query: string): boolean {
	return Array.from(normalizeProjectCodeBrowserSearchQuery(query)).length >= 2;
}

export function filterProjectCodeBrowserFilesByPath(
	files: ProjectCodeBrowserFileEntry[],
	filters?: { include?: string; exclude?: string },
): ProjectCodeBrowserFileEntry[] {
	const includeTokens = parseProjectCodeBrowserFileFilterTokens(filters?.include || "");
	const excludeTokens = parseProjectCodeBrowserFileFilterTokens(filters?.exclude || "");

	return files.filter((file) => {
		const normalizedPath = String(file.path || "").trim().toLowerCase();
		if (!normalizedPath) return false;

		if (
			includeTokens.length > 0 &&
			!includeTokens.some((token) => normalizedPath.includes(token))
		) {
			return false;
		}

		if (
			excludeTokens.length > 0 &&
			excludeTokens.some((token) => normalizedPath.includes(token))
		) {
			return false;
		}

		return true;
	});
}

export function buildProjectCodeBrowserHighlightParts(
	text: string,
	query: string,
): ProjectCodeBrowserSearchHighlightPart[] {
	const rawText = String(text || "");
	const normalizedQuery = normalizeProjectCodeBrowserSearchQuery(query);
	if (!rawText) return [];
	if (!normalizedQuery) {
		return [{ text: rawText, matched: false }];
	}

	const lowerText = rawText.toLowerCase();
	const parts: ProjectCodeBrowserSearchHighlightPart[] = [];
	let cursor = 0;

	while (cursor < rawText.length) {
		const matchIndex = lowerText.indexOf(normalizedQuery, cursor);
		if (matchIndex < 0) {
			parts.push({ text: rawText.slice(cursor), matched: false });
			break;
		}
		if (matchIndex > cursor) {
			parts.push({
				text: rawText.slice(cursor, matchIndex),
				matched: false,
			});
		}
		parts.push({
			text: rawText.slice(matchIndex, matchIndex + normalizedQuery.length),
			matched: true,
		});
		cursor = matchIndex + normalizedQuery.length;
	}

	return parts.filter((part) => part.text.length > 0);
}

export function buildProjectCodeBrowserSearchExcerpt(
	line: string,
	query: string,
	maxLength = 140,
): string {
	const rawLine = String(line || "");
	const normalizedQuery = normalizeProjectCodeBrowserSearchQuery(query);
	if (!normalizedQuery) return rawLine.trim() || rawLine;

	const trimmed = rawLine.trim() || rawLine;
	if (trimmed.length <= maxLength) return trimmed;

	const lowerLine = trimmed.toLowerCase();
	const matchIndex = lowerLine.indexOf(normalizedQuery);
	if (matchIndex < 0) {
		return `${trimmed.slice(0, Math.max(0, maxLength - 1)).trimEnd()}…`;
	}

	const availableContext = Math.max(0, maxLength - normalizedQuery.length);
	const start = Math.max(0, matchIndex - Math.floor(availableContext / 2));
	const end = Math.min(trimmed.length, start + maxLength);
	const prefix = start > 0 ? "…" : "";
	const suffix = end < trimmed.length ? "…" : "";
	return `${prefix}${trimmed.slice(start, end).trim()}${suffix}`;
}

export function buildProjectCodeBrowserFileSearchResults(
	files: ProjectCodeBrowserFileEntry[],
	query: string,
): ProjectCodeBrowserSearchResult[] {
	const normalizedQuery = normalizeProjectCodeBrowserSearchQuery(query);
	if (!normalizedQuery) return [];

	const results: ProjectCodeBrowserSearchResult[] = [];

	for (const file of files) {
		const filePath = String(file.path || "").trim();
		const fileName = getProjectCodeBrowserFileName(filePath);
		const pathScore = getProjectCodeBrowserSearchScore(filePath, normalizedQuery);
		const fileNameScore = getProjectCodeBrowserSearchScore(fileName, normalizedQuery);
		const score = fileNameScore > 0 ? fileNameScore + 60 : pathScore;
		if (score <= 0) continue;

		results.push({
			id: `file:${filePath}`,
			kind: "file",
			filePath,
			fileName,
			directoryPath: getProjectCodeBrowserDirectoryPath(filePath),
			lineNumber: null,
			excerpt: filePath,
			score,
			pathParts: buildProjectCodeBrowserHighlightParts(filePath, normalizedQuery),
			fileNameParts: buildProjectCodeBrowserHighlightParts(
				fileName,
				normalizedQuery,
			),
			excerptParts: [],
		});
	}

	return results.sort(compareSearchResults);
}

export function buildProjectCodeBrowserContentSearchResults(
	filePath: string,
	content: string,
	query: string,
	options?: { maxMatchesPerFile?: number },
): ProjectCodeBrowserSearchResult[] {
	const normalizedQuery = normalizeProjectCodeBrowserSearchQuery(query);
	if (!shouldProjectCodeBrowserSearchContent(normalizedQuery)) return [];

	const maxMatchesPerFile = options?.maxMatchesPerFile ?? 3;
	const normalizedFilePath = String(filePath || "").trim();
	const fileName = getProjectCodeBrowserFileName(normalizedFilePath);
	const directoryPath = getProjectCodeBrowserDirectoryPath(normalizedFilePath);
	const lines = String(content || "").replace(/\r\n/g, "\n").split("\n");
	const results: ProjectCodeBrowserSearchResult[] = [];

	for (let index = 0; index < lines.length; index += 1) {
		const line = lines[index];
		if (!line.toLowerCase().includes(normalizedQuery)) continue;
		const lineNumber = index + 1;
		const excerpt = buildProjectCodeBrowserSearchExcerpt(line, normalizedQuery);
		results.push({
			id: `content:${normalizedFilePath}:${lineNumber}`,
			kind: "content",
			filePath: normalizedFilePath,
			fileName,
			directoryPath,
			lineNumber,
			excerpt,
			score: 100 - lineNumber / 10000,
			pathParts: buildProjectCodeBrowserHighlightParts(
				normalizedFilePath,
				normalizedQuery,
			),
			fileNameParts: buildProjectCodeBrowserHighlightParts(
				fileName,
				normalizedQuery,
			),
			excerptParts: buildProjectCodeBrowserHighlightParts(
				excerpt,
				normalizedQuery,
			),
		});
		if (results.length >= maxMatchesPerFile) break;
	}

	return results;
}

export function mergeProjectCodeBrowserSearchResults(
	fileResults: ProjectCodeBrowserSearchResult[],
	contentResults: ProjectCodeBrowserSearchResult[],
	options?: { maxResults?: number },
): ProjectCodeBrowserSearchResult[] {
	const deduped = new Map<string, ProjectCodeBrowserSearchResult>();
	for (const result of [...fileResults, ...contentResults]) {
		if (!deduped.has(result.id)) {
			deduped.set(result.id, result);
		}
	}

	return Array.from(deduped.values())
		.sort(compareSearchResults)
		.slice(0, options?.maxResults ?? 50);
}

export function resolveProjectCodeBrowserPreviewDecorationForSearchResult(
	result: ProjectCodeBrowserSearchResult,
): Record<string, ProjectCodeBrowserPreviewDecoration> {
	if (
		result.kind === "content" &&
		typeof result.lineNumber === "number" &&
		Number.isFinite(result.lineNumber)
	) {
		return {
			[result.filePath]: {
				focusLine: result.lineNumber,
				highlightStartLine: result.lineNumber,
				highlightEndLine: result.lineNumber,
			},
		};
	}

	return {
		[result.filePath]: {},
	};
}

export function toggleProjectCodeBrowserFolder(
	current: Set<string>,
	folderPath: string,
): Set<string> {
	const next = new Set(current);
	if (next.has(folderPath)) {
		next.delete(folderPath);
	} else {
		next.add(folderPath);
	}
	return next;
}

export function resolveProjectCodeBrowserBackTarget(input: {
	from?: string | null;
	hasHistory: boolean;
}): number | string {
	if (input.hasHistory) {
		return -1;
	}
	const normalizedFrom =
		typeof input.from === "string" && input.from.startsWith("/")
			? input.from
			: "";
	return normalizedFrom || PROJECT_CODE_BROWSER_FALLBACK_PATH;
}

export function resolveProjectCodeBrowserFileSuccess(
	response: ProjectFileContentResponse,
): ProjectCodeBrowserFileViewState {
	if (!response.is_text) {
		return {
			status: "unavailable",
			message: PROJECT_CODE_BROWSER_UNAVAILABLE_MESSAGE,
		};
	}

	return {
		status: "ready",
		filePath: response.file_path,
		content: response.content,
		size: response.size,
		encoding: response.encoding,
	};
}

export function resolveProjectCodeBrowserFileFailure(
	_error: unknown,
): ProjectCodeBrowserFileViewState {
	return {
		status: "failed",
		message: PROJECT_CODE_BROWSER_FAILED_MESSAGE,
	};
}
