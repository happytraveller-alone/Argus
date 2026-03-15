import type { ProjectFileContentResponse } from "@/shared/api/database";

export interface ProjectCodeBrowserTreeNode {
	name: string;
	path: string;
	kind: "file" | "directory";
	size?: number;
	children?: ProjectCodeBrowserTreeNode[];
}

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

type MutableTreeNode = ProjectCodeBrowserTreeNode & {
	children?: MutableTreeNode[];
};

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
	files: Array<{ path: string; size: number }>,
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
