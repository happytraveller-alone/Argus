import { Button } from "@/components/ui/button";

interface ProjectsPaginationProps {
	currentPage: number;
	totalPages: number;
	totalCount: number;
	totalProjectCount: number;
	pageSize: number;
	currentPageItemCount: number;
	items: Array<number | "ellipsis">;
	onPageChange: (page: number) => void;
}

export default function ProjectsPagination({
	currentPage,
	totalPages,
	totalCount,
	totalProjectCount,
	pageSize,
	currentPageItemCount,
	items,
	onPageChange,
}: ProjectsPaginationProps) {
	const startItem =
		currentPageItemCount > 0 ? (currentPage - 1) * pageSize + 1 : 0;
	const endItem =
		currentPageItemCount > 0 ? startItem + currentPageItemCount - 1 : 0;
	const hasSearchFilter = totalCount !== totalProjectCount;
	const countSummary = hasSearchFilter
		? `共 ${totalProjectCount} 个项目，筛选出 ${totalCount} 个`
		: `共 ${totalProjectCount} 个项目`;
	const pageSummary =
		currentPageItemCount > 0
			? `第 ${currentPage} / ${totalPages} 页，本页显示 ${startItem}-${endItem} 项`
			: `第 ${currentPage} / ${totalPages} 页，本页暂无项目`;

	return (
		<div className="mt-auto pt-4 flex flex-wrap items-center justify-between gap-3">
			<div className="flex flex-col gap-1 text-xs text-muted-foreground sm:flex-row sm:items-center sm:gap-3">
				<span>{countSummary}</span>
				<span>{pageSummary}</span>
			</div>
			<div className="flex items-center gap-1.5">
				<Button
					variant="outline"
					size="sm"
					className="cyber-btn-outline h-8 px-3"
					disabled={currentPage <= 1}
					onClick={() => onPageChange(Math.max(currentPage - 1, 1))}
				>
					上一页
				</Button>
				{items.map((item, index) => {
					if (item === "ellipsis") {
						return (
							<span
								key={`ellipsis-${index}`}
								className="px-2 text-muted-foreground"
							>
								...
							</span>
						);
					}

					return (
						<Button
							key={`page-${item}`}
							size="sm"
							variant={item === currentPage ? "default" : "outline"}
							className={`h-8 min-w-8 px-2 ${
								item === currentPage ? "cyber-btn-primary" : "cyber-btn-ghost"
							}`}
							onClick={() => onPageChange(item)}
						>
							{item}
						</Button>
					);
				})}
				<Button
					variant="outline"
					size="sm"
					className="cyber-btn-outline h-8 px-3"
					disabled={currentPage >= totalPages}
					onClick={() => onPageChange(Math.min(currentPage + 1, totalPages))}
				>
					下一页
				</Button>
			</div>
		</div>
	);
}
