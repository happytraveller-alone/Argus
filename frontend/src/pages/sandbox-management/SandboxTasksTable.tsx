import { Link } from "react-router-dom";
import { Button } from "@/components/ui/button";
import { DataTable, type AppColumnDef } from "@/components/data-table";
import type { CubeSandboxTaskRecord } from "@/shared/api/cubesandboxTasks";

function formatTaskTime(value: string | null | undefined) {
  if (!value) return "-";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleString("zh-CN", {
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  });
}

function taskEngineLabel(task: CubeSandboxTaskRecord) {
  const engine = String(task.metadata?.engine || "").toLowerCase();
  if (engine === "opengrep") return "OpenGrep";
  if (engine === "codeql") return "CodeQL";
  return "-";
}

function taskProjectName(task: CubeSandboxTaskRecord) {
  return String(task.metadata?.projectName || task.metadata?.projectId || "-");
}

function taskDetailPath(task: CubeSandboxTaskRecord) {
  const explicit = typeof task.metadata?.detailPath === "string" ? task.metadata.detailPath : "";
  if (explicit) return explicit;
  const engine = String(task.metadata?.engine || "").toLowerCase();
  if (engine === "codeql") return `/codeql-analysis/${task.taskId}?codeqlTaskId=${task.taskId}&engine=codeql`;
  if (engine === "opengrep") return `/static-analysis/${task.taskId}?opengrepTaskId=${task.taskId}`;
  return "";
}

const columns: AppColumnDef<CubeSandboxTaskRecord, unknown>[] = [
  {
    id: "taskId",
    accessorFn: (row) => row.taskId,
    header: "任务 ID",
    meta: { label: "任务 ID", align: "left", minWidth: 220 },
    cell: ({ row }) => <span className="font-mono text-muted-foreground">{row.original.taskId}</span>,
  },
  {
    id: "engine",
    accessorFn: (row) => taskEngineLabel(row),
    header: "类型",
    meta: { label: "类型", align: "left", width: 110 },
    cell: ({ row }) => taskEngineLabel(row.original),
  },
  {
    id: "project",
    accessorFn: (row) => taskProjectName(row),
    header: "项目",
    meta: { label: "项目", align: "left", minWidth: 160 },
    cell: ({ row }) => <span className="text-muted-foreground">{taskProjectName(row.original)}</span>,
  },
  {
    id: "status",
    accessorFn: (row) => row.status,
    header: "状态",
    meta: { label: "状态", align: "left", width: 130 },
    cell: ({ row }) => row.original.status,
  },
  {
    id: "sandboxId",
    accessorFn: (row) => row.sandboxId ?? "-",
    header: "Sandbox ID",
    meta: { label: "Sandbox ID", align: "left", minWidth: 180 },
    cell: ({ row }) => <span className="font-mono text-muted-foreground">{row.original.sandboxId ?? "-"}</span>,
  },
  {
    id: "cleanupStatus",
    accessorFn: (row) => row.cleanupStatus,
    header: "清理状态",
    meta: { label: "清理状态", align: "left", width: 130 },
    cell: ({ row }) => <span className="text-muted-foreground">{row.original.cleanupStatus}</span>,
  },
  {
    id: "task",
    header: "任务",
    enableSorting: false,
    meta: { label: "任务", align: "center", width: 120 },
    cell: ({ row }) => {
      const detailPath = taskDetailPath(row.original);
      return detailPath ? (
        <Button asChild size="sm" variant="outline">
          <Link to={detailPath}>查看任务</Link>
        </Button>
      ) : (
        <span className="text-muted-foreground">-</span>
      );
    },
  },
  {
    id: "updatedAt",
    accessorFn: (row) => row.updatedAt,
    header: "更新时间",
    meta: { label: "更新时间", align: "left", minWidth: 140 },
    cell: ({ row }) => <span className="text-muted-foreground">{formatTaskTime(row.original.updatedAt)}</span>,
  },
];

export default function SandboxTasksTable({ rows }: { rows: CubeSandboxTaskRecord[] }) {
  return (
    <DataTable
      data={rows}
      columns={columns}
      toolbar={false}
      pagination={false}
      className="overflow-hidden rounded-xl border border-border/75"
      tableContainerClassName="border-0 rounded-none"
      fillContainerWidth
      emptyState={{ title: "暂无运行中沙箱或任务状态" }}
    />
  );
}
