import type { ColumnDef } from "@tanstack/react-table";
import { Button } from "@/components/ui/button";
import { DataTable, type AppColumnDef } from "@/components/data-table";
import type { CubesandboxTemplateRecord } from "@/shared/api/cubesandboxTemplates";

interface SandboxTemplatesTableProps {
  rows: CubesandboxTemplateRecord[];
  deletingRecordId?: string | null;
  onDeleteFailed: (record: CubesandboxTemplateRecord) => void;
}

const HEADER_CELL_CLASSNAME =
  "border-b-2 border-border/95 bg-muted/75 text-center font-mono text-[14px] font-semibold uppercase tracking-[0.18em] text-foreground/80";
const HEADER_CONTENT_CLASSNAME = "text-[14px]";
const BODY_CELL_CLASSNAME = "border-b-2 border-border/95 text-center";
const DIVIDER_CELL_CLASSNAME = "border-r-2 border-border/90";
const SECTION_DIVIDER_CLASSNAME = "border-l-2 border-border/95";

function shortText(value: string | null | undefined, fallback = "-") {
  if (!value) return fallback;
  return value.length > 72 ? `${value.slice(0, 69)}...` : value;
}

function kindLabel(kind?: string) {
  if (kind === "codeql_cpp") return "CodeQL C/C++";
  if (kind === "opengrep" || kind === "opengrep_dedicated") return "OpenGrep";
  return kind || "未知";
}

function statusClassName(status: string) {
  if (status === "ready") return "border-emerald-500/30 bg-emerald-500/12 text-emerald-100";
  if (status === "failed") return "border-rose-500/35 bg-rose-500/12 text-rose-100";
  if (status === "building" || status === "pending") return "border-amber-500/35 bg-amber-500/12 text-amber-100";
  return "border-slate-400/30 bg-slate-400/12 text-slate-100";
}

