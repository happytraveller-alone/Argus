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
