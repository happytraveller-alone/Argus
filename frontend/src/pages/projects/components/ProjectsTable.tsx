import { Link } from "react-router-dom";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import {
	Table,
	TableBody,
	TableCell,
	TableHead,
	TableHeader,
	TableRow,
} from "@/components/ui/table";
import type { ProjectsPageRowViewModel } from "../types";
import { PROJECT_ACTION_BTN_SUBTLE } from "../constants";

interface ProjectsTableProps {
	rows: ProjectsPageRowViewModel[];
	onCreateScan: (projectId: string) => void;
}

const VULNERABILITY_COLUMNS = [
	{
		key: "critical",
		label: "严重",
		headClassName: "text-left text-rose-300",
		cellClassName: "text-left font-semibold tabular-nums text-rose-300",
	},
	{
		key: "high",
		label: "高危",
		headClassName: "text-left text-amber-300",
		cellClassName: "text-left font-semibold tabular-nums text-amber-300",
	},
	{
		key: "medium",
		label: "中危",
		headClassName: "text-left text-sky-300",
		cellClassName: "text-left font-semibold tabular-nums text-sky-300",
	},
	{
		key: "low",
		label: "低危",
		headClassName: "text-left text-emerald-300",
		cellClassName: "text-left font-semibold tabular-nums text-emerald-300",
	},
] as const;

export default function ProjectsTable({
	rows,
	onCreateScan,
}: ProjectsTableProps) {
	return (
		<Table>
			<TableHeader>
				<TableRow>
					<TableHead className="min-w-[180px]">项目名称</TableHead>
					<TableHead className="min-w-[150px]">项目大小</TableHead>
					<TableHead className="w-[120px]">状态</TableHead>
					<TableHead className="w-[220px]">执行任务</TableHead>
					<TableHead className="w-[120px]">发现漏洞</TableHead>
					<TableHead className="min-w-[360px]">操作</TableHead>
				</TableRow>
			</TableHeader>
			<TableBody>
				{rows.map((row) => (
					<TableRow key={row.id}>
						<TableCell>
							<Link
								to={row.detailPath}
								state={row.detailState}
								title={row.name}
								className="block max-w-[180px] truncate text-foreground hover:text-primary transition-colors font-semibold"
							>
								{row.name}
							</Link>
						</TableCell>
						<TableCell className="text-sm text-muted-foreground">
							{row.sizeText}
						</TableCell>
						<TableCell>
							<div className="grid grid-cols-2 gap-2 min-w-[180px]">
								<div className="rounded border border-emerald-500/25 bg-emerald-500/10 px-2 py-1">
									<p className="text-sm leading-5 font-semibold text-emerald-300">
										已完成 {row.executionStats.completed}
									</p>
								</div>
								<div className="rounded border border-sky-500/25 bg-sky-500/10 px-2 py-1">
									<p className="text-sm leading-5 font-semibold text-sky-300">
										进行中 {row.executionStats.running}
									</p>
								</div>
							</div>
						</TableCell>
						{VULNERABILITY_COLUMNS.map((column) => (
							<TableCell
								key={`${row.id}-${column.key}`}
								className={column.cellClassName}
							>
								{column.label}: {row.vulnerabilityStats[column.key]}
							</TableCell>
						))}
						<TableCell>
							<div className="flex items-center gap-2 whitespace-nowrap">
								<Button
									asChild
									size="sm"
									variant="outline"
									className="cyber-btn-ghost h-8 px-3"
								>
									<Link to={row.detailPath} state={row.detailState}>
										查看详情
									</Link>
								</Button>
								{row.actions.canBrowseCode ? (
									<Button
										asChild
										size="sm"
										variant="outline"
										className="cyber-btn-ghost h-8 px-3 hover:bg-sky-500/10 hover:text-sky-200 hover:border-sky-500/30"
									>
										<Link
											to={row.actions.browseCodePath}
											state={row.actions.browseCodeState}
										>
											代码浏览
										</Link>
									</Button>
								) : (
									<Button
										size="sm"
										variant="outline"
										className="cyber-btn-ghost h-8 px-3"
										disabled
										title={row.actions.browseCodeDisabledReason ?? undefined}
										aria-label={`代码浏览 ${row.name}（${row.actions.browseCodeDisabledReason ?? "暂不可用"}）`}
									>
										代码浏览
									</Button>
								)}
								<Button
									size="sm"
									className={`${PROJECT_ACTION_BTN_SUBTLE} h-8 px-3`}
									onClick={() => onCreateScan(row.id)}
									disabled={!row.actions.canCreateScan}
								>
									创建扫描
								</Button>
							</div>
						</TableCell>
					</TableRow>
				))}
			</TableBody>
		</Table>
	);
}