function formatDate(value?: string | null) {
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

function buildColumns(
  deletingRecordId: string | null,
  onDeleteFailed: (record: CubesandboxTemplateRecord) => void,
): AppColumnDef<CubesandboxTemplateRecord, unknown>[] {
  return [
    {
      id: "rowNumber",
      header: "序号",
      enableSorting: false,
      meta: {
        label: "序号",
        width: 64,
        headerClassName: `${HEADER_CELL_CLASSNAME} ${DIVIDER_CELL_CLASSNAME}`,
        headerContentClassName: HEADER_CONTENT_CLASSNAME,
        cellClassName: `${BODY_CELL_CLASSNAME} ${DIVIDER_CELL_CLASSNAME}`,
      },
      cell: ({ row, table }) => table.getRowModel().rows.findIndex((r) => r.id === row.id) + 1,
    },
    {
      accessorKey: "kind",
      header: "模板类型",
      meta: {
        label: "模板类型",
        minWidth: 128,
        headerClassName: `${HEADER_CELL_CLASSNAME} ${DIVIDER_CELL_CLASSNAME}`,
        headerContentClassName: HEADER_CONTENT_CLASSNAME,
        cellClassName: `${BODY_CELL_CLASSNAME} ${DIVIDER_CELL_CLASSNAME} text-[15px] font-semibold`,
      },
      cell: ({ row }) => kindLabel(row.original.kind),
    },
    {
      accessorKey: "status",
      header: "记录状态",
      meta: {
        label: "状态",
        minWidth: 120,
        headerClassName: `${HEADER_CELL_CLASSNAME} ${DIVIDER_CELL_CLASSNAME}`,
        headerContentClassName: HEADER_CONTENT_CLASSNAME,
        cellClassName: `${BODY_CELL_CLASSNAME} ${DIVIDER_CELL_CLASSNAME}`,
      },
      cell: ({ row }) => (
        <span className={`inline-flex rounded-full border px-3 py-1 text-xs font-semibold ${statusClassName(row.original.status)}`}>
          {row.original.status}
        </span>
      ),
    },
    {
      accessorKey: "templateId",
      header: "CubeMaster 模板 ID",
      meta: {
        label: "模板 ID",
        minWidth: 190,
        headerClassName: `${HEADER_CELL_CLASSNAME} ${DIVIDER_CELL_CLASSNAME}`,
        headerContentClassName: HEADER_CONTENT_CLASSNAME,
        cellClassName: `${BODY_CELL_CLASSNAME} ${DIVIDER_CELL_CLASSNAME} text-muted-foreground`,
      },
      cell: ({ row }) => <span title={row.original.templateId ?? undefined}>{shortText(row.original.templateId)}</span>,
    },
    {
      accessorKey: "imageRef",
      header: "镜像",
      meta: {
        label: "镜像",
        minWidth: 180,
        headerClassName: `${HEADER_CELL_CLASSNAME} ${DIVIDER_CELL_CLASSNAME}`,
        headerContentClassName: HEADER_CONTENT_CLASSNAME,
        cellClassName: `${BODY_CELL_CLASSNAME} ${DIVIDER_CELL_CLASSNAME} text-muted-foreground`,
      },
      cell: ({ row }) => <span title={row.original.imageRef ?? undefined}>{shortText(row.original.imageRef)}</span>,
    },
    {
      id: "error",
      header: "错误摘要",
      meta: {
        label: "错误摘要",
        minWidth: 180,
        headerClassName: `${HEADER_CELL_CLASSNAME} ${DIVIDER_CELL_CLASSNAME}`,
        headerContentClassName: HEADER_CONTENT_CLASSNAME,
        cellClassName: `${BODY_CELL_CLASSNAME} ${DIVIDER_CELL_CLASSNAME} text-muted-foreground`,
      },
      cell: ({ row }) => <span title={row.original.errorMessage ?? row.original.buildLogTail}>{shortText(row.original.errorMessage ?? row.original.buildLogTail)}</span>,
    },
    {
      accessorKey: "updatedAt",
      header: "更新时间",
      meta: {
        label: "更新时间",
        minWidth: 120,
        headerClassName: `${HEADER_CELL_CLASSNAME} ${DIVIDER_CELL_CLASSNAME}`,
        headerContentClassName: HEADER_CONTENT_CLASSNAME,
        cellClassName: `${BODY_CELL_CLASSNAME} ${DIVIDER_CELL_CLASSNAME} text-muted-foreground`,
      },
      cell: ({ row }) => formatDate(row.original.updatedAt),
    },
    {
      id: "actions",
      header: "操作",
      enableSorting: false,
      meta: {
        label: "操作",
        plainHeader: true,
        minWidth: 154,
        headerClassName: `${HEADER_CELL_CLASSNAME} ${SECTION_DIVIDER_CLASSNAME}`,
        headerContentClassName: HEADER_CONTENT_CLASSNAME,
        cellClassName: `${BODY_CELL_CLASSNAME} ${SECTION_DIVIDER_CLASSNAME}`,
      },
      cell: ({ row }) => {
        const canDelete = row.original.status === "failed";
        const deleting = deletingRecordId === row.original.id;
        return (
          <Button
            size="sm"
            variant="ghost"
            className="h-8 px-2.5 text-rose-200 hover:bg-rose-500/10 hover:text-rose-100"
            disabled={!canDelete || deleting}
            title={canDelete ? "仅删除 FAILED 模板记录/模板" : "仅 FAILED 可删"}
            onClick={() => onDeleteFailed(row.original)}
          >
            {deleting ? "删除中..." : canDelete ? "删除 FAILED" : "仅 FAILED 可删"}
          </Button>
        );
      },
    },
  ];
}

export default function SandboxTemplatesTable({
  rows,
  deletingRecordId = null,
  onDeleteFailed,
}: SandboxTemplatesTableProps) {
  const columns = buildColumns(deletingRecordId, onDeleteFailed) as ColumnDef<CubesandboxTemplateRecord>[];
  return (
    <DataTable
      data={rows}
      columns={columns}
      toolbar={false}
      pagination={false}
      className="overflow-visible"
      containerClassName="overflow-visible"
      tableContainerClassName="overflow-visible border-0 rounded-none"
      fillContainerWidth
      emptyState={{ title: "暂无沙箱模板记录" }}
    />
  );
}
