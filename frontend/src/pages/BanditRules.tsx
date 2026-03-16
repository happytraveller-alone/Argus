/**
 * Bandit Rules Management Page
 *
 * 用途：在不改变现有页面布局的前提下，展示 Bandit 内置规则并提供启停/删除管理。
 * 说明：此处启停与删除仅影响规则页展示状态，不影响 Bandit 扫描执行命令。
 */

import { useEffect, useMemo, useState } from "react";
import { toast } from "sonner";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
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
  Code,
  Database,
  Save,
  Search,
  Shield,
} from "lucide-react";
import {
  batchDeleteBanditRules,
  batchRestoreBanditRules,
  batchUpdateBanditRulesEnabled,
  deleteBanditRule,
  getBanditRule,
  getBanditRules,
  restoreBanditRule,
  updateBanditRule,
  updateBanditRuleEnabled,
  type BanditRule,
} from "@/shared/api/bandit";

type EngineTab = "opengrep" | "gitleaks" | "bandit" | "phpstan";

interface BanditRulesProps {
  showEngineSelector?: boolean;
  engineValue?: EngineTab;
  onEngineChange?: (value: EngineTab) => void;
}

const getSourceLabel = () => "内置规则";

export default function BanditRules({
  showEngineSelector = false,
  engineValue = "bandit",
  onEngineChange,
}: BanditRulesProps) {
  const [rules, setRules] = useState<BanditRule[]>([]);
  const [loading, setLoading] = useState(true);
  const [searchTerm, setSearchTerm] = useState("");
  const [selectedSource, setSelectedSource] = useState("");
  const [selectedActiveStatus, setSelectedActiveStatus] = useState("");
  const [selectedDeletedStatus, setSelectedDeletedStatus] = useState<"false" | "true" | "all">("false");
  const [selectedRuleIds, setSelectedRuleIds] = useState<Set<string>>(new Set());
  const [batchOperating, setBatchOperating] = useState(false);
  const [showRuleDetail, setShowRuleDetail] = useState(false);
  const [selectedRule, setSelectedRule] = useState<BanditRule | null>(null);
  const [loadingDetail, setLoadingDetail] = useState(false);
  const [isEditingRule, setIsEditingRule] = useState(false);
  const [savingRule, setSavingRule] = useState(false);
  // Bandit integration: 规则编辑表单仅用于规则页展示态，不影响扫描执行。
  const [editRuleForm, setEditRuleForm] = useState({
    name: "",
    description_summary: "",
    description: "",
    checks_text: "",
  });
  const [currentPage, setCurrentPage] = useState(1);
  const [pageSize, setPageSize] = useState(10);

  const loadRules = async () => {
    try {
      setLoading(true);
      const data = await getBanditRules({
        deleted: selectedDeletedStatus,
        limit: 2000,
      });
      setRules(data);
    } catch (error) {
      console.error("Failed to load bandit rules:", error);
      toast.error("加载 bandit 规则失败");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    void loadRules();
  }, [selectedDeletedStatus]);

  const stats = useMemo(() => {
    const active = rules.filter((rule) => rule.is_active).length;
    const deleted = rules.filter((rule) => rule.is_deleted).length;
    const sources = new Set(rules.map(() => getSourceLabel()));
    const withChecks = rules.filter((rule) => (rule.checks || []).length > 0).length;
    return {
      total: rules.length,
      active,
      inactive: Math.max(rules.length - active, 0),
      deleted,
      sourceCount: sources.size,
      withChecks,
    };
  }, [rules]);

  const sourceOptions = useMemo(
    () => (rules.length > 0 ? ["内置规则"] : []),
    [rules.length],
  );

  const filteredRules = useMemo(
    () =>
      rules.filter((rule) => {
        const keyword = searchTerm.trim().toLowerCase();
        const matchSearch =
          !keyword ||
          rule.name.toLowerCase().includes(keyword) ||
          rule.test_id.toLowerCase().includes(keyword) ||
          rule.description.toLowerCase().includes(keyword) ||
          rule.id.toLowerCase().includes(keyword);

        const matchSource =
          !selectedSource || getSourceLabel() === selectedSource;
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

  const handleStartEditRule = (rule: BanditRule) => {
    setEditRuleForm({
      name: rule.name || "",
      description_summary: rule.description_summary || "",
      description: rule.description || "",
      checks_text: (rule.checks || []).join(", "),
    });
    setIsEditingRule(true);
  };

  const handleViewRuleDetail = async (rule: BanditRule, mode: "view" | "edit" = "view") => {
    setSelectedRule(rule);
    setShowRuleDetail(true);
    setIsEditingRule(mode === "edit");
    setLoadingDetail(true);
    try {
      const detail = await getBanditRule(rule.test_id);
      setSelectedRule(detail);
      if (mode === "edit") {
        handleStartEditRule(detail);
      }
    } catch (error: any) {
      toast.error(error?.response?.data?.detail || "加载规则详情失败");
    } finally {
      setLoadingDetail(false);
    }
  };

  const handleCancelEditRule = () => {
    setIsEditingRule(false);
    setSavingRule(false);
  };

  const handleSaveRule = async () => {
    if (!selectedRule) return;
    const normalizedChecks = editRuleForm.checks_text
      .split(/[\n,]/)
      .map((item) => item.trim())
      .filter(Boolean);
    if (!editRuleForm.name.trim()) {
      toast.error("规则名称不能为空");
      return;
    }

    try {
      setSavingRule(true);
      const result = await updateBanditRule({
        ruleId: selectedRule.test_id,
        name: editRuleForm.name.trim(),
        description_summary: editRuleForm.description_summary.trim(),
        description: editRuleForm.description.trim(),
        checks: normalizedChecks,
      });
      const updatedRule = result.rule;
      setSelectedRule(updatedRule);
      setRules((prev) =>
        prev.map((item) => (item.id === updatedRule.id ? { ...item, ...updatedRule } : item)),
      );
      setIsEditingRule(false);
      toast.success(result.message || "规则更新成功");
    } catch (error: any) {
      toast.error(error?.response?.data?.detail || "更新规则失败");
    } finally {
      setSavingRule(false);
    }
  };

  const handleDeleteRule = async (rule: BanditRule) => {
    try {
      await deleteBanditRule(rule.test_id);
      toast.success(`规则「${rule.test_id}」已删除`);
      await loadRules();
    } catch (error: any) {
      toast.error(error?.response?.data?.detail || "删除规则失败");
    }
  };

  const handleRestoreRule = async (rule: BanditRule) => {
    try {
      await restoreBanditRule(rule.test_id);
      toast.success(`规则「${rule.test_id}」已恢复`);
      await loadRules();
    } catch (error: any) {
      toast.error(error?.response?.data?.detail || "恢复规则失败");
    }
  };

  const handleToggleRule = async (rule: BanditRule) => {
    if (rule.is_deleted) {
      toast.error("已删除规则请先恢复后再启用/禁用");
      return;
    }
    try {
      await updateBanditRuleEnabled({
        ruleId: rule.test_id,
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

  const handleBatchToggleEnabled = async (isActive: boolean) => {
    try {
      setBatchOperating(true);
      const payload =
        selectedRuleIds.size > 0
          ? {
              rule_ids: Array.from(selectedRuleIds),
              is_active: isActive,
            }
          : {
              // 来源展示已统一为“内置规则”，这里不再传 source 避免与后端原始 source 值不一致。
              source: undefined,
              keyword: searchTerm.trim() || undefined,
              current_is_active:
                selectedActiveStatus === ""
                  ? undefined
                  : selectedActiveStatus === "true",
              is_active: isActive,
            };
      const result = await batchUpdateBanditRulesEnabled(payload);
      toast.success(result.message);
      setSelectedRuleIds(new Set());
      await loadRules();
    } catch (error: any) {
      toast.error(error?.response?.data?.detail || "批量启停失败");
    } finally {
      setBatchOperating(false);
    }
  };

  const handleBatchDelete = async () => {
    try {
      setBatchOperating(true);
      const payload =
        selectedRuleIds.size > 0
          ? { rule_ids: Array.from(selectedRuleIds) }
          : {
              // 来源展示已统一为“内置规则”，这里不再传 source 避免与后端原始 source 值不一致。
              source: undefined,
              keyword: searchTerm.trim() || undefined,
              current_is_deleted: false,
            };
      const result = await batchDeleteBanditRules(payload);
      toast.success(result.message);
      setSelectedRuleIds(new Set());
      await loadRules();
    } catch (error: any) {
      toast.error(error?.response?.data?.detail || "批量删除失败");
    } finally {
      setBatchOperating(false);
    }
  };

  const handleBatchRestore = async () => {
    try {
      setBatchOperating(true);
      const payload =
        selectedRuleIds.size > 0
          ? { rule_ids: Array.from(selectedRuleIds) }
          : {
              // 来源展示已统一为“内置规则”，这里不再传 source 避免与后端原始 source 值不一致。
              source: undefined,
              keyword: searchTerm.trim() || undefined,
              current_is_deleted: true,
            };
      const result = await batchRestoreBanditRules(payload);
      toast.success(result.message);
      setSelectedRuleIds(new Set());
      await loadRules();
    } catch (error: any) {
      toast.error(error?.response?.data?.detail || "批量恢复失败");
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
              <p className="stat-label">含检查节点规则数</p>
              <p className="stat-value">{stats.withChecks}</p>
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
                  placeholder="搜索名称/ID/描述..."
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
                    {sourceOptions.map((sourceLabel) => (
                      <SelectItem key={sourceLabel} value={sourceLabel}>
                        {sourceLabel}
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

              <div className="min-w-[150px] flex-1">
                <Label className="font-mono font-bold uppercase text-xs text-muted-foreground">
                  删除状态
                </Label>
                <Select
                  value={selectedDeletedStatus}
                  onValueChange={(val: "false" | "true" | "all") => {
                    setSelectedDeletedStatus(val);
                    setCurrentPage(1);
                    setSelectedRuleIds(new Set());
                  }}
                >
                  <SelectTrigger className="cyber-input h-10 mt-1.5">
                    <SelectValue placeholder="删除状态" />
                  </SelectTrigger>
                  <SelectContent className="cyber-dialog border-border">
                    <SelectItem value="false">未删除</SelectItem>
                    <SelectItem value="true">已删除</SelectItem>
                    <SelectItem value="all">全部</SelectItem>
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
                    setSelectedDeletedStatus("false");
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
                <Button
                  onClick={() => void handleBatchToggleEnabled(true)}
                  disabled={batchOperating}
                  className="cyber-btn-primary h-9 text-sm"
                >
                  {batchOperating ? "处理中..." : "批量启用"}
                </Button>
                <Button
                  onClick={() => void handleBatchToggleEnabled(false)}
                  disabled={batchOperating}
                  className="cyber-btn-outline h-9 text-sm"
                >
                  {batchOperating ? "处理中..." : "批量禁用"}
                </Button>
                <Button
                  onClick={() => void handleBatchDelete()}
                  disabled={batchOperating}
                  className="cyber-btn-outline h-9 text-sm"
                >
                  {batchOperating ? "处理中..." : "批量删除"}
                </Button>
                <Button
                  onClick={() => void handleBatchRestore()}
                  disabled={batchOperating}
                  className="cyber-btn-outline h-9 text-sm"
                >
                  {batchOperating ? "处理中..." : "批量恢复"}
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
                  : "暂无规则数据（请先生成并导入 bandit 内置规则快照）"}
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
                    <TableHead className="min-w-[300px]">规则名称</TableHead>
                    <TableHead className="min-w-[180px]">检查节点</TableHead>
                    <TableHead className="w-[120px]">来源</TableHead>
                    <TableHead className="w-[110px]">启用状态</TableHead>
                    <TableHead className="w-[160px]">更新时间</TableHead>
                    <TableHead className="min-w-[300px]">操作</TableHead>
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
                          {/* <div className="font-mono text-xs text-muted-foreground break-all">{rule.test_id}</div> */}
                          {/* {rule.description_summary ? (
                            <div className="text-xs text-muted-foreground break-all line-clamp-2">
                              {rule.description_summary}
                            </div>
                          ) : null} */}
                        </div>
                      </TableCell>
                      <TableCell className="text-sm text-muted-foreground">
                        {(rule.checks || []).join(", ") || "-"}
                      </TableCell>
                      <TableCell>
                        <Badge className="cyber-badge cyber-badge-info">
                          {getSourceLabel()}
                        </Badge>
                      </TableCell>
                      <TableCell>
                        {rule.is_deleted ? (
                          <Badge className="cyber-badge cyber-badge-muted">已删除</Badge>
                        ) : (
                          <Badge className={rule.is_active ? "cyber-badge cyber-badge-success" : "cyber-badge cyber-badge-muted"}>
                            {rule.is_active ? "已启用" : "已禁用"}
                          </Badge>
                        )}
                      </TableCell>
                      <TableCell className="text-xs text-muted-foreground">
                        {rule.updated_at ? new Date(rule.updated_at).toLocaleString() : "-"}
                      </TableCell>
                      <TableCell>
                        <div className="flex flex-wrap gap-2">
                          <Button
                            onClick={() => handleViewRuleDetail(rule)}
                            className="cyber-btn-outline h-8 text-xs"
                          >
                            查看详情
                          </Button>
                          <Button
                            onClick={() => handleViewRuleDetail(rule, "edit")}
                            className="cyber-btn-outline h-8 text-xs"
                          >
                            编辑
                          </Button>
                          <Button
                            onClick={() => void handleToggleRule(rule)}
                            disabled={rule.is_deleted}
                            className={rule.is_active ? "cyber-btn-outline h-8 text-xs" : "cyber-btn-primary h-8 text-xs"}
                          >
                            {rule.is_active ? "禁用" : "启用"}
                          </Button>
                          {!rule.is_deleted ? (
                            <Button
                              onClick={() => void handleDeleteRule(rule)}
                              className="cyber-btn-outline h-8 text-xs"
                            >
                              删除
                            </Button>
                          ) : (
                            <Button
                              onClick={() => void handleRestoreRule(rule)}
                              className="cyber-btn-primary h-8 text-xs"
                            >
                              恢复
                            </Button>
                          )}
                        </div>
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

      <Dialog
        open={showRuleDetail}
        onOpenChange={(open) => {
          setShowRuleDetail(open);
          if (!open) {
            setIsEditingRule(false);
            setSavingRule(false);
          }
        }}
      >
        <DialogContent className="!w-[min(90vw,900px)] !max-w-none max-h-[90vh] flex flex-col p-0 gap-0 cyber-dialog border border-border rounded-lg">
          <DialogHeader className="px-6 pt-4 flex-shrink-0">
            <DialogTitle className="font-mono text-lg uppercase tracking-wider flex items-center gap-2 text-foreground">
              <Code className="w-5 h-5 text-primary" />
              {isEditingRule ? "编辑规则" : "规则详情"}
            </DialogTitle>
          </DialogHeader>

          {loadingDetail ? (
            <div className="flex items-center justify-center p-8">
              <div className="loading-spinner" />
            </div>
          ) : selectedRule ? (
            <div className="flex-1 overflow-y-auto p-6">
              <div className="space-y-6">
                <div className="space-y-3">
                  <h3 className="font-mono font-bold uppercase text-sm text-muted-foreground border-b border-border pb-2">
                    基本信息
                  </h3>
                  <div className="grid grid-cols-1 md:grid-cols-2 gap-4 text-sm font-mono">
                    <div>
                      <p className="text-muted-foreground">规则名称</p>
                      {isEditingRule ? (
                        <Input
                          value={editRuleForm.name}
                          onChange={(e) =>
                            setEditRuleForm((prev) => ({ ...prev, name: e.target.value }))
                          }
                          className="cyber-input mt-1.5 h-9"
                        />
                      ) : (
                        <p className="text-foreground font-bold mt-1 break-all">{selectedRule.name}</p>
                      )}
                    </div>
                    <div>
                      <p className="text-muted-foreground">规则ID</p>
                      <p className="text-foreground font-bold mt-1 break-all">{selectedRule.test_id}</p>
                    </div>
                    <div>
                      <p className="text-muted-foreground">来源</p>
                      <Badge className="cyber-badge cyber-badge-info mt-1">
                        {getSourceLabel()}
                      </Badge>
                    </div>
                    <div>
                      <p className="text-muted-foreground">Bandit版本</p>
                      <p className="text-foreground font-bold mt-1">{selectedRule.bandit_version || "-"}</p>
                    </div>
                    <div>
                      <p className="text-muted-foreground">启用状态</p>
                      {selectedRule.is_deleted ? (
                        <Badge className="cyber-badge cyber-badge-muted mt-1">已删除</Badge>
                      ) : (
                        <Badge className={`mt-1 ${selectedRule.is_active ? "cyber-badge cyber-badge-success" : "cyber-badge cyber-badge-muted"}`}>
                          {selectedRule.is_active ? "已启用" : "已禁用"}
                        </Badge>
                      )}
                    </div>
                    <div>
                      <p className="text-muted-foreground">规则标识</p>
                      <p className="text-foreground font-bold mt-1 break-all">
                        {selectedRule.source || "-"}
                      </p>
                    </div>
                  </div>
                </div>

                <div className="space-y-3">
                  <h3 className="font-mono font-bold uppercase text-sm text-muted-foreground border-b border-border pb-2">
                    摘要
                  </h3>
                  {isEditingRule ? (
                    <Textarea
                      value={editRuleForm.description_summary}
                      onChange={(e) =>
                        setEditRuleForm((prev) => ({ ...prev, description_summary: e.target.value }))
                      }
                      className="cyber-input min-h-24"
                    />
                  ) : (
                    <div className="rounded border border-border/50 p-3 text-sm whitespace-pre-wrap break-words">
                      {selectedRule.description_summary || "-"}
                    </div>
                  )}
                </div>

                <div className="space-y-3">
                  <h3 className="font-mono font-bold uppercase text-sm text-muted-foreground border-b border-border pb-2">
                    描述
                  </h3>
                  {isEditingRule ? (
                    <Textarea
                      value={editRuleForm.description}
                      onChange={(e) =>
                        setEditRuleForm((prev) => ({ ...prev, description: e.target.value }))
                      }
                      className="cyber-input min-h-52 font-mono text-xs"
                    />
                  ) : (
                    <div className="max-h-[320px] overflow-y-auto rounded border border-border/50 p-3 text-xs text-muted-foreground whitespace-pre-wrap break-words font-mono">
                      {selectedRule.description || "-"}
                    </div>
                  )}
                </div>

                <div className="space-y-3">
                  <h3 className="font-mono font-bold uppercase text-sm text-muted-foreground border-b border-border pb-2">
                    检查节点
                  </h3>
                  {isEditingRule ? (
                    <Textarea
                      value={editRuleForm.checks_text}
                      onChange={(e) =>
                        setEditRuleForm((prev) => ({ ...prev, checks_text: e.target.value }))
                      }
                      placeholder="支持逗号或换行分隔"
                      className="cyber-input min-h-24 font-mono text-xs"
                    />
                  ) : (
                    <div className="rounded border border-border/50 p-3 text-sm whitespace-pre-wrap break-words">
                      {(selectedRule.checks || []).join(", ") || "-"}
                    </div>
                  )}
                </div>

                <div className="space-y-3">
                  <h3 className="font-mono font-bold uppercase text-sm text-muted-foreground border-b border-border pb-2">
                    元数据
                  </h3>
                  <div className="text-sm font-mono text-muted-foreground">
                    <p>创建时间: {selectedRule.created_at ? new Date(selectedRule.created_at).toLocaleString("zh-CN") : "-"}</p>
                    <p>更新时间: {selectedRule.updated_at ? new Date(selectedRule.updated_at).toLocaleString("zh-CN") : "-"}</p>
                  </div>
                </div>
              </div>
            </div>
          ) : null}

          <div className="flex-shrink-0 flex justify-end gap-3 px-6 py-4 bg-muted border-t border-border">
            <Button
              variant="outline"
              onClick={() => {
                if (isEditingRule) {
                  handleCancelEditRule();
                } else {
                  setShowRuleDetail(false);
                }
              }}
              className="cyber-btn-outline"
            >
              {isEditingRule ? "取消编辑" : "关闭"}
            </Button>
            {isEditingRule ? (
              <Button
                onClick={() => void handleSaveRule()}
                className="cyber-btn-primary"
                disabled={savingRule}
              >
                {savingRule ? (
                  <>
                    <div className="loading-spinner mr-2" />
                    保存中...
                  </>
                ) : (
                  <>
                    <Save className="w-4 h-4 mr-2" />
                    保存规则
                  </>
                )}
              </Button>
            ) : null}
          </div>
        </DialogContent>
      </Dialog>
    </div>
  );
}
