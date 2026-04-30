import type { ColumnDef } from "@tanstack/react-table";
import { Badge } from "@/components/ui/badge";

export function createRowNumberColumn<TData>(): ColumnDef<TData> {
	return {
		id: "__rowNumber__",
		header: "序号",
		enableSorting: false,
		enableColumnFilter: false,
		meta: {
			label: "序号",
			align: "center",
			hideable: false,
			width: 72,
		},
		cell: ({ row, table }) => {
			const pageRowIndex = table
				.getRowModel()
				.rows.findIndex((r) => r.id === row.id);
			return (
				table.getState().pagination.pageIndex *
					table.getState().pagination.pageSize +
				pageRowIndex +
				1
			);
		},
	};
}

export function createBadgeColumn<TData>({
	accessorKey,
	header,
	className,
}: {
	accessorKey: string;
	header: string;
	className?: string;
}): ColumnDef<TData> {
	return {
		accessorKey,
		header,
		meta: {
			label: header,
		},
		cell: ({ getValue }) => (
			<Badge className={className}>{String(getValue() ?? "-")}</Badge>
		),
	};
}
