interface TaskManagementSummaryCardsProps {
	taskLabel: string;
	total: number;
	completed: number;
	running: number;
}

const TASK_SUMMARY_GRID_CLASSNAME =
	"relative z-10 grid shrink-0 grid-cols-1 gap-3 sm:grid-cols-3";
const TASK_SUMMARY_CARD_CLASSNAME =
	"rounded-sm border border-border bg-card text-card-foreground shadow-sm flex items-center justify-between gap-3 px-3 py-3";
const TASK_SUMMARY_LABEL_CLASSNAME =
	"text-sm uppercase tracking-[0.12em] text-muted-foreground";
const TASK_SUMMARY_VALUE_CLASSNAME =
	"text-right text-xl font-semibold tabular-nums text-foreground";

export default function TaskManagementSummaryCards({
	taskLabel,
	total,
	completed,
	running,
}: TaskManagementSummaryCardsProps) {
	const cards = [
		{ label: taskLabel, value: total, valueClassName: "" },
		{ label: "已完成", value: completed, valueClassName: "text-emerald-400" },
		{ label: "进行中", value: running, valueClassName: "text-sky-400" },
	];

	return (
		<div className={TASK_SUMMARY_GRID_CLASSNAME}>
			{cards.map((item) => (
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
	);
}
