/**
 * Opengrep Rules Management Page
 * Cyberpunk Terminal Aesthetic
 */

import { useState, useEffect } from "react";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
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
    Dialog,
    DialogContent,
    DialogHeader,
    DialogTitle,
} from "@/components/ui/dialog";
import {
    AlertDialog,
    AlertDialogAction,
    AlertDialogCancel,
    AlertDialogContent,
    AlertDialogDescription,
    AlertDialogFooter,
    AlertDialogHeader,
    AlertDialogTitle,
} from "@/components/ui/alert-dialog";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Textarea } from "@/components/ui/textarea";
import { Checkbox } from "@/components/ui/checkbox";
import { toast } from "sonner";
import {
    Trash2,
    Search,
    Copy,
    Eye,
    Code,
    AlertCircle,
    ChevronLeft,
    ChevronRight,
    AlertTriangle,
    Database,
    ShieldCheck,
    ListFilter,
} from "lucide-react";
import {
    getOpengrepRules,
    getOpengrepRule,
    toggleOpengrepRule,
    deleteOpengrepRule,
    generateOpengrepRule,
    uploadOpengrepRuleJSON,
    uploadOpengrepRulesCompressed,
    uploadOpengrepRulesDirectory,
    batchUpdateOpengrepRules,
    RULE_SOURCES,
    SEVERITIES,
    ACTIVE_STATUS,
    type OpengrepRule,
    type OpengrepRuleDetail,
} from "@/shared/api/opengrep";
import { setOpengrepActiveRules } from "@/shared/stores/opengrepRulesStore";

