/**
 * PHPStan Rules Management Page
 *
 * 用途：在不改变现有页面布局的前提下，展示 PHPStan 规则并提供启停状态管理。
 * 说明：此处启停仅影响规则页展示状态，不影响 PHPStan 扫描执行命令。
 */

import { useEffect, useMemo, useState } from "react";
import { toast } from "sonner";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import {
  AlertCircle,
  AlertTriangle,
  ChevronLeft,
  ChevronRight,
  Database,
  Search,
  Shield,
} from "lucide-react";
import {
  batchUpdatePhpstanRulesEnabled,
  getPhpstanRules,
  updatePhpstanRuleEnabled,
  type PhpstanRule,
} from "@/shared/api/phpstan";

type EngineTab = "opengrep" | "gitleaks" | "bandit" | "phpstan";

interface PhpstanRulesProps {
  showEngineSelector?: boolean;
  engineValue?: EngineTab;
  onEngineChange?: (value: EngineTab) => void;
}

const SOURCE_LABEL_MAP: Record<string, string> = {
  official_extension: "官方扩展",
};

const getSourceLabel = (source?: string) => {
  if (!source) return "未知来源";
  return SOURCE_LABEL_MAP[source] ?? source;
};

export default function PhpstanRules({
  showEngineSelector = false,
  engineValue = "phpstan",
  onEngineChange,
}: PhpstanRulesProps) {
  const [rules, setRules] = useState<PhpstanRule[]>([]);
  const [loading, setLoading] = useState(true);
  const [searchTerm, setSearchTerm] = useState("");
  const [selectedSource, setSelectedSource] = useState("");
  const [selectedActiveStatus, setSelectedActiveStatus] = useState("");
  const [selectedRuleIds, setSelectedRuleIds] = useState<Set<string>>(new Set());
  const [batchOperating, setBatchOperating] = useState(false);
  const [currentPage, setCurrentPage] = useState(1);
  const [pageSize, setPageSize] = useState(10);

  const loadRules = async () => {
    try {
      setLoading(true);
      const data = await getPhpstanRules({ limit: 2000 });
      setRules(data);
    } catch (error) {
      console.error("Failed to load phpstan rules:", error);
      toast.error("加载 PHPStan 规则失败");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    void loadRules();
  }, []);

  const stats = useMemo(() => {
    const active = rules.filter((rule) => rule.is_active).length;
    const sources = new Set(rules.map((rule) => rule.source).filter(Boolean));
    const packages = new Set(rules.map((rule) => rule.package).filter(Boolean));
    return {
      total: rules.length,
      active,
      inactive: Math.max(rules.length - active, 0),
      sourceCount: sources.size,
      packageCount: packages.size,
    };
  }, [rules]);

  const sourceOptions = useMemo(
    () => Array.from(new Set(rules.map((rule) => rule.source).filter(Boolean))).sort(),
    [rules],
  );

  const filteredRules = useMemo(
    () =>
      rules.filter((rule) => {
        const keyword = searchTerm.trim().toLowerCase();
        const matchSearch =
          !keyword ||
          rule.name.toLowerCase().includes(keyword) ||
          rule.rule_class.toLowerCase().includes(keyword) ||
          rule.description_summary.toLowerCase().includes(keyword) ||
          rule.package.toLowerCase().includes(keyword) ||
          rule.id.toLowerCase().includes(keyword);

        const matchSource = !selectedSource || rule.source === selectedSource;
        const matchStatus =
          !selectedActiveStatus ||
          (selectedActiveStatus === "true" && rule.is_active) ||
          (selectedActiveStatus === "false" && !rule.is_active);

        return matchSearch && matchSource && matchStatus;
      }),
    [rules, searchTerm, selectedSource, selectedActiveStatus],
  );

  const totalPages = Math.max(1, Math.ceil(filteredRules.length / pageSize));
  const paginatedRules = filteredRules.slice(
    (currentPage - 1) * pageSize,
    currentPage * pageSize,
  );

  const handleToggleRule = async (rule: PhpstanRule) => {
    try {
      await updatePhpstanRuleEnabled({
        ruleId: rule.id,
        is_active: !rule.is_active,
      });
      await loadRules();
      toast.success(`规则已${rule.is_active ? "禁用" : "启用"}`);
    } catch (error: any) {
      toast.error(error?.response?.data?.detail || "更新规则失败");
    }
  };

  const handleToggleRuleSelection = (ruleId: string) => {
    const next = new Set(selectedRuleIds);
    if (next.has(ruleId)) next.delete(ruleId);
    else next.add(ruleId);
    setSelectedRuleIds(next);
  };

  const handleToggleAllSelection = () => {
    if (selectedRuleIds.size === paginatedRules.length) {
      setSelectedRuleIds(new Set());
    } else {
      setSelectedRuleIds(new Set(paginatedRules.map((rule) => rule.id)));
    }
  };

  const handleBatchUpdate = async (isActive: boolean) => {
    try {
      setBatchOperating(true);
      const payload =
        selectedRuleIds.size > 0
          ? {
              rule_ids: Array.from(selectedRuleIds),
              is_active: isActive,
            }
          : {
              source: selectedSource || undefined,
              keyword: searchTerm.trim() || undefined,
              current_is_active:
                selectedActiveStatus === ""
                  ? undefined
                  : selectedActiveStatus === "true",
              is_active: isActive,
            };
      const result = await batchUpdatePhpstanRulesEnabled(payload);
      toast.success(result.message);
      setSelectedRuleIds(new Set());
      await loadRules();
    } catch (error: any) {
      toast.error(error?.response?.data?.detail || "批量操作失败");
    } finally {
      setBatchOperating(false);
    }
  };

  return (
    <div className="space-y-6 p-4 md:p-6">
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4 relative z-10">
        <div className="cyber-card p-4">
          <div className="flex items-center justify-between">
            <div>
              <p className="stat-label">有效规则总数</p>
              <div className="flex items-end gap-3">
                <p className="stat-value">{stats.total}</p>
                <p className="text-sm mb-1 flex items-center gap-3">
                  <span className="inline-flex items-center gap-1 text-emerald-400">
                    <span className="w-2 h-2 rounded-full bg-emerald-400" />
                    已启用 {stats.active}
                  </span>
                </p>
              </div>
            </div>
            <div className="stat-icon text-primary">
              <Database className="w-6 h-6" />
            </div>
          </div>
        </div>
        <div className="cyber-card p-4">
          <div className="flex items-center justify-between">
            <div>
              <p className="stat-label">规则来源数量</p>
              <p className="stat-value">{stats.sourceCount}</p>
            </div>
            <div className="stat-icon text-indigo-400">
              <AlertTriangle className="w-6 h-6" />
            </div>
          </div>
        </div>
        <div className="cyber-card p-4">
          <div className="flex items-center justify-between">
            <div>
              <p className="stat-label">扩展包数量</p>
              <p className="stat-value">{stats.packageCount}</p>
            </div>
            <div className="stat-icon text-cyan-400">
              <Shield className="w-6 h-6" />
            </div>
          </div>
        </div>
      </div>

      <div className="cyber-card relative z-10 overflow-hidden">
        <div className="p-4">
          <div className="flex flex-wrap items-end gap-3">
            <div className="relative w-full max-w-sm shrink-0">
              <Label className="font-mono font-bold uppercase text-xs text-muted-foreground">
                搜索规则
              </Label>
              <div className="relative mt-1.5">
                <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground" />
                <Input
                  value={searchTerm}
                  onChange={(e) => setSearchTerm(e.target.value)}
                  placeholder="搜索名称/类名/包名..."
                  className="cyber-input !pl-10 h-10"
                />
              </div>
            </div>

            <div className="flex flex-1 flex-wrap items-end gap-3">
              {showEngineSelector ? (
                <div className="min-w-[150px] flex-1">
                  <Label className="font-mono font-bold uppercase text-xs text-muted-foreground">
                    扫描引擎
                  </Label>
                  <Select
                    value={engineValue}
                    onValueChange={(val) => {
                      if (
                        val === "opengrep" ||
                        val === "gitleaks" ||
                        val === "bandit" ||
                        val === "phpstan"
                      ) {
                        onEngineChange?.(val);
                      }
                    }}
                  >
                    <SelectTrigger className="cyber-input h-10 mt-1.5">
                      <SelectValue placeholder="选择引擎" />
                    </SelectTrigger>
                    <SelectContent className="cyber-dialog border-border">
                      <SelectItem value="opengrep">opengrep</SelectItem>
                      <SelectItem value="gitleaks">gitleaks</SelectItem>
                      <SelectItem value="bandit">bandit</SelectItem>
                      <SelectItem value="phpstan">phpstan</SelectItem>
                    </SelectContent>
                  </Select>
                </div>
              ) : null}

              <div className="min-w-[150px] flex-1">
                <Label className="font-mono font-bold uppercase text-xs text-muted-foreground">
                  规则来源
                </Label>
                <Select
                  value={selectedSource || "all"}
                  onValueChange={(val) => setSelectedSource(val === "all" ? "" : val)}
                >
                  <SelectTrigger className="cyber-input h-10 mt-1.5">
                    <SelectValue placeholder="所有来源" />
                  </SelectTrigger>
                  <SelectContent className="cyber-dialog border-border">
                    <SelectItem value="all">所有来源</SelectItem>
                    {sourceOptions.map((source) => (
                      <SelectItem key={source} value={source}>
                        {getSourceLabel(source)}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>

              <div className="min-w-[150px] flex-1">
                <Label className="font-mono font-bold uppercase text-xs text-muted-foreground">
                  启用状态
                </Label>
                <Select
                  value={selectedActiveStatus || "all"}
                  onValueChange={(val) => setSelectedActiveStatus(val === "all" ? "" : val)}
                >
                  <SelectTrigger className="cyber-input h-10 mt-1.5">
                    <SelectValue placeholder="所有状态" />
                  </SelectTrigger>
                  <SelectContent className="cyber-dialog border-border">
                    <SelectItem value="all">所有状态</SelectItem>
                    <SelectItem value="true">已启用</SelectItem>
                    <SelectItem value="false">已禁用</SelectItem>
                  </SelectContent>
                </Select>
              </div>

              <div className="ml-auto flex items-end gap-2">
                <Button
                  className="cyber-btn-outline h-10 min-w-[96px]"
                  onClick={() => {
                    setSearchTerm("");
                    setSelectedSource("");
                    setSelectedActiveStatus("");
                    setCurrentPage(1);
                    setSelectedRuleIds(new Set());
                  }}
                >
                  重置
                </Button>
              </div>
            </div>
          </div>
        </div>

        {filteredRules.length > 0 ? (
          <div className="border-t border-primary/20 bg-primary/5 px-4 py-4">
            <div className="flex flex-wrap items-center justify-between gap-4">
              <p className="font-mono text-sm">
                {selectedRuleIds.size > 0 ? (
                  <>
                    已选择 <span className="font-bold text-primary">{selectedRuleIds.size}</span> 条规则
                  </>
                ) : (
                  <>
                    将对 <span className="font-bold text-primary">{filteredRules.length}</span> 条规则进行操作
                  </>
                )}
              </p>
              <div className="flex flex-wrap gap-2">
                <Button onClick={() => void handleBatchUpdate(true)} disabled={batchOperating} className="cyber-btn-primary h-9 text-sm">
                  {batchOperating ? "处理中..." : "批量启用"}
                </Button>
                <Button onClick={() => void handleBatchUpdate(false)} disabled={batchOperating} className="cyber-btn-outline h-9 text-sm">
                  {batchOperating ? "处理中..." : "批量禁用"}
                </Button>
              </div>
            </div>
          </div>
        ) : null}

        <div className="border-t border-border/60">
          {loading ? (
            <div className="p-16 text-center text-muted-foreground">加载中...</div>
          ) : filteredRules.length === 0 ? (
            <div className="p-16 text-center">
              <AlertCircle className="w-12 h-12 text-muted-foreground mx-auto mb-4" />
              <h3 className="text-lg font-bold text-foreground mb-2">未找到规则</h3>
              <p className="text-muted-foreground font-mono text-sm">
                {searchTerm || selectedSource || selectedActiveStatus
                  ? "调整筛选条件尝试"
                  : "暂无规则数据（请先生成并导入 phpstan 规则快照）"}
              </p>
            </div>
          ) : (
            <>
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead className="w-[52px]">
                      <Checkbox
                        checked={selectedRuleIds.size === paginatedRules.length && paginatedRules.length > 0}
                        onCheckedChange={handleToggleAllSelection}
                        className="w-4 h-4"
                      />
                    </TableHead>
                    <TableHead className="w-[72px] text-center">序号</TableHead>
                    <TableHead className="min-w-[320px]">规则</TableHead>
                    <TableHead className="min-w-[180px]">扩展包</TableHead>
                    <TableHead className="w-[120px]">来源</TableHead>
                    <TableHead className="w-[110px]">启用状态</TableHead>
                    <TableHead className="w-[160px]">更新时间</TableHead>
                    <TableHead className="min-w-[180px]">操作</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {paginatedRules.map((rule, index) => (
                    <TableRow key={rule.id}>
                      <TableCell>
                        <Checkbox
                          checked={selectedRuleIds.has(rule.id)}
                          onCheckedChange={() => handleToggleRuleSelection(rule.id)}
                          className="w-4 h-4"
                        />
                      </TableCell>
                      <TableCell className="text-center text-muted-foreground">
                        {(currentPage - 1) * pageSize + index + 1}
                      </TableCell>
                      <TableCell>
                        <div className="space-y-0.5">
                          <div className="font-semibold text-foreground break-all">{rule.name}</div>
                          <div className="font-mono text-xs text-muted-foreground break-all">{rule.rule_class}</div>
                          {rule.description_summary ? (
                            <div className="text-xs text-muted-foreground break-all line-clamp-2">
                              {rule.description_summary}
                            </div>
                          ) : null}
                        </div>
                      </TableCell>
                      <TableCell className="text-sm text-muted-foreground break-all">
                        {rule.package || "-"}
                      </TableCell>
                      <TableCell>
                        <Badge className="cyber-badge cyber-badge-info">
                          {getSourceLabel(rule.source)}
                        </Badge>
                      </TableCell>
                      <TableCell>
                        <Badge className={rule.is_active ? "cyber-badge cyber-badge-success" : "cyber-badge cyber-badge-muted"}>
                          {rule.is_active ? "已启用" : "已禁用"}
                        </Badge>
                      </TableCell>
                      <TableCell className="text-xs text-muted-foreground">
                        {rule.updated_at ? new Date(rule.updated_at).toLocaleString() : "-"}
                      </TableCell>
                      <TableCell>
                        <Button
                          onClick={() => void handleToggleRule(rule)}
                          className={rule.is_active ? "cyber-btn-outline h-8 text-xs" : "cyber-btn-primary h-8 text-xs"}
                        >
                          {rule.is_active ? "禁用" : "启用"}
                        </Button>
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>

              <div className="flex flex-wrap items-center justify-between gap-3 p-4 border-t border-border/60">
                <div className="text-sm text-muted-foreground">
                  共 {filteredRules.length} 条，当前第 {currentPage} / {totalPages} 页
                </div>
                <div className="flex items-center gap-2">
                  <Select
                    value={String(pageSize)}
                    onValueChange={(value) => {
                      setPageSize(Number(value));
                      setCurrentPage(1);
                    }}
                  >
                    <SelectTrigger className="cyber-input h-9 w-[110px]">
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent className="cyber-dialog border-border">
                      <SelectItem value="10">10 / 页</SelectItem>
                      <SelectItem value="20">20 / 页</SelectItem>
                      <SelectItem value="50">50 / 页</SelectItem>
                    </SelectContent>
                  </Select>

                  <Button
                    className="cyber-btn-outline h-9 px-3"
                    disabled={currentPage <= 1}
                    onClick={() => setCurrentPage((prev) => Math.max(1, prev - 1))}
                  >
                    <ChevronLeft className="w-4 h-4" />
                  </Button>
                  <Button
                    className="cyber-btn-outline h-9 px-3"
                    disabled={currentPage >= totalPages}
                    onClick={() => setCurrentPage((prev) => Math.min(totalPages, prev + 1))}
                  >
                    <ChevronRight className="w-4 h-4" />
                  </Button>
                </div>
              </div>
            </>
          )}
        </div>
      </div>
    </div>
  );
}
