import { Link } from "react-router-dom";
import { AlertCircle, Loader2 } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import {
  appendReturnTo,
  buildFindingDetailPath,
} from "@/shared/utils/findingRoute";
import type { FindingStatus, UnifiedFindingRow } from "./viewModel";
import {
  getStaticAnalysisConfidenceBadgeClass,
  getStaticAnalysisConfidenceLabel,
  getStaticAnalysisSeverityBadgeClass,
  getStaticAnalysisSeverityLabel,
} from "./viewModel";

const YES_BADGE_CLASS = "bg-emerald-500/20 text-emerald-300 border-emerald-500/30";
const NO_BADGE_CLASS = "bg-muted text-muted-foreground border-border";

export default function StaticAnalysisFindingsTable({
  currentRoute,
  loadingInitial,
  pagedRows,
  pageStart,
  totalRows,
  totalPages,
  clampedPage,
  updatingKey,
  onToggleStatus,
  onPageChange,
}: {
  currentRoute: string;
  loadingInitial: boolean;
  pagedRows: UnifiedFindingRow[];
  pageStart: number;
  totalRows: number;
  totalPages: number;
  clampedPage: number;
  updatingKey: string | null;
  onToggleStatus: (row: UnifiedFindingRow, target: FindingStatus) => void;
  onPageChange: (page: number) => void;
}) {
  return (
    <>
      <div className="border border-border rounded-md overflow-x-auto">
        <Table className="min-w-[1400px]">
          <TableHeader>
            <TableRow>
              <TableHead className="w-[72px]">序号</TableHead>
              <TableHead className="w-[110px]">所属引擎</TableHead>
              <TableHead className="min-w-[220px]">命中规则</TableHead>
              <TableHead className="min-w-[240px]">命中位置</TableHead>
              <TableHead className="w-[120px]">漏洞危害</TableHead>
              <TableHead className="w-[110px]">置信度</TableHead>
              <TableHead className="w-[220px]">处理状态</TableHead>
              <TableHead className="min-w-[280px]">操作</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {loadingInitial ? (
              <TableRow>
                <TableCell colSpan={8} className="py-12 text-center">
                  <div className="inline-flex items-center gap-2 text-sm text-muted-foreground">
                    <Loader2 className="w-4 h-4 animate-spin" />
                    加载扫描数据中...
                  </div>
                </TableCell>
              </TableRow>
            ) : pagedRows.length === 0 ? (
              <TableRow>
                <TableCell colSpan={8} className="py-12 text-center">
                  <div className="inline-flex items-center gap-2 text-sm text-muted-foreground">
                    <AlertCircle className="w-4 h-4" />
                    暂无符合条件的漏洞
                  </div>
                </TableCell>
              </TableRow>
            ) : (
              pagedRows.map((row, index) => {
                const rowStatus = String(row.status || "open").toLowerCase();
                const processed = rowStatus !== "open";
                const verified = rowStatus === "verified";
                const falsePositive = rowStatus === "false_positive";
                const isOpengrep = row.engine === "opengrep";
                const verifyUpdating = updatingKey === `${row.engine}:${row.id}:verified`;
                const falsePositiveUpdating =
                  updatingKey === `${row.engine}:${row.id}:false_positive`;
                const fixedUpdating = updatingKey === `${row.engine}:${row.id}:fixed`;

                const detailRoute = appendReturnTo(
                  buildFindingDetailPath({
                    source: "static",
                    taskId: row.taskId,
                    findingId: row.id,
                    engine: row.engine,
                  }),
                  currentRoute,
                );

                return (
                  <TableRow key={row.key}>
                    <TableCell className="font-mono text-xs">
                      {(pageStart + index + 1).toLocaleString()}
                    </TableCell>
                    <TableCell>
                      <Badge
                        className={
                          row.engine === "opengrep"
                            ? "bg-sky-500/20 text-sky-300 border-sky-500/30"
                            : row.engine === "gitleaks"
                              ? "bg-amber-500/20 text-amber-300 border-amber-500/30"
                              : row.engine === "bandit"
                                ? "bg-emerald-500/20 text-emerald-300 border-emerald-500/30"
                                : "bg-violet-500/20 text-violet-300 border-violet-500/30"
                        }
                      >
                        {row.engine === "opengrep"
                          ? "Opengrep"
                          : row.engine === "gitleaks"
                            ? "Gitleaks"
                            : row.engine === "bandit"
                              ? "Bandit"
                              : "PHPStan"}
                      </Badge>
                    </TableCell>
                    <TableCell className="text-sm break-all">
                      {row.rule || "-"}
                    </TableCell>
                    <TableCell className="font-mono text-xs break-all">
                      {row.filePath}
                      {row.line ? `:${row.line}` : ""}
                    </TableCell>
                    <TableCell>
                      <Badge
                        className={getStaticAnalysisSeverityBadgeClass(row.severity)}
                      >
                        {getStaticAnalysisSeverityLabel(row.severity)}
                      </Badge>
                    </TableCell>
                    <TableCell>
                      <Badge
                        className={getStaticAnalysisConfidenceBadgeClass(row.confidence)}
                      >
                        {getStaticAnalysisConfidenceLabel(row.confidence)}
                      </Badge>
                    </TableCell>
                    <TableCell>
                      <div className="flex items-center gap-1.5 flex-nowrap whitespace-nowrap">
                        <Badge className={processed ? YES_BADGE_CLASS : NO_BADGE_CLASS}>
                          处理：{processed ? "是" : "否"}
                        </Badge>
                        <Badge className={verified ? YES_BADGE_CLASS : NO_BADGE_CLASS}>
                          验证：{verified ? "是" : "否"}
                        </Badge>
                        <Badge
                          className={falsePositive ? YES_BADGE_CLASS : NO_BADGE_CLASS}
                        >
                          误报：{falsePositive ? "是" : "否"}
                        </Badge>
                      </div>
                    </TableCell>
                    <TableCell>
                      <div className="flex items-center gap-1.5 flex-wrap">
                        <Button
                          asChild
                          size="sm"
                          variant="outline"
                          className="cyber-btn-outline h-7 px-2.5"
                        >
                          <Link to={detailRoute}>详情</Link>
                        </Button>
                        <Button
                          size="sm"
                          variant="outline"
                          className="cyber-btn-outline h-7 px-2.5 border-emerald-500/40 text-emerald-500 hover:bg-emerald-500/10"
                          disabled={Boolean(updatingKey)}
                          onClick={() => onToggleStatus(row, "verified")}
                        >
                          {verifyUpdating ? (
                            <Loader2 className="w-3 h-3 animate-spin" />
                          ) : rowStatus === "verified" ? (
                            "取消验证"
                          ) : (
                            "验证"
                          )}
                        </Button>
                        <Button
                          size="sm"
                          variant="outline"
                          className="cyber-btn-outline h-7 px-2.5 border-amber-500/40 text-amber-500 hover:bg-amber-500/10"
                          disabled={Boolean(updatingKey)}
                          onClick={() => onToggleStatus(row, "false_positive")}
                        >
                          {falsePositiveUpdating ? (
                            <Loader2 className="w-3 h-3 animate-spin" />
                          ) : rowStatus === "false_positive" ? (
                            "取消误报"
                          ) : (
                            "误报"
                          )}
                        </Button>
                        {isOpengrep ? null : (
                          <Button
                            size="sm"
                            variant="outline"
                            className="cyber-btn-outline h-7 px-2.5 border-emerald-500/40 text-emerald-500 hover:bg-emerald-500/10"
                            disabled={Boolean(updatingKey)}
                            onClick={() => onToggleStatus(row, "fixed")}
                          >
                            {fixedUpdating ? (
                              <Loader2 className="w-3 h-3 animate-spin" />
                            ) : rowStatus === "fixed" ? (
                              "取消修复"
                            ) : (
                              "修复"
                            )}
                          </Button>
                        )}
                      </div>
                    </TableCell>
                  </TableRow>
                );
              })
            )}
          </TableBody>
        </Table>
      </div>

      <div className="flex items-center justify-between gap-2 flex-wrap">
        <div className="text-xs text-muted-foreground">
          共 {totalRows.toLocaleString()} 条，当前显示 {pagedRows.length.toLocaleString()} 条
        </div>
        <div className="flex items-center gap-2">
          <Button
            size="sm"
            variant="outline"
            className="cyber-btn-outline h-8"
            onClick={() => onPageChange(Math.max(1, clampedPage - 1))}
            disabled={clampedPage <= 1}
          >
            上一页
          </Button>
          <Button
            size="sm"
            variant="outline"
            className="cyber-btn-outline h-8"
            onClick={() => onPageChange(Math.min(totalPages, clampedPage + 1))}
            disabled={clampedPage >= totalPages}
          >
            下一页
          </Button>
        </div>
      </div>
    </>
  );
}
