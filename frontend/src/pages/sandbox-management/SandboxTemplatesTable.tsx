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

function recordCanDelete(status: string) {
  return status === "failed" || status === "invalidated";
}

function templateIdentityTitle(record: CubesandboxTemplateRecord) {
  return `ID: ${record.templateId || "-"}\n镜像: ${record.imageRef || "-"}`;
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
      id: "templateIdentity",
      header: "模板 / 镜像",
      meta: {
        label: "模板 / 镜像",
        minWidth: 260,
        headerClassName: `${HEADER_CELL_CLASSNAME} ${DIVIDER_CELL_CLASSNAME}`,
        headerContentClassName: HEADER_CONTENT_CLASSNAME,
        cellClassName: `${BODY_CELL_CLASSNAME} ${DIVIDER_CELL_CLASSNAME}`,
      },
      cell: ({ row }) => (
        <div className="flex flex-col items-center gap-1.5" title={templateIdentityTitle(row.original)}>
          <span className="inline-flex max-w-[260px] rounded-md border border-sky-400/30 bg-sky-500/10 px-2 py-0.5 font-mono text-[11px] font-semibold text-sky-100">
            <span className="mr-1 text-sky-300/80">ID</span>
            <span className="truncate">{shortText(row.original.templateId, "-")}</span>
          </span>
          <span className="inline-flex max-w-[260px] rounded-md border border-violet-400/30 bg-violet-500/10 px-2 py-0.5 font-mono text-[11px] font-semibold text-violet-100">
            <span className="mr-1 text-violet-300/80">镜像</span>
            <span className="truncate">{shortText(row.original.imageRef, "-")}</span>
          </span>
        </div>
      ),
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
        const canDelete = recordCanDelete(row.original.status);
        const deleting = deletingRecordId === row.original.id;
        return (
          <Button
            size="sm"
            variant="ghost"
            className="h-8 px-2.5 text-rose-200 hover:bg-rose-500/10 hover:text-rose-100"
            disabled={!canDelete || deleting}
            title={canDelete ? "删除 FAILED / INVALIDATED 模板记录/模板" : "仅 FAILED / INVALIDATED 可删"}
            onClick={() => onDeleteFailed(row.original)}
          >
            {deleting ? "删除中..." : canDelete ? "删除" : "不可删"}
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
