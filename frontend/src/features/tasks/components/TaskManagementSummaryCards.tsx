import { DataTable, type AppColumnDef } from "@/components/data-table";

interface TaskManagementSummaryCardsProps {
	taskLabel: string;
	total: number;
	completed: number;
	running: number;
}

type TaskSummaryCardRow = {
	label: string;
	value: number;
	valueClassName: string;
};

const TASK_SUMMARY_GRID_CLASSNAME =
	"relative z-10 grid shrink-0 grid-cols-1 gap-3 sm:grid-cols-3";
const TASK_SUMMARY_CARD_CLASSNAME =
	"rounded-sm border border-border bg-card text-card-foreground shadow-sm flex items-center justify-between gap-3 px-3 py-3";
const TASK_SUMMARY_LABEL_CLASSNAME =
	"text-sm uppercase tracking-[0.12em] text-muted-foreground";
const TASK_SUMMARY_VALUE_CLASSNAME =
	"text-right text-xl font-semibold tabular-nums text-foreground";

const TASK_SUMMARY_COLUMNS: AppColumnDef<TaskSummaryCardRow, unknown>[] = [
	{
		accessorKey: "label",
		header: "指标",
		meta: { label: "指标" },
	},
	{
		accessorKey: "value",
		header: "数值",
		meta: { label: "数值" },
	},
];

export default function TaskManagementSummaryCards({
	taskLabel,
	total,
	completed,
	running,
}: TaskManagementSummaryCardsProps) {
	const cards: TaskSummaryCardRow[] = [
		{ label: taskLabel, value: total, valueClassName: "" },
		{ label: "已完成", value: completed, valueClassName: "text-emerald-400" },
		{ label: "进行中", value: running, valueClassName: "text-sky-400" },
	];

	return (
		<DataTable
			data={cards}
			columns={TASK_SUMMARY_COLUMNS}
			toolbar={false}
			pagination={false}
			className="border-0 bg-transparent shadow-none"
			renderMode={({ rows }) => (
				<div className={TASK_SUMMARY_GRID_CLASSNAME}>
					{rows.map((item) => (
						<div key={item.label} className={TASK_SUMMARY_CARD_CLASSNAME}>
							<div className={TASK_SUMMARY_LABEL_CLASSNAME}>{item.label}</div>
							<div
								className={`${TASK_SUMMARY_VALUE_CLASSNAME} ${item.valueClassName}`}
							>
								{item.value}
							</div>
						</div>
					))}
				</div>
			)}
		/>
	);
}
