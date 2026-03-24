import type { Project } from "@/shared/types";

interface ResponsiveProjectsPageSizeInput {
	containerHeight: number;
	tableHeaderHeight: number;
	paginationHeight: number;
	rowHeight: number;
}

const MIN_PROJECT_PAGE_SIZE = 1;
const PROJECT_PAGINATION_WINDOW = 7;

function toFiniteNumber(value: unknown): number {
	const parsed = Number(value);
	return Number.isFinite(parsed) ? parsed : 0;
}

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

export function calculateResponsiveProjectsPageSize(
	input: ResponsiveProjectsPageSizeInput,
) {
	const containerHeight = Math.max(toFiniteNumber(input.containerHeight), 0);
	const tableHeaderHeight = Math.max(toFiniteNumber(input.tableHeaderHeight), 0);
	const paginationHeight = Math.max(toFiniteNumber(input.paginationHeight), 0);
	const rowHeight = Math.max(toFiniteNumber(input.rowHeight), 1);
	const availableRowsHeight = Math.max(
		containerHeight - tableHeaderHeight - paginationHeight,
		rowHeight,
	);
	return Math.max(1, Math.floor(availableRowsHeight / rowHeight));
}

export function resolveProjectsFirstVisibleIndex({
	page,
	pageSize,
}: {
	page: number;
	pageSize: number;
}) {
	const safePage = Math.max(1, Math.floor(page) || 1);
	const safePageSize = Math.max(
		MIN_PROJECT_PAGE_SIZE,
		Math.floor(pageSize) || MIN_PROJECT_PAGE_SIZE,
	);
	return (safePage - 1) * safePageSize;
}

export function resolveAnchoredProjectsPage({
	firstVisibleIndex,
	nextPageSize,
	totalRows,
}: {
	firstVisibleIndex: number;
	nextPageSize: number;
	totalRows: number;
}) {
	const safePageSize = Math.max(
		MIN_PROJECT_PAGE_SIZE,
		Math.floor(nextPageSize) || MIN_PROJECT_PAGE_SIZE,
	);
	const safeTotalRows = Math.max(0, Math.floor(totalRows) || 0);
	const lastIndex = Math.max(0, safeTotalRows - 1);
	const clampedIndex = Math.max(
		0,
		Math.min(Math.floor(firstVisibleIndex) || 0, lastIndex),
	);
	const totalPages = Math.max(1, Math.ceil(safeTotalRows / safePageSize));
	const nextPage = Math.floor(clampedIndex / safePageSize) + 1;

	return Math.min(totalPages, Math.max(1, nextPage));
}

export function buildPaginationItems(
	currentPage: number,
	totalPages: number,
	maxVisiblePages = PROJECT_PAGINATION_WINDOW,
): Array<number | "ellipsis"> {
	const safeTotalPages = Math.max(1, Math.floor(totalPages) || 1);
	const safeCurrentPage = Math.min(
		safeTotalPages,
		Math.max(1, Math.floor(currentPage) || 1),
	);
	const safeMaxVisiblePages = Math.max(5, Math.floor(maxVisiblePages) || 5);

	if (safeTotalPages <= safeMaxVisiblePages) {
		return Array.from({ length: safeTotalPages }, (_, index) => index + 1);
	}

	const windowSize = Math.max(1, safeMaxVisiblePages - 2);
	const halfWindow = Math.floor(windowSize / 2);
	let start = Math.max(2, safeCurrentPage - halfWindow);
	let end = start + windowSize - 1;
	const maxEnd = safeTotalPages - 1;

	if (end > maxEnd) {
		end = maxEnd;
		start = Math.max(2, end - windowSize + 1);
	}

	const items: Array<number | "ellipsis"> = [];

	items.push(1);
	if (start > 2) {
		items.push("ellipsis");
	}
	for (let page = start; page <= end; page += 1) {
		items.push(page);
	}
	if (end < safeTotalPages - 1) {
		items.push("ellipsis");
	}
	items.push(safeTotalPages);

	return items;
}
