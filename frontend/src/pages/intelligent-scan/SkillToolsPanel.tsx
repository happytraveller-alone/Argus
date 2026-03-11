import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { Search } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
	Table,
	TableBody,
	TableCell,
	TableHead,
	TableHeader,
	TableRow,
} from "@/components/ui/table";
import { api } from "@/shared/api/database";
import { SKILL_TOOLS_CATALOG } from "./skillToolsCatalog";
import {
	DEFAULT_MCP_CATALOG,
	normalizeMcpCatalog,
	type McpCatalogItem,
} from "./mcpCatalog";
import {
	EXTERNAL_TOOLS_PAGE_SIZE,
	buildExternalToolListState,
	buildExternalToolRows,
	type SkillAvailabilityMap,
} from "./externalToolsViewModel";

function toObjectRecord(value: unknown): Record<string, unknown> {
	return value && typeof value === "object" && !Array.isArray(value)
		? (value as Record<string, unknown>)
		: {};
}

function renderCapabilities(capabilities: string[]) {
	if (!capabilities.length) {
		return <span className="text-sm text-muted-foreground">-</span>;
	}

	return (
		<div className="space-y-1.5 py-0.5">
			{capabilities.map((capability) => (
				<div
					key={capability}
					className="text-sm leading-6 text-foreground/90 break-words"
				>
					{capability}
				</div>
			))}
		</div>
	);
}

export default function SkillToolsPanel() {
	const [mcpCatalog, setMcpCatalog] = useState<McpCatalogItem[]>(DEFAULT_MCP_CATALOG);
	const [skillAvailability, setSkillAvailability] = useState<SkillAvailabilityMap>({});
	const [mcpCatalogLoading, setMcpCatalogLoading] = useState(false);
	const [mcpCatalogFallbackNotice, setMcpCatalogFallbackNotice] = useState<string | null>(null);
	const [searchQuery, setSearchQuery] = useState("");
	const [page, setPage] = useState(1);

	useEffect(() => {
		let mounted = true;
		const loadRuntimeCatalog = async () => {
			setMcpCatalogLoading(true);
			try {
				const config = await api.getUserConfig();
				if (!mounted) return;

				const otherConfig = toObjectRecord(config?.otherConfig);
				const mcpConfig = toObjectRecord(otherConfig.mcpConfig);
				const runtimeSkillAvailability = mcpConfig.skillAvailability;
				if (runtimeSkillAvailability && typeof runtimeSkillAvailability === "object") {
					setSkillAvailability(runtimeSkillAvailability as SkillAvailabilityMap);
				} else {
					setSkillAvailability({});
				}

				const serverCatalog = mcpConfig.catalog;
				if (Array.isArray(serverCatalog) && serverCatalog.length > 0) {
					setMcpCatalog(normalizeMcpCatalog(serverCatalog));
					setMcpCatalogFallbackNotice(null);
				} else {
					setMcpCatalog(DEFAULT_MCP_CATALOG);
					setMcpCatalogFallbackNotice("后端未返回 MCP 目录，当前展示默认目录（非实时状态）。");
				}
			} catch {
				if (!mounted) return;
				setSkillAvailability({});
				setMcpCatalog(DEFAULT_MCP_CATALOG);
				setMcpCatalogFallbackNotice("MCP 目录加载失败，当前展示默认目录（非实时状态）。");
			} finally {
				if (mounted) {
					setMcpCatalogLoading(false);
				}
			}
		};

		void loadRuntimeCatalog();
		return () => {
			mounted = false;
		};
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
			}),
		[page, rows, searchQuery],
	);

	useEffect(() => {
		if (page !== listState.page) {
			setPage(listState.page);
		}
	}, [listState.page, page]);

	return (
		<div className="space-y-5">
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
					<div className="flex flex-wrap items-center gap-x-4 gap-y-1 text-xs font-mono text-muted-foreground">
						<span>总数 {rows.length}</span>
						<span>命中 {listState.totalRows}</span>
						<span>固定每页 {EXTERNAL_TOOLS_PAGE_SIZE} 条</span>
						<span>
							第 {listState.page} / {listState.totalPages} 页
						</span>
						{mcpCatalogLoading ? (
							<span className="text-primary">目录加载中</span>
						) : null}
					</div>
					{mcpCatalogFallbackNotice ? (
						<div className="text-xs leading-relaxed text-amber-700 dark:text-amber-300">
							{mcpCatalogFallbackNotice}
						</div>
					) : null}
				</div>
			</div>

			<div className="overflow-x-auto">
				<Table className="w-full table-fixed">
					<TableHeader className="bg-transparent">
						<TableRow className="border-b border-border/60 hover:bg-transparent">
							<TableHead className="w-[72px] text-center">序号</TableHead>
							<TableHead className="w-[28%] min-w-[220px]">名称</TableHead>
							<TableHead className="w-[120px] text-center">标签</TableHead>
							<TableHead className="min-w-[320px]">执行功能</TableHead>
							<TableHead className="w-[120px] text-center">操作</TableHead>
						</TableRow>
					</TableHeader>
					<TableBody>
						{listState.pageRows.length ? (
							listState.pageRows.map((row, index) => {
								const order = listState.startIndex + index + 1;
								return (
									<TableRow
										key={`${row.type}:${row.id}`}
										className="border-b border-border/40 align-top"
									>
										<TableCell className="text-center text-sm text-muted-foreground">
											{order}
										</TableCell>
										<TableCell className="align-top">
											<div className="space-y-1">
												<div className="text-sm font-semibold tracking-[0.02em] text-foreground break-all">
													{row.name}
												</div>
												<div className="text-xs font-mono text-muted-foreground break-all">
													{row.id}
												</div>
											</div>
										</TableCell>
										<TableCell className="text-center align-top">
											<Badge variant="outline" className="text-[10px] uppercase">
												{row.type === "mcp" ? "MCP" : "SKILL"}
											</Badge>
										</TableCell>
										<TableCell className="align-top">
											{renderCapabilities(row.capabilities)}
										</TableCell>
										<TableCell className="text-center align-top">
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
										</TableCell>
									</TableRow>
								);
							})
						) : (
							<TableRow className="border-b border-border/40">
								<TableCell colSpan={5} className="py-14 text-center">
									<div className="space-y-1">
										<div className="text-sm font-medium text-foreground">
											未找到匹配的外部工具
										</div>
										<div className="text-xs text-muted-foreground">
											尝试更换名称关键词或执行功能描述。
										</div>
									</div>
								</TableCell>
							</TableRow>
						)}
					</TableBody>
				</Table>
			</div>

			<div className="flex flex-wrap items-center justify-between gap-3 border-t border-border/50 pt-4">
				<span className="text-xs font-mono text-muted-foreground">
					当前展示 {listState.pageRows.length} / {listState.totalRows} 条
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
