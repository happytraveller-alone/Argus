import type { Project } from "@/shared/types";

export function filterProjects<T extends Pick<Project, "name" | "description">>(
	projects: T[],
	searchTerm: string,
) {
	const keyword = searchTerm.trim().toLowerCase();
	if (!keyword) return projects;

	return projects.filter((project) => {
		return (
			project.name.toLowerCase().includes(keyword) ||
			(project.description || "").toLowerCase().includes(keyword)
		);
	});
}

export function paginateItems<T>(
	items: T[],
	currentPage: number,
	pageSize: number,
) {
	const start = (currentPage - 1) * pageSize;
	return items.slice(start, start + pageSize);
}

export function buildPaginationItems(
	currentPage: number,
	totalPages: number,
): Array<number | "ellipsis"> {
	if (totalPages <= 7) {
		return Array.from({ length: totalPages }, (_, index) => index + 1);
	}

	const pages = new Set<number>([
		1,
		totalPages,
		currentPage - 1,
		currentPage,
		currentPage + 1,
	]);
	const sortedPages = Array.from(pages)
		.filter((page) => page >= 1 && page <= totalPages)
		.sort((a, b) => a - b);

	const items: Array<number | "ellipsis"> = [];
	let previousPage = 0;
	for (const page of sortedPages) {
		if (previousPage > 0 && page - previousPage > 1) {
			items.push("ellipsis");
		}
		items.push(page);
		previousPage = page;
	}
	return items;
}

export function getCurrentPageSelectionState(params: {
	currentPageProjectIds: string[];
	selectedProjectIds: Set<string>;
}) {
	const { currentPageProjectIds, selectedProjectIds } = params;
	if (currentPageProjectIds.length === 0) {
		return {
			isAllSelected: false,
			isSomeSelected: false,
			selectedCount: 0,
		};
	}

	const selectedCount = currentPageProjectIds.filter((projectId) =>
		selectedProjectIds.has(projectId),
	).length;

	return {
		isAllSelected: selectedCount === currentPageProjectIds.length,
		isSomeSelected:
			selectedCount > 0 && selectedCount < currentPageProjectIds.length,
		selectedCount,
	};
}

export function pruneSelectedProjectIds(
	selectedProjectIds: Set<string>,
	projects: Pick<Project, "id">[],
) {
	if (selectedProjectIds.size === 0) {
		return selectedProjectIds;
	}

	const validProjectIds = new Set(projects.map((project) => project.id));
	const next = new Set<string>();
	for (const projectId of selectedProjectIds) {
		if (validProjectIds.has(projectId)) {
			next.add(projectId);
		}
	}

	return next.size === selectedProjectIds.size ? selectedProjectIds : next;
}
