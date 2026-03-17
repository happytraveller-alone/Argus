import { useEffect, useMemo, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { Grid3X3, Search } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { api } from "@/shared/api/database";
import { SKILL_TOOLS_CATALOG } from "./skillToolsCatalog";
import {
	DEFAULT_MCP_CATALOG,
	type McpCatalogItem,
} from "./mcpCatalog";
import {
	buildExternalToolListState,
	buildExternalToolRows,
	type SkillAvailabilityMap,
} from "./externalToolsViewModel";
import {
	EXTERNAL_TOOLS_CARD_MIN_WIDTH,
	resolveAnchoredExternalToolsPage,
	resolveExternalToolsFirstVisibleIndex,
	resolveResponsiveExternalToolsLayout,
} from "./externalToolsResponsiveLayout";

export default function SkillToolsPanel() {
	const [mcpCatalog, setMcpCatalog] = useState<McpCatalogItem[]>(DEFAULT_MCP_CATALOG);
	const [skillAvailability, setSkillAvailability] = useState<SkillAvailabilityMap>({});
	const [searchQuery, setSearchQuery] = useState("");
	const [page, setPage] = useState(1);
	const gridViewportRef = useRef<HTMLDivElement | null>(null);
	const pageSizeRef = useRef(1);
	const [layout, setLayout] = useState(() =>
		resolveResponsiveExternalToolsLayout({
			width: 0,
			height: 0,
		}),
	);

	useEffect(() => {
		void api.getUserConfig().then(() => {
			setSkillAvailability({});
			setMcpCatalog(DEFAULT_MCP_CATALOG);
		}).catch(() => {
			setSkillAvailability({});
			setMcpCatalog(DEFAULT_MCP_CATALOG);
		});
	}, []);

	const rows = useMemo(
		() =>
			buildExternalToolRows({
				mcpCatalog: mcpCatalog.filter((item) => item.type === "mcp-server"),
				skillCatalog: SKILL_TOOLS_CATALOG,
				skillAvailability,
			}),
		[mcpCatalog, skillAvailability],
	);

	const listState = useMemo(
		() =>
			buildExternalToolListState({
				rows,
				searchQuery,
				page,
				pageSize: layout.pageSize,
			}),
		[layout.pageSize, page, rows, searchQuery],
	);

	useEffect(() => {
		if (page !== listState.page) {
			setPage(listState.page);
		}
	}, [listState.page, page]);

	useEffect(() => {
		if (!gridViewportRef.current) {
			return;
		}

		const viewportNode = gridViewportRef.current;
		const updateLayout = () => {
			const { width, height } = viewportNode.getBoundingClientRect();
			const nextLayout = resolveResponsiveExternalToolsLayout({
				width,
				height,
			});
			setLayout((current) => {
				if (
					current.columnCount === nextLayout.columnCount &&
					current.rowCount === nextLayout.rowCount &&
					current.pageSize === nextLayout.pageSize
				) {
					return current;
				}
				return nextLayout;
			});
		};

		updateLayout();
		const observer =
			typeof ResizeObserver === "undefined"
				? null
				: new ResizeObserver(() => {
						updateLayout();
					});
		observer?.observe(viewportNode);
		window.addEventListener("resize", updateLayout);
		window.visualViewport?.addEventListener("resize", updateLayout);

		return () => {
			observer?.disconnect();
			window.removeEventListener("resize", updateLayout);
			window.visualViewport?.removeEventListener("resize", updateLayout);
		};
	}, []);

	useEffect(() => {
		setPage((current) => {
			const firstVisibleIndex = resolveExternalToolsFirstVisibleIndex({
				page: current,
				pageSize: pageSizeRef.current,
			});
			const nextPage = resolveAnchoredExternalToolsPage({
				firstVisibleIndex,
				nextPageSize: layout.pageSize,
				totalRows: listState.totalRows,
			});
			return current === nextPage ? current : nextPage;
		});
		pageSizeRef.current = layout.pageSize;
	}, [layout.pageSize, listState.totalRows]);

	return (
		<div className="flex flex-1 flex-col gap-5 min-h-0">
			<div className="grid gap-4 xl:grid-cols-[minmax(0,1fr)_auto] xl:items-end">
				<div className="space-y-3">
					<Input
						type="search"
						value={searchQuery}
						onChange={(event) => {
							setSearchQuery(event.target.value);
							setPage(1);
						}}
						startIcon={<Search className="h-4 w-4" />}
						placeholder="搜索工具名称或执行功能..."
						className="cyber-input h-11 border-border/60 bg-background/70"
						wrapperClassName="max-w-full"
						aria-label="搜索工具名称或执行功能"
					/>
				</div>
			</div>

			<div ref={gridViewportRef} className="flex flex-1 min-h-[20rem] flex-col">
				{listState.pageRows.length ? (
					<div
						className="grid flex-1 content-start gap-4"
						style={{
							gridTemplateColumns: `repeat(auto-fit, minmax(${EXTERNAL_TOOLS_CARD_MIN_WIDTH}px, 1fr))`,
						}}
					>
						{listState.pageRows.map((row, index) => {
							const order = listState.startIndex + index + 1;
							return (
								<article
									key={`${row.type}:${row.id}`}
									className="cyber-card flex h-full min-h-[240px] flex-col border border-border/50 bg-background/40 p-4 transition-colors duration-200 hover:border-primary/40 hover:bg-background/60"
								>
									<div className="flex items-start justify-between gap-3">
										<div className="space-y-2 min-w-0">
											<div className="text-[11px] font-mono uppercase tracking-[0.28em] text-muted-foreground">
												#{String(order).padStart(2, "0")}
											</div>
											<div className="text-base font-semibold tracking-[0.02em] text-foreground break-all">
												{row.name}
											</div>
										</div>
										<Badge variant="outline" className="text-[10px] uppercase">
											{row.type === "mcp" ? "MCP" : "SKILL"}
										</Badge>
									</div>

									<div className="mt-5 flex-1 space-y-3">
										<div className="flex items-center gap-2 text-[11px] font-mono uppercase tracking-[0.28em] text-muted-foreground">
											<Grid3X3 className="h-3.5 w-3.5" />
											执行功能
										</div>
										{row.capabilities.length ? (
											<ul className="space-y-2 text-sm leading-6 text-foreground/90">
												{row.capabilities.map((capability) => (
													<li
														key={`${row.id}:${capability}`}
														className="flex items-start gap-2"
													>
														<span className="mt-2 h-1.5 w-1.5 flex-shrink-0 rounded-full bg-primary/80" />
														<span className="break-words">{capability}</span>
													</li>
												))}
											</ul>
										) : (
											<div className="text-sm text-muted-foreground">暂无执行功能说明</div>
										)}
									</div>

									<div className="mt-5 flex items-center justify-between gap-3 border-t border-border/40 pt-4">
										<div className="text-xs font-mono text-muted-foreground">
											{row.type === "mcp" ? "MCP 服务" : "Skill 工具"}
										</div>
										<Button
											asChild
											size="sm"
											variant="outline"
											className="cyber-btn-ghost h-8 px-3"
										>
											<Link
												to={`/scan-config/external-tools/${row.type}/${encodeURIComponent(row.id)}`}
											>
												详情
											</Link>
										</Button>
									</div>
								</article>
							);
						})}
					</div>
				) : (
					<div className="cyber-card flex flex-1 items-center justify-center border border-dashed border-border/50 bg-background/25 p-8 text-center">
						<div className="space-y-2">
							<div className="text-sm font-medium text-foreground">
								未找到匹配的外部工具
							</div>
							<div className="text-xs text-muted-foreground">
								尝试更换名称关键词或执行功能描述。
							</div>
						</div>
					</div>
				)}
			</div>

			<div className="mt-auto flex flex-wrap items-center justify-between gap-3 border-t border-border/50 pt-4">
				<span className="text-xs font-mono text-muted-foreground">
					当前展示 {listState.pageRows.length} / {listState.totalRows} 条 ·
					每页 {listState.pageSize} 条
				</span>
				<div className="flex items-center gap-2">
					<Button
						type="button"
						variant="outline"
						size="sm"
						className="cyber-btn-ghost h-8 px-3"
						onClick={() => setPage((current) => Math.max(1, current - 1))}
						disabled={listState.page <= 1 || listState.totalRows === 0}
					>
						上一页
					</Button>
					<span className="min-w-[96px] text-center text-xs font-mono text-muted-foreground">
						第 {listState.page} / {listState.totalPages} 页
					</span>
					<Button
						type="button"
						variant="outline"
						size="sm"
						className="cyber-btn-ghost h-8 px-3"
						onClick={() =>
							setPage((current) =>
								Math.min(listState.totalPages, current + 1),
							)
						}
						disabled={
							listState.page >= listState.totalPages || listState.totalRows === 0
						}
					>
						下一页
					</Button>
				</div>
			</div>
		</div>
	);
}