export default function OpengrepRules() {
    const [rules, setRules] = useState<OpengrepRule[]>([]);
    const [ruleStats, setRuleStats] = useState({ total: 0, active: 0 });
    const [loading, setLoading] = useState(true);
    const [searchTerm, setSearchTerm] = useState("");
    const [selectedLanguage, setSelectedLanguage] = useState<string>("");
    const [selectedSource, setSelectedSource] = useState<string>("");
    const [selectedSeverity, setSelectedSeverity] = useState<string>("");
    const [selectedActiveStatus, setSelectedActiveStatus] = useState<string>("");
    const [showRuleDetail, setShowRuleDetail] = useState(false);
    const [selectedRule, setSelectedRule] = useState<OpengrepRuleDetail | null>(
        null,
    );
    const [loadingDetail, setLoadingDetail] = useState(false);
    const [availableLanguages, setAvailableLanguages] = useState<string[]>([]);
    const [showRuleTypeDialog, setShowRuleTypeDialog] = useState(false);
    const [showGenericDialog, setShowGenericDialog] = useState(false);
    const [showEventDialog, setShowEventDialog] = useState(false);
    const [generatingRule, setGeneratingRule] = useState(false);
    const [currentPage, setCurrentPage] = useState(1);
    const [pageSize, setPageSize] = useState(10);
    const [selectedRuleIds, setSelectedRuleIds] = useState<Set<string>>(
        new Set(),
    );
    const [batchOperating, setBatchOperating] = useState(false);
    const [pendingDeleteRule, setPendingDeleteRule] = useState<{
        id: string;
        name: string;
    } | null>(null);
    const [deletingRule, setDeletingRule] = useState(false);
    const [generateFormData, setGenerateFormData] = useState({
        repo_owner: "",
        repo_name: "",
        commit_hash: "",
        commit_content: "",
    });
    const [genericRuleUploadTab, setGenericRuleUploadTab] = useState<
        "manual" | "compressed" | "directory"
    >("manual");
    const [compressedFile, setCompressedFile] = useState<File | null>(null);
    const [directoryFiles, setDirectoryFiles] = useState<File[]>([]);
    const [uploadingRules, setUploadingRules] = useState(false);
    const [manualRuleForm, setManualRuleForm] = useState({
        id: "",
        name: "",
        language: "python",
        pattern_yaml: "",
        severity: "WARNING",
        source: "json",
        patch: "",
        correct: true,
        is_active: true,
    });

    useEffect(() => {
        loadRules();
        loadRuleStats();
    }, []);

    // 当筛选条件改变时，重新加载规则
    useEffect(() => {
        if (!loading) {
            setCurrentPage(1);
            loadRules();
        }
    }, [selectedLanguage, selectedSource, selectedSeverity, selectedActiveStatus]);

    const loadRules = async (options?: { silent?: boolean }) => {
        const silent = options?.silent ?? false;
        try {
            if (!silent) {
                setLoading(true);
            }
            const data = await getOpengrepRules({
                language: selectedLanguage || undefined,
                source: (selectedSource as "internal" | "patch") || undefined,
            });
            setRules(data);

            // 如果是首次加载或没有筛选条件，保存所有规则用于提取语言列表
            if (!selectedLanguage && !selectedSource) {
                // 提取所有唯一的编程语言
                const languages = Array.from(
                    new Set(data.map((rule) => rule.language)),
                ).sort();
                setAvailableLanguages(languages);
            }

            // 同步启用规则到全局缓存
            setOpengrepActiveRules(data.filter((rule) => rule.is_active));
        } catch (error) {
            console.error("Failed to load rules:", error);
            toast.error("加载规则失败");
        } finally {
            if (!silent) {
                setLoading(false);
            }
        }
    };

    const loadRuleStats = async () => {
        try {
            const allRules = await getOpengrepRules();
            setRuleStats({
                total: allRules.length,
                active: allRules.filter((rule) => rule.is_active).length,
            });
        } catch (error) {
            console.error("Failed to load rule stats:", error);
        }
    };

    const handleViewRule = async (rule: OpengrepRule) => {
        try {
            setLoadingDetail(true);
            const detail = await getOpengrepRule(rule.id);
            setSelectedRule(detail);
            setShowRuleDetail(true);
        } catch (error) {
            console.error("Failed to load rule detail:", error);
            toast.error("加载规则详情失败");
        } finally {
            setLoadingDetail(false);
        }
    };

    const handleToggleRule = async (rule: OpengrepRule) => {
        const nextActive = !rule.is_active;
        const previousRules = rules;
        const nextRules = rules.map((item) =>
            item.id === rule.id ? { ...item, is_active: nextActive } : item,
        );

        setRules(nextRules);
        setOpengrepActiveRules(nextRules.filter((item) => item.is_active));

        try {
            await toggleOpengrepRule(rule.id);
            loadRuleStats();
            toast.success(`规则已${rule.is_active ? "禁用" : "启用"}`);
        } catch (error) {
            setRules(previousRules);
            setOpengrepActiveRules(
                previousRules.filter((item) => item.is_active),
            );
            console.error("Failed to toggle rule:", error);
            toast.error("更新规则失败");
        }
    };

    const handleDeleteRule = async () => {
        if (!pendingDeleteRule) return;
        const deletingTarget = pendingDeleteRule;
        try {
            setDeletingRule(true);
            await deleteOpengrepRule(deletingTarget.id);
            toast.success(`规则「${deletingTarget.name}」删除成功`);
            await loadRules({ silent: true });
            await loadRuleStats();
            setShowRuleDetail(false);
            setPendingDeleteRule(null);
        } catch (error) {
            console.error("Failed to delete rule:", error);
            toast.error("删除规则失败");
        } finally {
            setDeletingRule(false);
        }
    };

    const handleGenerateRule = async () => {
        if (
            !generateFormData.repo_owner ||
            !generateFormData.repo_name ||
            !generateFormData.commit_hash ||
            !generateFormData.commit_content
        ) {
            toast.error("请填写所有必需字段");
            return;
        }
        try {
            setGeneratingRule(true);
            await generateOpengrepRule(generateFormData);
            toast.success("规则生成成功");
            setShowEventDialog(false);
            setGenerateFormData({
                repo_owner: "",
                repo_name: "",
                commit_hash: "",
                commit_content: "",
            });
            await loadRules({ silent: true });
            await loadRuleStats();
        } catch (error) {
            console.error("Failed to generate rule:", error);
            toast.error("生成规则失败");
        } finally {
            setGeneratingRule(false);
        }
    };

    const handleGenerateGenericRule = async () => {
        if (!manualRuleForm.name.trim()) {
            toast.error("请输入规则名称");
            return;
        }
        if (!manualRuleForm.pattern_yaml.trim()) {
            toast.error("请输入规则 YAML 内容");
            return;
        }
        if (!manualRuleForm.language.trim()) {
            toast.error("请输入编程语言");
            return;
        }

        // 验证编程语言是否正确
        const supportedLanguages = [
            "python",
            "javascript",
            "typescript",
            "java",
            "go",
            "rust",
            "cpp",
            "c",
            "csharp",
            "c#",
            "php",
            "ruby",
            "kotlin",
            "swift",
            "objc",
            "scala",
            "groovy",
            "clojure",
            "elixir",
            "erlang",
            "haskell",
            "lua",
            "perl",
            "r",
            "sql",
            "bash",
            "shell",
            "powershell",
            "dockerfile",
            "yaml",
            "json",
            "xml",
            "html",
            "css",
            "scss",
            "less",
            "dart",
            "go",
            "julia",
        ];

        const language = manualRuleForm.language.toLowerCase().trim();
        if (!supportedLanguages.includes(language)) {
            toast.error(
                `编程语言 "${manualRuleForm.language}" 不是常见语言，请检查拼写。常见语言: ${supportedLanguages.slice(0, 8).join(", ")}...`,
            );
            return;
        }

        try {
            setUploadingRules(true);
            await uploadOpengrepRuleJSON({
                ...(manualRuleForm.id && { id: manualRuleForm.id }),
                name: manualRuleForm.name,
                pattern_yaml: manualRuleForm.pattern_yaml,
                language: language,
                severity: manualRuleForm.severity,
                source: manualRuleForm.source,
                ...(manualRuleForm.patch && { patch: manualRuleForm.patch }),
                correct: manualRuleForm.correct,
                is_active: manualRuleForm.is_active,
            });

            toast.success("规则上传成功");
            setShowGenericDialog(false);
            setManualRuleForm({
                id: "",
                name: "",
                language: "python",
                pattern_yaml: "",
                severity: "WARNING",
                source: "json",
                patch: "",
                correct: true,
                is_active: true,
            });
            setGenericRuleUploadTab("manual");
            await loadRules({ silent: true });
            await loadRuleStats();
        } catch (error: any) {
            const message =
                error?.response?.data?.detail || error?.message || "上传规则失败";
            toast.error(message);
        } finally {
            setUploadingRules(false);
        }
    };

    const handleUploadCompressedRules = async () => {
        if (!compressedFile) {
            toast.error("请选择压缩文件");
            return;
        }
        try {
            setUploadingRules(true);
            const result = await uploadOpengrepRulesCompressed(compressedFile);
            toast.success(
                `上传成功: 成功 ${result.success_count}，失败 ${result.failed_count}，重复 ${result.duplicate_count}`,
            );
            setShowGenericDialog(false);
            setCompressedFile(null);
            setGenericRuleUploadTab("manual");
            await loadRules({ silent: true });
            await loadRuleStats();
        } catch (error: any) {
            const message =
                error?.response?.data?.detail || error?.message || "上传规则失败";
            toast.error(message);
        } finally {
            setUploadingRules(false);
        }
    };

    const handleUploadDirectoryRules = async () => {
        if (directoryFiles.length === 0) {
            toast.error("请选择规则文件");
            return;
        }
        try {
            setUploadingRules(true);
            const result = await uploadOpengrepRulesDirectory(directoryFiles);
            toast.success(
                `上传成功: 成功 ${result.success_count}，失败 ${result.failed_count}，重复 ${result.duplicate_count}`,
            );
            setShowGenericDialog(false);
            setDirectoryFiles([]);
            setGenericRuleUploadTab("manual");
            await loadRules({ silent: true });
            await loadRuleStats();
        } catch (error: any) {
            const message =
                error?.response?.data?.detail || error?.message || "上传规则失败";
            toast.error(message);
        } finally {
            setUploadingRules(false);
        }
    };

    const handleResetFilters = () => {
        setSearchTerm("");
        setSelectedLanguage("");
        setSelectedSource("");
        setSelectedSeverity("");
        setSelectedActiveStatus("");
        setCurrentPage(1);
        setSelectedRuleIds(new Set());
    };

    const handleToggleRuleSelection = (ruleId: string) => {
        const newSet = new Set(selectedRuleIds);
        if (newSet.has(ruleId)) {
            newSet.delete(ruleId);
        } else {
            newSet.add(ruleId);
        }
        setSelectedRuleIds(newSet);
    };

    const handleToggleAllSelection = () => {
        if (selectedRuleIds.size === paginatedRules.length) {
            setSelectedRuleIds(new Set());
        } else {
            setSelectedRuleIds(new Set(paginatedRules.map((r) => r.id)));
        }
    };

    const handleBatchUpdateRules = async (isActive: boolean) => {
        // 如果有直接选中的规则 ID，使用 rule_ids 方式
        if (selectedRuleIds.size > 0) {
            try {
                setBatchOperating(true);
                const result = await batchUpdateOpengrepRules({
                    rule_ids: Array.from(selectedRuleIds),
                    is_active: isActive,
                });
                toast.success(result.message);
                setSelectedRuleIds(new Set());
                await loadRules({ silent: true });
                await loadRuleStats();
            } catch (error) {
                console.error("Batch operation failed:", error);
                toast.error("批量操作失败");
            } finally {
                setBatchOperating(false);
            }
            return;
        }

        // 否则，检查是否有其他过滤条件
        if (!selectedLanguage && !selectedSource && !selectedSeverity) {
            toast.error("请先选择要操作的规则或设定过滤条件");
            return;
        }

        try {
            setBatchOperating(true);
            const result = await batchUpdateOpengrepRules({
                language: selectedLanguage || undefined,
                source: (selectedSource as "internal" | "patch") || undefined,
                severity: selectedSeverity || undefined,
                is_active: isActive,
            });
            toast.success(result.message);
            await loadRules({ silent: true });
            await loadRuleStats();
        } catch (error) {
            console.error("Batch operation failed:", error);
            toast.error("批量操作失败");
        } finally {
            setBatchOperating(false);
        }
    };

    const filteredRules = rules.filter((rule) => {
        const matchSearch =
            rule.name.toLowerCase().includes(searchTerm.toLowerCase()) ||
            rule.id.toLowerCase().includes(searchTerm.toLowerCase());

        const matchLanguage =
            !selectedLanguage || rule.language === selectedLanguage;
        const matchSeverity =
            !selectedSeverity || rule.severity === selectedSeverity;
        const matchActiveStatus =
            !selectedActiveStatus ||
            (selectedActiveStatus === "true" && rule.is_active) ||
            (selectedActiveStatus === "false" && !rule.is_active);

        return (
            matchSearch && matchLanguage && matchSeverity && matchActiveStatus
        );
    });

    // 分页逻辑
    const totalPages = Math.ceil(filteredRules.length / pageSize);
    const paginatedRules = filteredRules.slice(
        (currentPage - 1) * pageSize,
        currentPage * pageSize,
    );

    const getSeverityColor = (severity: string) => {
        switch (severity) {
            case "ERROR":
                return "bg-rose-500/20 text-rose-300 border-rose-500/30";
            case "WARNING":
                return "bg-amber-500/20 text-amber-300 border-amber-500/30";
            case "INFO":
                return "bg-sky-500/20 text-sky-300 border-sky-500/30";
            default:
                return "bg-muted text-muted-foreground";
        }
    };

    const getSourceBadge = (source: string) => {
        return source === "patch" ? "从Patch生成" : "内置规则";
    };

    if (loading) {
        return (
            <div className="flex items-center justify-center min-h-screen">
                <div className="text-center space-y-4">
                    <div className="loading-spinner mx-auto" />
                    <p className="text-muted-foreground font-mono text-sm uppercase tracking-wider">
                        加载规则数据...
                    </p>
                </div>
            </div>
        );
    }

    return (
        <div className="h-screen flex flex-col bg-background font-mono relative overflow-hidden">
            {/* Grid background */}
            <div className="absolute inset-0 cyber-grid-subtle pointer-events-none" />

            {/* Scrollable Content */}
            <div className="flex-1 overflow-y-auto">
                <div className="space-y-6 p-6 relative z-10">
                    {/* Filters */}
                    <div className="cyber-card p-4 relative z-10 space-y-4">
                        <div>
                            <Label className="font-mono font-bold uppercase text-xs text-muted-foreground">
                                搜索
                            </Label>
                            <div className="relative mt-1.5">
                                <Search className="absolute left-3 top-1/2 transform -translate-y-1/2 text-muted-foreground w-4 h-4" />
                                <Input
                                    placeholder="规则名称或ID..."
                                    value={searchTerm}
                                    onChange={(e) =>
                                        setSearchTerm(e.target.value)
                                    }
                                    className="cyber-input !pl-10"
                                />
                            </div>
                        </div>

                        <div className="flex flex-wrap items-end gap-4">
                            <div className="min-w-[180px] flex-1">
                                <Label className="font-mono font-bold uppercase text-xs text-muted-foreground">
                                    编程语言
                                </Label>
                                <Select
                                    value={selectedLanguage || "all"}
                                    onValueChange={(val) =>
                                        setSelectedLanguage(
                                            val === "all" ? "" : val,
                                        )
                                    }
                                >
                                    <SelectTrigger className="cyber-input mt-1.5">
                                        <SelectValue placeholder="所有语言" />
                                    </SelectTrigger>
                                    <SelectContent className="cyber-dialog border-border">
                                        <SelectItem value="all">
                                            所有语言
                                        </SelectItem>
                                        {availableLanguages.map((lang) => (
                                            <SelectItem key={lang} value={lang}>
                                                {lang}
                                            </SelectItem>
                                        ))}
                                    </SelectContent>
                                </Select>
                            </div>

                            <div className="min-w-[180px] flex-1">
                                <Label className="font-mono font-bold uppercase text-xs text-muted-foreground">
                                    规则来源
                                </Label>
                                <Select
                                    value={selectedSource || "all"}
                                    onValueChange={(val) =>
                                        setSelectedSource(
                                            val === "all" ? "" : val,
                                        )
                                    }
                                >
                                    <SelectTrigger className="cyber-input mt-1.5">
                                        <SelectValue placeholder="所有来源" />
                                    </SelectTrigger>
                                    <SelectContent className="cyber-dialog border-border">
                                        <SelectItem value="all">
                                            所有来源
                                        </SelectItem>
                                        {RULE_SOURCES.map((source) => (
                                            <SelectItem
                                                key={source.value}
                                                value={source.value}
                                            >
                                                {source.label}
                                            </SelectItem>
                                        ))}
                                    </SelectContent>
                                </Select>
                            </div>

                            <div className="min-w-[180px] flex-1">
                                <Label className="font-mono font-bold uppercase text-xs text-muted-foreground">
                                    严重程度
                                </Label>
                                <Select
                                    value={selectedSeverity || "all"}
                                    onValueChange={(val) =>
                                        setSelectedSeverity(
                                            val === "all" ? "" : val,
                                        )
                                    }
                                >
                                    <SelectTrigger className="cyber-input mt-1.5">
                                        <SelectValue placeholder="所有级别" />
                                    </SelectTrigger>
                                    <SelectContent className="cyber-dialog border-border">
                                        <SelectItem value="all">
                                            所有级别
                                        </SelectItem>
                                        {SEVERITIES.map((severity) => (
                                            <SelectItem
                                                key={severity.value}
                                                value={severity.value}
                                            >
                                                {severity.label}
                                            </SelectItem>
                                        ))}
                                    </SelectContent>
                                </Select>
                            </div>

                            <div className="min-w-[180px] flex-1">
                                <Label className="font-mono font-bold uppercase text-xs text-muted-foreground">
                                    启用状态
                                </Label>
                                <Select
                                    value={selectedActiveStatus || "all"}
                                    onValueChange={(val) =>
                                        setSelectedActiveStatus(
                                            val === "all" ? "" : val,
                                        )
                                    }
                                >
                                    <SelectTrigger className="cyber-input mt-1.5">
                                        <SelectValue placeholder="所有状态" />
                                    </SelectTrigger>
                                    <SelectContent className="cyber-dialog border-border">
                                        <SelectItem value="all">
                                            所有状态
                                        </SelectItem>
                                        {ACTIVE_STATUS.map((status) => (
                                            <SelectItem
                                                key={status.value}
                                                value={status.value}
                                            >
                                                {status.label}
                                            </SelectItem>
                                        ))}
                                    </SelectContent>
                                </Select>
                            </div>

                            <div className="flex items-end gap-2">
                                <Button
                                    variant="outline"
                                    onClick={handleResetFilters}
                                    className="cyber-btn-outline h-10 min-w-[110px]"
                                >
                                    重置
                                </Button>
                                <Button
                                    onClick={() => setShowRuleTypeDialog(true)}
                                    className="cyber-btn-primary h-10 min-w-[150px]"
                                >
                                    新建规则
                                </Button>
                            </div>
                        </div>
                    </div>

                    {/* Stats Cards */}
                    <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4 relative z-10">
                        <div className="cyber-card p-4">
                            <div className="flex items-center justify-between">
                                <div>
                                    <p className="stat-label">有效规则总数</p>
                                    <p className="stat-value">
                                        {ruleStats.total}
                                    </p>
                                    <p className="text-sm text-muted-foreground mt-1">
                                        当前规则库
                                    </p>
                                </div>
                                <div className="stat-icon text-primary">
                                    <Database className="w-6 h-6" />
                                </div>
                            </div>
                        </div>

                        <div className="cyber-card p-4">
                            <div className="flex items-center justify-between">
                                <div>
                                    <p className="stat-label">启用规则数量</p>
                                    <p className="stat-value">
                                        {ruleStats.active}
                                    </p>
                                    <p className="text-sm text-emerald-400 mt-1 flex items-center gap-1">
                                        <span className="w-2 h-2 rounded-full bg-emerald-400" />
                                        未禁用
                                    </p>
                                </div>
                                <div className="stat-icon text-emerald-400">
                                    <ShieldCheck className="w-6 h-6" />
                                </div>
                            </div>
                        </div>

                        <div className="cyber-card p-4">
                            <div className="flex items-center justify-between">
                                <div>
                                    <p className="stat-label">筛选规则数量</p>
                                    <p className="stat-value">
                                        {filteredRules.length}
                                    </p>
                                    <p className="text-sm text-sky-400 mt-1 flex items-center gap-1">
                                        <span className="w-2 h-2 rounded-full bg-sky-400" />
                                        当前筛选结果
                                    </p>
                                </div>
                                <div className="stat-icon text-sky-400">
                                    <ListFilter className="w-6 h-6" />
                                </div>
                            </div>
                        </div>
                    </div>

                    {/* Batch Operations */}
                    {(selectedRuleIds.size > 0 ||
                        selectedLanguage ||
                        selectedSource ||
                        selectedSeverity) && (
                        <div className="cyber-card p-4 relative z-10 bg-primary/5 border-primary/30">
                            <div className="flex flex-wrap items-center justify-between gap-4">
                                <p className="font-mono text-sm">
                                    {selectedRuleIds.size > 0 ? (
                                        <>
                                            已选择{" "}
                                            <span className="font-bold text-primary">
                                                {selectedRuleIds.size}
                                            </span>{" "}
                                            条规则
                                        </>
                                    ) : (
                                        <>
                                            将对{" "}
                                            <span className="font-bold text-primary">
                                                {filteredRules.length}
                                            </span>{" "}
                                            条符合条件的规则进行操作
                                        </>
                                    )}
                                </p>
                                <div className="flex flex-wrap gap-2">
                                    <Button
                                        onClick={() =>
                                            handleBatchUpdateRules(true)
                                        }
                                        disabled={batchOperating}
                                        className="cyber-btn-primary h-9 text-sm"
                                    >
                                        {batchOperating
                                            ? "处理中..."
                                            : "批量启用"}
                                    </Button>
                                    <Button
                                        onClick={() =>
                                            handleBatchUpdateRules(false)
                                        }
                                        disabled={batchOperating}
                                        className="cyber-btn-outline h-9 text-sm"
                                    >
                                        {batchOperating
                                            ? "处理中..."
                                            : "批量禁用"}
                                    </Button>
                                    <Button
                                        onClick={() => {
                                            setSelectedRuleIds(new Set());
                                            handleResetFilters();
                                        }}
                                        disabled={batchOperating}
                                        className="cyber-btn-ghost h-9 text-sm"
                                    >
                                        取消操作
                                    </Button>
                                </div>
                            </div>
                        </div>
                    )}

                    {/* Rules Table */}
                    <div className="cyber-card relative z-10 overflow-hidden">
                        {filteredRules.length === 0 ? (
                            <div className="p-16 text-center">
                                <AlertCircle className="w-12 h-12 text-muted-foreground mx-auto mb-4" />
                                <h3 className="text-lg font-bold text-foreground mb-2">
                                    未找到规则
                                </h3>
                                <p className="text-muted-foreground font-mono text-sm">
                                    {searchTerm ||
                                    selectedLanguage ||
                                    selectedSource ||
                                    selectedSeverity
                                        ? "调整筛选条件尝试"
                                        : "暂无规则数据"}
                                </p>
                            </div>
                        ) : (
                            <>
                                <div>
                                    {/* Table Header with Select All */}
                                    <div className="flex items-center gap-3 p-4 border-b border-border bg-muted/30">
                                        <Checkbox
                                            checked={
                                                selectedRuleIds.size ===
                                                    paginatedRules.length &&
                                                paginatedRules.length > 0
                                            }
                                            onCheckedChange={
                                                handleToggleAllSelection
                                            }
                                            className="w-4 h-4"
                                        />
                                        <span className="text-sm font-mono text-muted-foreground">
                                            {selectedRuleIds.size > 0
                                                ? `已选择 ${selectedRuleIds.size} 条`
                                                : "全选当前页"}
                                        </span>
                                    </div>

                                    {/* Rules List */}
                                    <ScrollArea className="h-[calc(100vh-600px)] min-h-[400px]">
                                        <div className="divide-y divide-border">
                                            {paginatedRules.map((rule) => (
                                                <div
                                                    key={rule.id}
                                                    className="p-4 hover:bg-muted/50 transition-colors border-b border-border last:border-0"
                                                >
                                                    <div className="flex flex-col xl:flex-row xl:items-start xl:justify-between gap-4">
                                                        <div className="flex gap-3 flex-1 min-w-0">
                                                            <Checkbox
                                                                checked={selectedRuleIds.has(
                                                                    rule.id,
                                                                )}
                                                                onCheckedChange={() =>
                                                                    handleToggleRuleSelection(
                                                                        rule.id,
                                                                    )
                                                                }
                                                                className="w-4 h-4 mt-1"
                                                            />
                                                            <div className="flex-1 min-w-0">
                                                                <div className="flex items-center gap-2 mb-2">
                                                                    <h3 className="font-bold text-foreground truncate">
                                                                        {
                                                                            rule.name
                                                                        }
                                                                    </h3>
                                                                    <Badge
                                                                        className={`cyber-badge ${getSeverityColor(rule.severity)}`}
                                                                    >
                                                                        {
                                                                            rule.severity
                                                                        }
                                                                    </Badge>
                                                                    <Badge
                                                                        className={`cyber-badge ${
                                                                            rule.source ===
                                                                            "patch"
                                                                                ? "cyber-badge-warning"
                                                                                : "cyber-badge-info"
                                                                        }`}
                                                                    >
                                                                        {getSourceBadge(
                                                                            rule.source,
                                                                        )}
                                                                    </Badge>
                                                                    {rule.is_active ? (
                                                                        <Badge className="cyber-badge cyber-badge-success">
                                                                            已启用
                                                                        </Badge>
                                                                    ) : (
                                                                        <Badge className="cyber-badge cyber-badge-muted">
                                                                            已禁用
                                                                        </Badge>
                                                                    )}
                                                                </div>

                                                                <div className="grid grid-cols-2 md:grid-cols-4 gap-3 text-xs text-muted-foreground font-mono">
                                                                    <div>
                                                                        <span className="text-muted-foreground">
                                                                            ID:{" "}
                                                                        </span>
                                                                        <span className="text-foreground font-bold">
                                                                            {rule.id.substring(
                                                                                0,
                                                                                8,
                                                                            )}
                                                                        </span>
                                                                    </div>
                                                                    <div>
                                                                        <span className="text-muted-foreground">
                                                                            语言:{" "}
                                                                        </span>
                                                                        <span className="text-foreground font-bold">
                                                                            {
                                                                                rule.language
                                                                            }
                                                                        </span>
                                                                    </div>
                                                                    <div>
                                                                        <span className="text-muted-foreground">
                                                                            状态:{" "}
                                                                        </span>
                                                                        <span
                                                                            className={
                                                                                rule.correct
                                                                                    ? "text-emerald-400"
                                                                                    : "text-amber-400"
                                                                            }
                                                                        >
                                                                            {rule.correct
                                                                                ? "✓ 正确"
                                                                                : "⚠ 未验证"}
                                                                        </span>
                                                                    </div>
                                                                    <div>
                                                                        <span className="text-muted-foreground">
                                                                            创建:{" "}
                                                                        </span>
                                                                        <span className="text-foreground font-bold">
                                                                            {new Date(
                                                                                rule.created_at,
                                                                            ).toLocaleDateString(
                                                                                "zh-CN",
                                                                            )}
                                                                        </span>
                                                                    </div>
                                                                </div>
                                                            </div>
                                                        </div>

                                                        <div className="flex flex-wrap items-center gap-2 xl:justify-end">
                                                            <Button
                                                                size="sm"
                                                                variant="outline"
                                                                onClick={() =>
                                                                    handleViewRule(
                                                                        rule,
                                                                    )
                                                                }
                                                                className="cyber-btn-ghost h-8 px-3 min-w-[64px]"
                                                            >
                                                                <Eye className="w-4 h-4" />
                                                            </Button>
                                                            <Button
                                                                size="sm"
                                                                variant="outline"
                                                                onClick={() =>
                                                                    handleToggleRule(
                                                                        rule,
                                                                    )
                                                                }
                                                                className={`cyber-btn-ghost h-8 px-3 min-w-[72px] ${
                                                                    rule.is_active
                                                                        ? "hover:bg-rose-500/10"
                                                                        : "hover:bg-emerald-500/10"
                                                                }`}
                                                            >
                                                                {rule.is_active
                                                                    ? "禁用"
                                                                    : "启用"}
                                                            </Button>
                                                            <Button
                                                                size="sm"
                                                                variant="outline"
                                                                onClick={() =>
                                                                    setPendingDeleteRule(
                                                                        {
                                                                            id: rule.id,
                                                                            name: rule.name,
                                                                        },
                                                                    )
                                                                }
                                                                className="cyber-btn-ghost h-8 px-3 min-w-[64px] hover:bg-rose-500/10 hover:text-rose-400"
                                                            >
                                                                <Trash2 className="w-4 h-4" />
                                                            </Button>
                                                        </div>
                                                    </div>
                                                </div>
                                            ))}
                                        </div>
                                    </ScrollArea>
                                </div>

                                {/* Pagination */}
                                <div className="flex items-center justify-between p-4 border-t border-border bg-muted/20">
                                    <div className="flex items-center gap-2">
                                        <Label className="text-xs font-mono text-muted-foreground">
                                            每页显示:
                                        </Label>
                                        <Select
                                            value={pageSize.toString()}
                                            onValueChange={(val) => {
                                                setPageSize(Number(val));
                                                setCurrentPage(1);
                                            }}
                                        >
                                            <SelectTrigger className="cyber-input w-[80px] h-8">
                                                <SelectValue />
                                            </SelectTrigger>
                                            <SelectContent className="cyber-dialog border-border">
                                                <SelectItem value="10">
                                                    10
                                                </SelectItem>
                                                <SelectItem value="20">
                                                    20
                                                </SelectItem>
                                                <SelectItem value="50">
                                                    50
                                                </SelectItem>
                                                <SelectItem value="100">
                                                    100
                                                </SelectItem>
                                            </SelectContent>
                                        </Select>
                                    </div>

                                    <div className="text-xs font-mono text-muted-foreground">
                                        第 {currentPage} / {totalPages} 页 (共{" "}
                                        {filteredRules.length} 条)
                                    </div>

                                    <div className="flex items-center gap-2">
                                        <Button
                                            size="sm"
                                            variant="outline"
                                            onClick={() =>
                                                setCurrentPage(
                                                    Math.max(
                                                        1,
                                                        currentPage - 1,
                                                    ),
                                                )
                                            }
                                            disabled={currentPage === 1}
                                            className="cyber-btn-ghost h-8 px-2 w-8"
                                        >
                                            <ChevronLeft className="w-4 h-4" />
                                        </Button>
                                        <div className="flex items-center gap-1">
                                            {Array.from(
                                                {
                                                    length: Math.min(
                                                        5,
                                                        totalPages,
                                                    ),
                                                },
                                                (_, i) => {
                                                    const page =
                                                        Math.max(
                                                            1,
                                                            currentPage - 2,
                                                        ) + i;
                                                    if (page > totalPages)
                                                        return null;
                                                    return (
                                                        <Button
                                                            key={page}
                                                            size="sm"
                                                            variant={
                                                                page ===
                                                                currentPage
                                                                    ? "default"
                                                                    : "outline"
                                                            }
                                                            onClick={() =>
                                                                setCurrentPage(
                                                                    page,
                                                                )
                                                            }
                                                            className={`cyber-btn-${page === currentPage ? "primary" : "ghost"} h-8 px-2 min-w-8`}
                                                        >
                                                            {page}
                                                        </Button>
                                                    );
                                                },
                                            )}
                                        </div>
                                        <Button
                                            size="sm"
                                            variant="outline"
                                            onClick={() =>
                                                setCurrentPage(
                                                    Math.min(
                                                        totalPages,
                                                        currentPage + 1,
                                                    ),
                                                )
                                            }
                                            disabled={
                                                currentPage === totalPages
                                            }
                                            className="cyber-btn-ghost h-8 px-2 w-8"
                                        >
                                            <ChevronRight className="w-4 h-4" />
                                        </Button>
                                    </div>
                                </div>
                            </>
                        )}
                    </div>

                    {/* Rule Detail Dialog */}
                    <Dialog
                        open={showRuleDetail}
                        onOpenChange={setShowRuleDetail}
                    >
                        <DialogContent className="!w-[min(90vw,900px)] !max-w-none max-h-[90vh] flex flex-col p-0 gap-0 cyber-dialog border border-border rounded-lg">
                            {/* Terminal Header */}
                            <div className="flex items-center gap-2 px-4 py-3 cyber-bg-elevated border-b border-border flex-shrink-0">
                                <div className="flex items-center gap-1.5">
                                    <div className="w-3 h-3 rounded-full bg-red-500/80" />
                                    <div className="w-3 h-3 rounded-full bg-yellow-500/80" />
                                    <div className="w-3 h-3 rounded-full bg-green-500/80" />
                                </div>
                                <span className="ml-2 font-mono text-xs text-muted-foreground tracking-wider">
                                    rule_detail@deepaudit
                                </span>
                            </div>

                            <DialogHeader className="px-6 pt-4 flex-shrink-0">
                                <DialogTitle className="font-mono text-lg uppercase tracking-wider flex items-center gap-2 text-foreground">
                                    <Code className="w-5 h-5 text-primary" />
                                    规则详情
                                </DialogTitle>
                            </DialogHeader>

                            {loadingDetail ? (
                                <div className="flex items-center justify-center p-8">
                                    <div className="loading-spinner" />
                                </div>
                            ) : selectedRule ? (
                                <div className="flex-1 overflow-y-auto p-6">
                                    <div className="space-y-6">
                                        {/* Basic Info */}
                                        <div className="space-y-3">
                                            <h3 className="font-mono font-bold uppercase text-sm text-muted-foreground border-b border-border pb-2">
                                                基本信息
                                            </h3>
                                            <div className="grid grid-cols-2 gap-4 text-sm font-mono">
                                                <div>
                                                    <p className="text-muted-foreground">
                                                        名称
                                                    </p>
                                                    <p className="text-foreground font-bold mt-1">
                                                        {selectedRule.name}
                                                    </p>
                                                </div>
                                                <div>
                                                    <p className="text-muted-foreground">
                                                        规则ID
                                                    </p>
                                                    <p className="text-foreground font-bold mt-1 break-all">
                                                        {selectedRule.id}
                                                    </p>
                                                </div>
                                                <div>
                                                    <p className="text-muted-foreground">
                                                        编程语言
                                                    </p>
                                                    <p className="text-foreground font-bold mt-1">
                                                        {selectedRule.language}
                                                    </p>
                                                </div>
                                                <div>
                                                    <p className="text-muted-foreground">
                                                        严重程度
                                                    </p>
                                                    <Badge
                                                        className={`cyber-badge mt-1 ${getSeverityColor(selectedRule.severity)}`}
                                                    >
                                                        {selectedRule.severity}
                                                    </Badge>
                                                </div>
                                                <div>
                                                    <p className="text-muted-foreground">
                                                        规则来源
                                                    </p>
                                                    <Badge
                                                        className={`cyber-badge mt-1 ${selectedRule.source === "patch" ? "cyber-badge-warning" : "cyber-badge-info"}`}
                                                    >
                                                        {getSourceBadge(
                                                            selectedRule.source,
                                                        )}
                                                    </Badge>
                                                </div>
                                                <div>
                                                    <p className="text-muted-foreground">
                                                        验证状态
                                                    </p>
                                                    <p
                                                        className={`font-bold mt-1 ${selectedRule.correct ? "text-emerald-400" : "text-amber-400"}`}
                                                    >
                                                        {selectedRule.correct
                                                            ? "✓ 正确"
                                                            : "⚠ 未验证"}
                                                    </p>
                                                </div>
                                            </div>
                                        </div>

                                        {/* Pattern YAML */}
                                        <div className="space-y-3">
                                            <div className="flex items-center justify-between">
                                                <h3 className="font-mono font-bold uppercase text-sm text-muted-foreground">
                                                    规则模式
                                                </h3>
                                                <Button
                                                    size="sm"
                                                    variant="ghost"
                                                    onClick={() => {
                                                        navigator.clipboard.writeText(
                                                            selectedRule.pattern_yaml,
                                                        );
                                                        toast.success(
                                                            "已复制到剪贴板",
                                                        );
                                                    }}
                                                    className="cyber-btn-ghost h-7 text-xs"
                                                >
                                                    <Copy className="w-3 h-3" />
                                                </Button>
                                            </div>
                                            <div className="bg-muted border border-border rounded p-4">
                                                <pre className="text-xs font-mono text-foreground whitespace-pre-wrap break-words">
                                                    {selectedRule.pattern_yaml}
                                                </pre>
                                            </div>
                                        </div>

                                        {/* Patch Info */}
                                        {selectedRule.source === "patch" &&
                                            selectedRule.patch && (
                                                <div className="space-y-3">
                                                    <h3 className="font-mono font-bold uppercase text-sm text-muted-foreground border-b border-border pb-2">
                                                        生成来源
                                                    </h3>
                                                    <div className="bg-muted border border-border rounded p-4">
                                                        <pre className="text-xs font-mono text-foreground whitespace-pre-wrap break-words">
                                                            {selectedRule.patch}
                                                        </pre>
                                                    </div>
                                                </div>
                                            )}

                                        {/* Metadata */}
                                        <div className="space-y-3">
                                            <h3 className="font-mono font-bold uppercase text-sm text-muted-foreground border-b border-border pb-2">
                                                元数据
                                            </h3>
                                            <div className="text-sm font-mono text-muted-foreground">
                                                <p>
                                                    创建时间:{" "}
                                                    {new Date(
                                                        selectedRule.created_at,
                                                    ).toLocaleString("zh-CN")}
                                                </p>
                                            </div>
                                        </div>
                                    </div>
                                </div>
                            ) : null}

                            {/* Footer */}
                            <div className="flex-shrink-0 flex justify-end gap-3 px-6 py-4 bg-muted border-t border-border">
                                <Button
                                    variant="outline"
                                    onClick={() => setShowRuleDetail(false)}
                                    className="cyber-btn-outline"
                                >
                                    关闭
                                </Button>
                                <Button
                                    variant="outline"
                                    onClick={() =>
                                        selectedRule &&
                                        setPendingDeleteRule({
                                            id: selectedRule.id,
                                            name: selectedRule.name,
                                        })
                                    }
                                    className="cyber-btn-ghost hover:bg-rose-500/10 hover:text-rose-400"
                                >
                                    <Trash2 className="w-4 h-4 mr-2" />
                                    删除规则
                                </Button>
                            </div>
                        </DialogContent>
                    </Dialog>

                    <AlertDialog
                        open={Boolean(pendingDeleteRule)}
                        onOpenChange={(open) => {
                            if (!open && !deletingRule) {
                                setPendingDeleteRule(null);
                            }
                        }}
                    >
                        <AlertDialogContent className="cyber-dialog border-border max-w-md p-0 gap-0">
                            <AlertDialogHeader className="px-6 pt-5 pb-4 border-b border-border">
                                <AlertDialogTitle className="flex items-center gap-2">
                                    <AlertTriangle className="w-5 h-5 text-rose-400" />
                                    确认删除规则
                                </AlertDialogTitle>
                                <AlertDialogDescription className="pt-1">
                                    {pendingDeleteRule
                                        ? `将删除规则「${pendingDeleteRule.name}」，该操作不可恢复。`
                                        : "该操作不可恢复。"}
                                </AlertDialogDescription>
                            </AlertDialogHeader>
                            <AlertDialogFooter>
                                <AlertDialogCancel
                                    disabled={deletingRule}
                                    className="cyber-btn-outline"
                                >
                                    取消
                                </AlertDialogCancel>
                                <AlertDialogAction
                                    disabled={deletingRule}
                                    onClick={(event) => {
                                        event.preventDefault();
                                        handleDeleteRule();
                                    }}
                                    className="cyber-btn-primary"
                                >
                                    {deletingRule ? "删除中..." : "确认删除"}
                                </AlertDialogAction>
                            </AlertDialogFooter>
                        </AlertDialogContent>
                    </AlertDialog>

                    {/* Rule Type Dialog */}
                    <Dialog
                        open={showRuleTypeDialog}
                        onOpenChange={setShowRuleTypeDialog}
                    >
                        <DialogContent className="cyber-dialog max-w-xl border-border">
                            <DialogHeader className="px-6 pt-4 flex-shrink-0">
                                <DialogTitle className="font-mono text-lg uppercase tracking-wider text-foreground">
                                    选择规则类型
                                </DialogTitle>
                            </DialogHeader>

                            <div className="p-6 grid grid-cols-1 md:grid-cols-2 gap-4">
                                <Button
                                    variant="outline"
                                    className="h-auto flex flex-col items-start gap-2 p-4 cyber-btn-outline text-left"
                                    onClick={() => {
                                        setShowRuleTypeDialog(false);
                                        setShowGenericDialog(true);
                                    }}
                                >
                                    <span className="text-base font-bold text-foreground">
                                        通用型规则
                                    </span>
                                    <span className="text-xs text-muted-foreground font-mono">
                                        直接粘贴规则文本，自动校验格式
                                    </span>
                                </Button>
                                <Button
                                    variant="outline"
                                    className="h-auto flex flex-col items-start gap-2 p-4 cyber-btn-outline text-left"
                                    onClick={() => {
                                        setShowRuleTypeDialog(false);
                                        setShowEventDialog(true);
                                    }}
                                >
                                    <span className="text-base font-bold text-foreground">
                                        事件型规则
                                    </span>
                                    <span className="text-xs text-muted-foreground font-mono">
                                        基于Patch生成规则
                                    </span>
                                </Button>
                            </div>
                        </DialogContent>
                    </Dialog>

                    {/* Generic Rule Dialog */}
                    <Dialog
                        open={showGenericDialog}
                        onOpenChange={setShowGenericDialog}
                    >
                        <DialogContent className="cyber-dialog max-w-3xl border-border max-h-[90vh] flex flex-col">
                            <DialogHeader className="px-6 pt-4 flex-shrink-0">
                                <DialogTitle className="font-mono text-lg uppercase tracking-wider text-foreground">
                                    通用型规则
                                </DialogTitle>
                            </DialogHeader>

                            {/* Tab Selection */}
                            <div className="flex-shrink-0 px-6 flex gap-2 border-b border-border">
                                <button
                                    onClick={() => setGenericRuleUploadTab("manual")}
                                    className={`px-4 py-2 font-mono text-xs font-bold uppercase border-b-2 transition-colors ${
                                        genericRuleUploadTab === "manual"
                                            ? "border-primary text-primary"
                                            : "border-transparent text-muted-foreground hover:text-foreground"
                                    }`}
                                >
                                    手动上传
                                </button>
                                <button
                                    onClick={() => setGenericRuleUploadTab("compressed")}
                                    className={`px-4 py-2 font-mono text-xs font-bold uppercase border-b-2 transition-colors ${
                                        genericRuleUploadTab === "compressed"
                                            ? "border-primary text-primary"
                                            : "border-transparent text-muted-foreground hover:text-foreground"
                                    }`}
                                >
                                    压缩包上传
                                </button>
                                <button
                                    onClick={() => setGenericRuleUploadTab("directory")}
                                    className={`px-4 py-2 font-mono text-xs font-bold uppercase border-b-2 transition-colors ${
                                        genericRuleUploadTab === "directory"
                                            ? "border-primary text-primary"
                                            : "border-transparent text-muted-foreground hover:text-foreground"
                                    }`}
                                >
                                    目录上传
                                </button>
                            </div>

                            {/* Content Area */}
                            <div className="flex-1 overflow-y-auto p-6">
                                {/* Manual Upload Tab */}
                                {genericRuleUploadTab === "manual" && (
                                    <div className="space-y-4">
                                        <div className="grid grid-cols-2 gap-4">
                                            {/* Rule ID (Optional) */}
                                            <div>
                                                <Label className="font-mono font-bold uppercase text-xs text-muted-foreground">
                                                    规则 ID <span className="text-muted-foreground/60">(可选)</span>
                                                </Label>
                                                <Input
                                                    value={manualRuleForm.id}
                                                    onChange={(e) =>
                                                        setManualRuleForm({
                                                            ...manualRuleForm,
                                                            id: e.target.value,
                                                        })
                                                    }
                                                    placeholder="自动生成"
                                                    className="cyber-input mt-1.5 font-mono text-xs"
                                                />
                                            </div>

                                            {/* Rule Name (Required) */}
                                            <div>
                                                <Label className="font-mono font-bold uppercase text-xs text-muted-foreground">
                                                    规则名称 <span className="text-rose-400">*</span>
                                                </Label>
                                                <Input
                                                    value={manualRuleForm.name}
                                                    onChange={(e) =>
                                                        setManualRuleForm({
                                                            ...manualRuleForm,
                                                            name: e.target.value,
                                                        })
                                                    }
                                                    placeholder="例如: sql-injection-detector"
                                                    className="cyber-input mt-1.5 font-mono text-xs"
                                                />
                                            </div>

                                            {/* Language (Required) */}
                                            <div>
                                                <Label className="font-mono font-bold uppercase text-xs text-muted-foreground">
                                                    编程语言 <span className="text-rose-400">*</span>
                                                </Label>
                                                <Input
                                                    value={manualRuleForm.language}
                                                    onChange={(e) =>
                                                        setManualRuleForm({
                                                            ...manualRuleForm,
                                                            language: e.target.value,
                                                        })
                                                    }
                                                    placeholder="例如: python, javascript, java"
                                                    className="cyber-input mt-1.5 font-mono text-xs"
                                                />
                                            </div>

                                            {/* Severity */}
                                            <div>
                                                <Label className="font-mono font-bold uppercase text-xs text-muted-foreground">
                                                    严重程度
                                                </Label>
                                                <Select
                                                    value={manualRuleForm.severity}
                                                    onValueChange={(value) =>
                                                        setManualRuleForm({
                                                            ...manualRuleForm,
                                                            severity: value,
                                                        })
                                                    }
                                                >
                                                    <SelectTrigger className="cyber-input mt-1.5 font-mono text-xs">
                                                        <SelectValue />
                                                    </SelectTrigger>
                                                    <SelectContent>
                                                        <SelectItem value="ERROR">
                                                            ERROR
                                                        </SelectItem>
                                                        <SelectItem value="WARNING">
                                                            WARNING
                                                        </SelectItem>
                                                        <SelectItem value="INFO">
                                                            INFO
                                                        </SelectItem>
                                                    </SelectContent>
                                                </Select>
                                            </div>

                                            {/* Patch Link (Optional) */}
                                            <div className="col-span-2">
                                                <Label className="font-mono font-bold uppercase text-xs text-muted-foreground">
                                                    补丁或相关链接 <span className="text-muted-foreground/60">(可选)</span>
                                                </Label>
                                                <Input
                                                    value={manualRuleForm.patch}
                                                    onChange={(e) =>
                                                        setManualRuleForm({
                                                            ...manualRuleForm,
                                                            patch: e.target.value,
                                                        })
                                                    }
                                                    placeholder="https://example.com/patch"
                                                    className="cyber-input mt-1.5 font-mono text-xs"
                                                />
                                            </div>
                                        </div>

                                        {/* YAML Content (Required) */}
                                        <div>
                                            <Label className="font-mono font-bold uppercase text-xs text-muted-foreground">
                                                规则 YAML 内容 <span className="text-rose-400">*</span>
                                            </Label>
                                            <Textarea
                                                value={manualRuleForm.pattern_yaml}
                                                onChange={(e) =>
                                                    setManualRuleForm({
                                                        ...manualRuleForm,
                                                        pattern_yaml: e.target.value,
                                                    })
                                                }
                                                placeholder={
                                                    "规则 YAML 内容...\n\n示例:\nrules:\n  - id: my-rule\n    languages: [python]\n    pattern: $X = $Y\n    message: Found assignment"
                                                }
                                                className="cyber-input mt-1.5 font-mono text-xs min-h-56 cursor-text"
                                            />
                                        </div>

                                        {/* Checkboxes */}
                                        <div className="flex gap-4 items-center">
                                            <div className="flex items-center gap-2">
                                                <Checkbox
                                                    id="correct"
                                                    checked={manualRuleForm.correct}
                                                    onCheckedChange={(checked) =>
                                                        setManualRuleForm({
                                                            ...manualRuleForm,
                                                            correct: Boolean(checked),
                                                        })
                                                    }
                                                />
                                                <Label
                                                    htmlFor="correct"
                                                    className="font-mono text-xs text-muted-foreground cursor-pointer"
                                                >
                                                    规则正确
                                                </Label>
                                            </div>

                                            <div className="flex items-center gap-2">
                                                <Checkbox
                                                    id="is_active"
                                                    checked={manualRuleForm.is_active}
                                                    onCheckedChange={(checked) =>
                                                        setManualRuleForm({
                                                            ...manualRuleForm,
                                                            is_active: Boolean(checked),
                                                        })
                                                    }
                                                />
                                                <Label
                                                    htmlFor="is_active"
                                                    className="font-mono text-xs text-muted-foreground cursor-pointer"
                                                >
                                                    启用规则
                                                </Label>
                                            </div>
                                        </div>

                                        <p className="text-xs text-muted-foreground font-mono pt-2 border-t border-border">
                                            <span className="text-rose-400">*</span> 表示必填项，规则 YAML 必须包含 rules 数组和规则 id
                                        </p>
                                    </div>
                                )}

                                {/* Compressed Upload Tab */}
                                {genericRuleUploadTab === "compressed" && (
                                    <div className="space-y-4">
                                        <div>
                                            <Label className="font-mono font-bold uppercase text-xs text-muted-foreground">
                                                选择压缩文件
                                            </Label>
                                            <div className="mt-1.5 border-2 border-dashed border-border rounded-lg p-6 text-center hover:border-primary/50 transition-colors cursor-pointer"
                                                onClick={() => {
                                                    const input =
                                                        document.createElement(
                                                            "input",
                                                        );
                                                    input.type = "file";
                                                    input.accept =
                                                        ".zip,.tar,.tar.gz,.tgz,.tar.bz2,.7z,.rar";
                                                    input.onchange = (e) => {
                                                        const file = (e.target as HTMLInputElement)
                                                            .files?.[0];
                                                        if (file) {
                                                            setCompressedFile(file);
                                                        }
                                                    };
                                                    input.click();
                                                }}
                                            >
                                                {compressedFile ? (
                                                    <div>
                                                        <p className="text-sm font-mono text-primary">
                                                            ✓{" "}
                                                            {compressedFile.name}
                                                        </p>
                                                        <p className="text-xs text-muted-foreground mt-1">
                                                            ({(
                                                                compressedFile.size /
                                                                1024 /
                                                                1024
                                                            ).toFixed(2)}
                                                            MB)
                                                        </p>
                                                    </div>
                                                ) : (
                                                    <div>
                                                        <p className="text-sm font-mono text-muted-foreground">
                                                            点击选择或拖拽上传
                                                        </p>
                                                        <p className="text-xs text-muted-foreground mt-2">
                                                            支持: ZIP, TAR, TAR.GZ,
                                                            TAR.BZ2, 7Z, RAR
                                                        </p>
                                                    </div>
                                                )}
                                            </div>
                                        </div>
                                        <p className="text-xs text-muted-foreground font-mono">
                                            批量上传规则文件，系统会自动递归查找所有 YAML
                                            文件并进行去重处理
                                        </p>
                                    </div>
                                )}

                                {/* Directory Upload Tab */}
                                {genericRuleUploadTab === "directory" && (
                                    <div className="space-y-4">
                                        <div>
                                            <Label className="font-mono font-bold uppercase text-xs text-muted-foreground">
                                                选择规则文件
                                            </Label>
                                            <div className="mt-1.5 border-2 border-dashed border-border rounded-lg p-6 text-center hover:border-primary/50 transition-colors cursor-pointer"
                                                onClick={() => {
                                                    const input =
                                                        document.createElement(
                                                            "input",
                                                        );
                                                    input.type = "file";
                                                    input.multiple = true;
                                                    input.accept = ".yaml,.yml";
                                                    input.onchange = (e) => {
                                                        const files = Array.from(
                                                            (e.target as HTMLInputElement)
                                                                .files || [],
                                                        );
                                                        if (files.length > 0) {
                                                            setDirectoryFiles(files);
                                                        }
                                                    };
                                                    input.click();
                                                }}
                                            >
                                                {directoryFiles.length > 0 ? (
                                                    <div>
                                                        <p className="text-sm font-mono text-primary">
                                                            ✓ 已选择{" "}
                                                            {directoryFiles.length}{" "}
                                                             个文件
                                                        </p>
                                                        <div className="text-xs text-muted-foreground mt-2 space-y-1 max-h-32 overflow-y-auto">
                                                            {directoryFiles
                                                                .slice(0, 5)
                                                                .map((f) => (
                                                                    <p key={f.name}>
                                                                        {f.name}
                                                                    </p>
                                                                ))}
                                                            {directoryFiles.length >
                                                                5 && (
                                                                <p>
                                                                    ... 及其他{" "}
                                                                    {directoryFiles.length -
                                                                        5}{" "}
                                                                    个文件
                                                                </p>
                                                            )}
                                                        </div>
                                                    </div>
                                                ) : (
                                                    <div>
                                                        <p className="text-sm font-mono text-muted-foreground">
                                                            点击选择或拖拽上传
                                                        </p>
                                                        <p className="text-xs text-muted-foreground mt-2">
                                                            支持选择多个
                                                            YAML/YML 规则文件
                                                        </p>
                                                    </div>
                                                )}
                                            </div>
                                        </div>
                                        <p className="text-xs text-muted-foreground font-mono">
                                            选择一个或多个规则文件，支持批量上传和自动去重
                                        </p>
                                    </div>
                                )}
                            </div>

                            {/* Footer */}
                            <div className="flex-shrink-0 flex justify-between gap-3 px-6 py-4 bg-muted border-t border-border">
                                <Button
                                    variant="outline"
                                    onClick={() => {
                                        setShowGenericDialog(false);
                                        setShowRuleTypeDialog(true);
                                        setGenericRuleUploadTab("manual");
                                        setManualRuleForm({
                                            id: "",
                                            name: "",
                                            language: "python",
                                            pattern_yaml: "",
                                            severity: "WARNING",
                                            source: "json",
                                            patch: "",
                                            correct: true,
                                            is_active: true,
                                        });
                                        setCompressedFile(null);
                                        setDirectoryFiles([]);
                                    }}
                                    className="cyber-btn-outline"
                                    disabled={uploadingRules}
                                >
                                    返回
                                </Button>
                                <div className="flex gap-3">
                                    <Button
                                        onClick={() => {
                                            if (genericRuleUploadTab === "manual") {
                                                handleGenerateGenericRule();
                                            } else if (
                                                genericRuleUploadTab === "compressed"
                                            ) {
                                                handleUploadCompressedRules();
                                            } else {
                                                handleUploadDirectoryRules();
                                            }
                                        }}
                                        className="cyber-btn-primary"
                                        disabled={
                                            uploadingRules ||
                                            (genericRuleUploadTab === "manual" &&
                                                (!manualRuleForm.name.trim() ||
                                                    !manualRuleForm.pattern_yaml.trim() ||
                                                    !manualRuleForm.language.trim())) ||
                                            (genericRuleUploadTab ===
                                                "compressed" &&
                                                !compressedFile) ||
                                            (genericRuleUploadTab ===
                                                "directory" &&
                                                directoryFiles.length === 0)
                                        }
                                    >
                                        {uploadingRules ? (
                                            <>
                                                <div className="loading-spinner mr-2" />
                                                上传中...
                                            </>
                                        ) : (
                                            `${
                                                genericRuleUploadTab ===
                                                "manual"
                                                    ? "生成规则"
                                                    : "上传规则"
                                            }`
                                        )}
                                    </Button>
                                </div>
                            </div>
                        </DialogContent>
                    </Dialog>
                    {/* Event Rule Dialog */}
                    <Dialog
                        open={showEventDialog}
                        onOpenChange={setShowEventDialog}
                    >
                        <DialogContent className="cyber-dialog max-w-2xl border-border">
                            <div
                                className="absolute inset-0 opacity-5 pointer-events-none"
                                style={{
                                    backgroundImage:
                                        "repeating-linear-gradient(0deg, transparent, transparent 2px, rgba(34, 197, 94, 0.1) 2px, rgba(34, 197, 94, 0.1) 4px)",
                                    backgroundSize: "100% 4px",
                                }}
                            />
                            <DialogHeader className="px-6 pt-4 flex-shrink-0">
                                <DialogTitle className="font-mono text-lg uppercase tracking-wider flex items-center gap-2 text-foreground">
                                    事件型规则
                                </DialogTitle>
                            </DialogHeader>

                            <div className="flex-1 overflow-y-auto p-6 space-y-4">
                                <div>
                                    <Label className="font-mono font-bold uppercase text-xs text-muted-foreground">
                                        仓库所有者
                                    </Label>
                                    <Input
                                        value={generateFormData.repo_owner}
                                        onChange={(e) =>
                                            setGenerateFormData({
                                                ...generateFormData,
                                                repo_owner: e.target.value,
                                            })
                                        }
                                        placeholder="例如: owner"
                                        className="cyber-input mt-1.5"
                                    />
                                </div>

                                <div>
                                    <Label className="font-mono font-bold uppercase text-xs text-muted-foreground">
                                        仓库名称
                                    </Label>
                                    <Input
                                        value={generateFormData.repo_name}
                                        onChange={(e) =>
                                            setGenerateFormData({
                                                ...generateFormData,
                                                repo_name: e.target.value,
                                            })
                                        }
                                        placeholder="例如: repository"
                                        className="cyber-input mt-1.5"
                                    />
                                </div>

                                <div>
                                    <Label className="font-mono font-bold uppercase text-xs text-muted-foreground">
                                        提交哈希
                                    </Label>
                                    <Input
                                        value={generateFormData.commit_hash}
                                        onChange={(e) =>
                                            setGenerateFormData({
                                                ...generateFormData,
                                                commit_hash: e.target.value,
                                            })
                                        }
                                        placeholder="例如: abc123def456"
                                        className="cyber-input mt-1.5"
                                    />
                                </div>

                                <div>
                                    <Label className="font-mono font-bold uppercase text-xs text-muted-foreground">
                                        Patch内容
                                    </Label>
                                    <Textarea
                                        value={generateFormData.commit_content}
                                        onChange={(e) =>
                                            setGenerateFormData({
                                                ...generateFormData,
                                                commit_content: e.target.value,
                                            })
                                        }
                                        placeholder="粘贴补丁内容..."
                                        className="cyber-input mt-1.5 font-mono text-xs min-h-48 cursor-text"
                                    />
                                </div>
                            </div>

                            <div className="flex-shrink-0 flex justify-between gap-3 px-6 py-4 bg-muted border-t border-border">
                                <Button
                                    variant="outline"
                                    onClick={() => {
                                        setShowEventDialog(false);
                                        setShowRuleTypeDialog(true);
                                    }}
                                    className="cyber-btn-outline"
                                    disabled={generatingRule}
                                >
                                    返回
                                </Button>
                                <div className="flex items-center gap-3">
                                    <Button
                                        variant="outline"
                                        onClick={() =>
                                            setShowEventDialog(false)
                                        }
                                        className="cyber-btn-outline"
                                        disabled={generatingRule}
                                    >
                                        取消
                                    </Button>
                                    <Button
                                        onClick={handleGenerateRule}
                                        className="cyber-btn-primary"
                                        disabled={generatingRule}
                                    >
                                        {generatingRule ? (
                                            <>
                                                <div className="loading-spinner mr-2" />
                                                生成中...
                                            </>
                                        ) : (
                                            <>生成规则</>
                                        )}
                                    </Button>
                                </div>
                            </div>
                        </DialogContent>
                    </Dialog>
                </div>
            </div>
        </div>
    );
}
