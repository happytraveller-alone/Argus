import { useEffect, useMemo, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { Search } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { api, type SkillCatalogItemPayload } from "@/shared/api/database";
import { SKILL_TOOLS_CATALOG } from "./skillToolsCatalog";
import {
  buildExternalToolListState,
  buildExternalToolRows,
} from "./externalToolsViewModel";
import {
  resolveAnchoredExternalToolsPage,
  resolveExternalToolsFirstVisibleIndex,
  resolveResponsiveExternalToolsLayout,
} from "./externalToolsResponsiveLayout";

export interface SkillToolsPanelProps {
  initialSkillCatalog?: SkillCatalogItemPayload[];
}

export default function SkillToolsPanel({
  initialSkillCatalog = [],
}: SkillToolsPanelProps) {
  const [skillCatalog, setSkillCatalog] =
    useState<SkillCatalogItemPayload[]>(initialSkillCatalog);
  const [searchQuery, setSearchQuery] = useState("");
  const [page, setPage] = useState(1);
  const tableViewportRef = useRef<HTMLDivElement | null>(null);
  const pageSizeRef = useRef(6);
  const [pageSize, setPageSize] = useState(6);

  useEffect(() => {
    let cancelled = false;

    void api
      .getSkillCatalog({
        namespace: "scan-core",
        limit: 200,
      })
      .then((items) => {
        if (cancelled || items.length === 0) {
          return;
        }
        setSkillCatalog(items);
      })
      .catch(() => {
        // Keep initial data when the catalog request fails.
      });

    return () => {
      cancelled = true;
    };
  }, []);

  const rows = useMemo(
    () =>
      buildExternalToolRows({
        skillCatalog,
        staticSkillCatalog: SKILL_TOOLS_CATALOG,
      }),
    [skillCatalog],
  );

  const listState = useMemo(
    () =>
      buildExternalToolListState({
        rows,
        searchQuery,
        page,
        pageSize,
      }),
    [page, pageSize, rows, searchQuery],
  );

  useEffect(() => {
    if (page !== listState.page) {
      setPage(listState.page);
    }
  }, [listState.page, page]);

  useEffect(() => {
    if (!tableViewportRef.current) {
      return;
    }

    const viewportNode = tableViewportRef.current;
    const updateLayout = () => {
      const { width, height } = viewportNode.getBoundingClientRect();
      const nextLayout = resolveResponsiveExternalToolsLayout({
        width,
        height,
        minCardHeight: 72,
      });
      setPageSize((current) =>
        current === nextLayout.pageSize ? current : nextLayout.pageSize,
      );
    };

    updateLayout();
    const observer =
      typeof ResizeObserver === "undefined"
        ? null
        : new ResizeObserver(() => {
            updateLayout();
          });
    observer?.observe(viewportNode);
    window.addEventListener("resize", updateLayout);
    window.visualViewport?.addEventListener("resize", updateLayout);

    return () => {
      observer?.disconnect();
      window.removeEventListener("resize", updateLayout);
      window.visualViewport?.removeEventListener("resize", updateLayout);
    };
  }, []);

  useEffect(() => {
    setPage((current) => {
      const firstVisibleIndex = resolveExternalToolsFirstVisibleIndex({
        page: current,
        pageSize: pageSizeRef.current,
      });
      const nextPage = resolveAnchoredExternalToolsPage({
        firstVisibleIndex,
        nextPageSize: pageSize,
        totalRows: listState.totalRows,
      });
      return current === nextPage ? current : nextPage;
    });
    pageSizeRef.current = pageSize;
  }, [listState.totalRows, pageSize]);

  return (
    <div className="flex flex-1 flex-col gap-5 min-h-0">
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
            placeholder="搜索工具名称、类型或执行功能..."
            className="cyber-input h-11 border-border/60 bg-background/70"
            wrapperClassName="max-w-full"
            aria-label="搜索工具名称、类型或执行功能"
          />
        </div>
      </div>

      <div ref={tableViewportRef} className="flex flex-1 min-h-[20rem] flex-col">
        <div className="overflow-x-auto rounded-sm border border-border/50 bg-background/20">
          <table className="min-w-[780px] w-full border-collapse">
            <thead>
              <tr className="border-b border-border/50 bg-background/60 text-left">
                <th className="px-4 py-3 text-xs font-mono uppercase tracking-[0.24em] text-muted-foreground">
                  序号
                </th>
                <th className="px-4 py-3 text-xs font-mono uppercase tracking-[0.24em] text-muted-foreground">
                  工具名称
                </th>
                <th className="px-4 py-3 text-xs font-mono uppercase tracking-[0.24em] text-muted-foreground">
                  类型
                </th>
                <th className="px-4 py-3 text-xs font-mono uppercase tracking-[0.24em] text-muted-foreground">
                  执行功能
                </th>
                <th className="px-4 py-3 text-right text-xs font-mono uppercase tracking-[0.24em] text-muted-foreground">
                  操作
                </th>
              </tr>
            </thead>
            <tbody>
              {listState.pageRows.length ? (
                listState.pageRows.map((row, index) => {
                  const order = listState.startIndex + index + 1;
                  return (
                    <tr
                      key={`${row.type}:${row.id}`}
                      className="border-b border-border/30 align-top transition-colors duration-150 hover:bg-background/40"
                    >
                      <td className="px-4 py-4 text-sm font-mono text-muted-foreground">
                        {String(order).padStart(2, "0")}
                      </td>
                      <td className="px-4 py-4">
                        <div className="space-y-1">
                          <div className="text-sm font-semibold text-foreground">
                            {row.name}
                          </div>
                        </div>
                      </td>
                      <td className="px-4 py-4">
                        <Badge variant="outline" className="text-[10px] uppercase">
                          {row.displayType}
                        </Badge>
                      </td>
                      <td className="px-4 py-4">
                        <div
                          className="text-sm leading-6 text-foreground/90 whitespace-nowrap overflow-hidden text-ellipsis"
                          title={row.capabilities.join("; ")}
                        >
                          {row.capabilities.join("; ")}
                        </div>
                      </td>
                      <td className="px-4 py-4 text-right">
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
                      </td>
                    </tr>
                  );
                })
              ) : (
                <tr>
                  <td
                    colSpan={5}
                    className="px-4 py-12 text-center text-sm text-muted-foreground"
                  >
                    未找到匹配的外部工具，尝试更换名称关键词、类型或执行功能描述。
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </div>

      <div className="mt-auto flex flex-wrap items-center justify-between gap-3 border-t border-border/50 pt-4">
        <span className="text-xs font-mono text-muted-foreground">
          当前展示 {listState.pageRows.length} / {listState.totalRows} 条 ·
          每页 {listState.pageSize} 条
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
