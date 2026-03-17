import { Link } from "react-router-dom";
import { Button } from "@/components/ui/button";
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

const EXECUTION_COLUMNS = [
	{
		key: "completed",
		label: "已完成",
		cellClassName: "text-left",
		chipClassName:
			"border-emerald-500/35 bg-emerald-500/12 text-emerald-200 shadow-[inset_0_1px_0_rgba(52,211,153,0.18)]",
	},
	{
		key: "running",
		label: "进行中",
		cellClassName: "text-left",
		chipClassName:
			"border-sky-500/35 bg-sky-500/12 text-sky-200 shadow-[inset_0_1px_0_rgba(56,189,248,0.18)]",
	},
] as const;

const VULNERABILITY_COLUMNS = [
	{
		key: "critical",
		label: "严重",
		cellClassName: "text-left",
		chipClassName:
			"border-rose-500/35 bg-rose-500/12 text-rose-200 shadow-[inset_0_1px_0_rgba(251,113,133,0.18)]",
	},
	{
		key: "high",
		label: "高危",
		cellClassName: "text-left",
		chipClassName:
			"border-amber-500/35 bg-amber-500/12 text-amber-200 shadow-[inset_0_1px_0_rgba(251,191,36,0.18)]",
	},
	{
		key: "medium",
		label: "中危",
		cellClassName: "text-left",
		chipClassName:
			"border-sky-500/35 bg-sky-500/12 text-sky-200 shadow-[inset_0_1px_0_rgba(56,189,248,0.18)]",
	},
	{
		key: "low",
		label: "低危",
		cellClassName: "text-left",
		chipClassName:
			"border-emerald-500/35 bg-emerald-500/12 text-emerald-200 shadow-[inset_0_1px_0_rgba(52,211,153,0.18)]",
	},
] as const;

const METRIC_CHIP_CLASSNAME =
	"inline-grid grid-cols-[2ch_auto] items-center gap-1 rounded-md border px-2.5 py-1 text-sm leading-none";
const METRIC_CHIP_CLASSNAME_2 =
	"inline-grid grid-cols-[2ch_auto] items-center gap-5 rounded-md border px-2.5 py-1 text-sm leading-none";
const METRIC_CHIP_VALUE_CLASSNAME =
	"text-left font-semibold tabular-nums text-[16px] gap-2";
const METRIC_CHIP_LABEL_CLASSNAME =
	"whitespace-nowrap text-left text-[16px] font-medium tracking-[0.02em]";

export default function ProjectsTable({
	rows,
	onCreateScan,
}: ProjectsTableProps) {
	const formatMetricValue = (
		row: ProjectsPageRowViewModel,
		value: number,
	) => {
		if (row.metricsStatus !== "ready") {
			return "—";
		}
		return value;
	};

	return (
		<Table>
			<TableHeader>
				<TableRow>
					<TableHead className="min-w-[176px]">
						项目名称
					</TableHead>
					<TableHead className="min-w-[132px]">
						项目大小
					</TableHead>
					<TableHead className="text-left" colSpan={2}>
						执行任务
					</TableHead>
					<TableHead className="text-left" colSpan={4}>
						发现漏洞
					</TableHead>
					<TableHead className="min-w-[320px]">
						操作
					</TableHead>
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
						<TableCell className="text-base text-muted-foreground">
							<span title={row.metricsStatusMessage ?? undefined}>
								{row.sizeText}
							</span>
						</TableCell>
						{EXECUTION_COLUMNS.map((column) => (
							<TableCell
								key={`${row.id}-${column.key}`}
								className={column.cellClassName}
							>
								<span
									data-project-metric-chip={column.key}
									className={`${METRIC_CHIP_CLASSNAME} ${column.chipClassName}`}
									title={row.metricsStatus !== "ready"
										? row.metricsStatusMessage ?? undefined
										: undefined}
								>
									<span className={METRIC_CHIP_VALUE_CLASSNAME}>
										{formatMetricValue(
											row,
											row.executionStats[column.key],
										)}
									</span>
									<span className={METRIC_CHIP_LABEL_CLASSNAME}>
										{column.label}
									</span>
								</span>
							</TableCell>
						))}
						{VULNERABILITY_COLUMNS.map((column) => (
							<TableCell
								key={`${row.id}-${column.key}`}
								className={column.cellClassName}
							>
								<span
									data-project-metric-chip={column.key}
									className={`${METRIC_CHIP_CLASSNAME_2} ${column.chipClassName}`}
									title={row.metricsStatus !== "ready"
										? row.metricsStatusMessage ?? undefined
										: undefined}
								>
									<span className={METRIC_CHIP_VALUE_CLASSNAME}>
										{formatMetricValue(
											row,
											row.vulnerabilityStats[column.key],
										)}
									</span>
									<span className={METRIC_CHIP_LABEL_CLASSNAME}> 
										{column.label}
									</span>
								</span>
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
