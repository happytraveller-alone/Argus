import { Link } from "react-router-dom";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Checkbox } from "@/components/ui/checkbox";
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
	selectedProjectIds: Set<string>;
	isAllCurrentPageSelected: boolean;
	isSomeCurrentPageSelected: boolean;
	onToggleProjectSelection: (projectId: string, checked: boolean) => void;
	onToggleSelectCurrentPage: (checked: boolean) => void;
	onCreateScan: (projectId: string) => void;
	onToggleProjectStatus: (
		projectId: string,
		action: ProjectsPageRowViewModel["statusToggle"]["action"],
	) => void;
}

export default function ProjectsTable({
	rows,
	selectedProjectIds,
	isAllCurrentPageSelected,
	isSomeCurrentPageSelected,
	onToggleProjectSelection,
	onToggleSelectCurrentPage,
	onCreateScan,
	onToggleProjectStatus,
}: ProjectsTableProps) {
	return (
		<Table>
			<TableHeader>
				<TableRow>
					<TableHead className="w-[52px]">
						<Checkbox
							checked={
								isAllCurrentPageSelected
									? true
									: isSomeCurrentPageSelected
										? "indeterminate"
										: false
							}
							onCheckedChange={(checked) =>
								onToggleSelectCurrentPage(Boolean(checked))
							}
							aria-label="全选当前页"
						/>
					</TableHead>
					<TableHead className="w-[80px] text-center">序号</TableHead>
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
					<TableRow
						key={row.id}
						className={row.isActive ? undefined : "opacity-80"}
					>
						<TableCell>
							<Checkbox
								checked={selectedProjectIds.has(row.id)}
								onCheckedChange={(checked) =>
									onToggleProjectSelection(row.id, Boolean(checked))
								}
								aria-label={`选择项目 ${row.name}`}
							/>
						</TableCell>
						<TableCell className="text-muted-foreground text-center">
							{row.rowNumber}
						</TableCell>
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
							<Badge className={row.statusClassName}>{row.statusLabel}</Badge>
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
						<TableCell className="text-amber-300 font-semibold">
							{row.totalIssues}
						</TableCell>
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
								<Button
									size="sm"
									variant="outline"
									aria-label={`切换项目状态 ${row.name}`}
									className={
										row.statusToggle.action === "disable"
											? "cyber-btn-ghost h-8 px-3 hover:bg-rose-500/10 hover:text-rose-400 hover:border-rose-500/30"
											: "cyber-btn-ghost h-8 px-3 hover:bg-emerald-500/10 hover:text-emerald-400 hover:border-emerald-500/30"
									}
									onClick={() =>
										onToggleProjectStatus(row.id, row.statusToggle.action)
									}
									disabled={row.statusToggle.disabled}
								>
									{row.statusToggle.label}
								</Button>
							</div>
						</TableCell>
					</TableRow>
				))}
			</TableBody>
		</Table>
	);
}
