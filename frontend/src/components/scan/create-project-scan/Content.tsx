import type { ChangeEvent } from "react";
import { useI18n } from "@/shared/i18n";
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
import {
    Select,
    SelectContent,
    SelectItem,
    SelectTrigger,
    SelectValue,
} from "@/components/ui/select";
import {
    Bot,
    CheckCircle2,
    Loader2,
    Settings2,
    Shield,
    TerminalSquare,
    Upload,
    Zap,
} from "lucide-react";
import type { Project } from "@/shared/types";
import type { PreflightMissingField } from "@/shared/api/agentPreflight";
import { SUPPORTED_ARCHIVE_INPUT_ACCEPT } from "@/features/projects/services/repoZipScan";
import {
    getCreateProjectScanProviderLabel,
    type LLMProviderItem,
} from "@/shared/llm/providerCatalog";

import type { StaticTool } from "@/components/agent/AgentModeSelector";
import StaticEngineConfigDialog from "@/components/scan/create-scan-task/StaticEngineConfigDialog";
import { normalizeCreateProjectScanProvider } from "./utils";

type LlmQuickConfig = {
    provider: string;
    model: string;
    baseUrl: string;
    apiKey: string;
};

export default function CreateProjectScanDialogContent({
    open,
    onOpenChange,
    dialogTitle,
    allowUploadProject,
    sourceMode,
    setSourceMode,
    creating,
    lockMode,
    mode,
    setMode,
    loadingProjects,
    lockProjectSelection,
    searchTerm,
    setSearchTerm,
    filteredProjects,
    visibleProjects,
    projectPage,
    projectTotalPages,
    setProjectPage,
    selectedProject,
    selectedProjectId,
    setSelectedProjectId,
    newProjectName,
    setNewProjectName,
    newProjectFile,
    handleNewProjectFileSelect,
    opengrepEnabled,
    setOpengrepEnabled,
    isPmdBlockedProject,
    pmdBlockedMessage,
    showLlmQuickFixPanel,
    openLlmQuickFixPanelManual,
    quickFixSaving,
    quickFixTesting,
    quickFixPanelOpening,
    lastPreflightMessage,
    llmProviderOptions,
    llmQuickConfig,
    missingFieldClass,
    handleQuickFixProviderChange,
    handleQuickFixConfigChange,
    quickFixTestResult,
    disableQuickFixTest,
    llmTestBlockedMessage,
    handleQuickFixTest,
    handleQuickFixSave,
    showReturnButton,
    onReturn,
    primaryCreateLabel,
    secondaryCreateLabel,
    createButtonVariant,
    canCreate,
    handleCreate,
    configEngine,
    setConfigEngine,
    onNavigateToEngineConfig,
    onNavigateToAdvancedLlmConfig,
}: {
    open: boolean;
    onOpenChange: (open: boolean) => void;
    dialogTitle: string;
    allowUploadProject: boolean;
    sourceMode: "existing" | "upload";
    setSourceMode: (mode: "existing" | "upload") => void;
    creating: boolean;
    lockMode: boolean;
    mode: "static" | "agent";
    setMode: (mode: "static" | "agent") => void;
    loadingProjects: boolean;
    lockProjectSelection: boolean;
    searchTerm: string;
    setSearchTerm: (value: string) => void;
    filteredProjects: Project[];
    visibleProjects: Project[];
    projectPage: number;
    projectTotalPages: number;
    setProjectPage: (page: number) => void;
    selectedProject: Project | undefined;
    selectedProjectId: string;
    setSelectedProjectId: (id: string) => void;
    newProjectName: string;
    setNewProjectName: (value: string) => void;
    newProjectFile: File | null;
    handleNewProjectFileSelect: (event: ChangeEvent<HTMLInputElement>) => void;
    opengrepEnabled: boolean;
    setOpengrepEnabled: (enabled: boolean) => void;
    gitleaksEnabled: boolean;
    setGitleaksEnabled: (enabled: boolean) => void;
    banditEnabled: boolean;
    setBanditEnabled: (enabled: boolean) => void;
    phpstanEnabled: boolean;
    setPhpstanEnabled: (enabled: boolean) => void;
    pmdEnabled: boolean;
    setPmdEnabled: (enabled: boolean) => void;
    isPmdBlockedProject: boolean;
    pmdBlockedMessage: string;
    showLlmQuickFixPanel: boolean;
    openLlmQuickFixPanelManual: () => void | Promise<void>;
    quickFixSaving: boolean;
    quickFixTesting: boolean;
    quickFixPanelOpening: boolean;
    lastPreflightMessage: string;
    llmProviderOptions: LLMProviderItem[];
    llmQuickConfig: LlmQuickConfig;
    missingFieldClass: (field: PreflightMissingField) => string;
    handleQuickFixProviderChange: (provider: string) => void;
    handleQuickFixConfigChange: (
        key: keyof LlmQuickConfig,
        value: string,
    ) => void;
    quickFixTestResult: {
        success: boolean;
        message: string;
        model?: string;
    } | null;
    disableQuickFixTest: boolean;
    llmTestBlockedMessage: string;
    handleQuickFixTest: () => void | Promise<void>;
    handleQuickFixSave: () => void | Promise<void>;
    showReturnButton: boolean;
    onReturn?: () => void;
    primaryCreateLabel: string;
    secondaryCreateLabel: string;
    createButtonVariant: "single" | "dual";
    canCreate: boolean;
    handleCreate: (action?: "primary" | "secondary") => void | Promise<void>;
    configEngine: StaticTool | null;
    setConfigEngine: (engine: StaticTool | null) => void;
    onNavigateToEngineConfig: (engine: StaticTool) => void;
    onNavigateToAdvancedLlmConfig: () => void;
}) {
    const { t } = useI18n();
    const shouldShowAgentPrecheckHint = mode === "agent";
    const staticEngineItems: Array<{
        key: StaticTool;
        title: string;
        checked: boolean;
        setChecked: (enabled: boolean) => void;
    }> = [
        {
            key: "opengrep",
            title: "Opengrep",
            checked: opengrepEnabled,
            setChecked: setOpengrepEnabled,
        },
    ];

    return (
        <>
            <Dialog open={open} onOpenChange={onOpenChange}>
                <DialogContent
                    aria-describedby={undefined}
                    className="!w-[min(92vw,760px)] !max-w-none max-h-[88vh] p-0 gap-0 flex flex-col cyber-dialog border border-border rounded-lg"
                >
                    <DialogHeader className="px-6 py-4 border-b border-border bg-muted">
                        <DialogTitle className="flex items-center gap-3 font-mono">
                            <div className="p-2 rounded border border-sky-500/30 bg-sky-500/10">
                                <TerminalSquare className="w-5 h-5 text-sky-300" />
                            </div>
                            <div>
                                <p className="text-base font-bold uppercase tracking-wider text-foreground">
                                    {dialogTitle}
                                </p>
                            </div>
                        </DialogTitle>
                    </DialogHeader>

                    <div className="p-6 space-y-5 overflow-y-auto flex-1">
                        {allowUploadProject && (
                            <div className="space-y-2">
                                <p className="text-xs uppercase tracking-wider text-muted-foreground">
                                    项目来源
                                </p>
                                <div className="grid grid-cols-2 gap-2">
                                    <Button
                                        type="button"
                                        variant={
                                            sourceMode === "existing"
                                                ? "default"
                                                : "outline"
                                        }
                                        className={
                                            sourceMode === "existing"
                                                ? "cyber-btn-primary h-10"
                                                : "cyber-btn-outline h-10"
                                        }
                                        onClick={() =>
                                            setSourceMode("existing")
                                        }
                                        disabled={creating}
                                    >
                                        选择已有项目
                                    </Button>
                                    <Button
                                        type="button"
                                        variant={
                                            sourceMode === "upload"
                                                ? "default"
                                                : "outline"
                                        }
                                        className={
                                            sourceMode === "upload"
                                                ? "cyber-btn-primary h-10"
                                                : "cyber-btn-outline h-10"
                                        }
                                        onClick={() => setSourceMode("upload")}
                                        disabled={creating}
                                    >
                                        上传新项目
                                    </Button>
                                </div>
                            </div>
                        )}

                        {!lockMode && (
                            <div className="space-y-2">
                                <p className="text-xs uppercase tracking-wider text-muted-foreground">
                                    扫描方式
                                </p>
                                {/* PHPStan integration: keep the same static-engine card layout */}
                                <div className="grid grid-cols-1 md:grid-cols-2 gap-2">
                                    <Button
                                        type="button"
                                        variant={
                                            mode === "static"
                                                ? "default"
                                                : "outline"
                                        }
                                        className={
                                            mode === "static"
                                                ? "cyber-btn-primary h-10 justify-start"
                                                : "cyber-btn-outline h-10 justify-start"
                                        }
                                        onClick={() => setMode("static")}
                                        disabled={creating}
                                    >
                                        <Zap className="w-4 h-4 mr-2" />
                                        静态审计
                                    </Button>
                                    <Button
                                        type="button"
                                        variant={
                                            mode === "agent"
                                                ? "default"
                                                : "outline"
                                        }
                                        className={
                                            mode === "agent"
                                                ? "h-10 justify-start border border-violet-500/40 bg-violet-500/20 text-violet-100 hover:bg-violet-500/30"
                                                : "cyber-btn-outline h-10 justify-start"
                                        }
                                        onClick={() => setMode("agent")}
                                        disabled={creating}
                                    >
                                        <Bot className="w-4 h-4 mr-2" />
                                        智能审计
                                    </Button>
                                </div>
                            </div>
                        )}

                        {sourceMode === "existing" ? (
                            <div className="space-y-3">
                                {lockProjectSelection ? null : (
                                    <Input
                                        value={searchTerm}
                                        onChange={(event) =>
                                            setSearchTerm(event.target.value)
                                        }
                                        placeholder="搜索项目..."
                                        className="h-9 cyber-input"
                                        disabled={creating}
                                    />
                                )}
                                <div className="border border-border rounded-lg p-2 space-y-2">
                                    {loadingProjects ? (
                                        <div className="py-10 flex items-center justify-center text-sm text-muted-foreground">
                                            <Loader2 className="w-4 h-4 animate-spin mr-2" />
                                            加载项目中...
                                        </div>
                                    ) : lockProjectSelection ? (
                                        selectedProject ? (
                                            <div className="w-full text-left p-3 rounded border border-sky-500/50 bg-sky-500/10">
                                                <div className="flex items-start justify-between gap-3">
                                                    <div className="min-w-0">
                                                        <p className="text-sm font-semibold text-foreground">
                                                            {
                                                                selectedProject.name
                                                            }
                                                        </p>
                                                        {selectedProject.description && (
                                                            <p className="text-xs text-muted-foreground mt-1 line-clamp-1">
                                                                {
                                                                    selectedProject.description
                                                                }
                                                            </p>
                                                        )}
                                                    </div>
                                                    <div className="flex items-center gap-2 shrink-0">
                                                        <Badge
                                                            className={
                                                                selectedProject.source_type ===
                                                                "zip"
                                                                    ? "cyber-badge-warning"
                                                                    : "cyber-badge-info"
                                                            }
                                                        >
                                                            {selectedProject.source_type ===
                                                            "zip"
                                                                ? "ZIP"
                                                                : "仓库"}
                                                        </Badge>
                                                        <CheckCircle2 className="w-4 h-4 text-sky-400" />
                                                    </div>
                                                </div>
                                            </div>
                                        ) : (
                                            <div className="py-10 text-center text-sm text-muted-foreground">
                                                目标项目不可用，请返回项目管理页重试
                                            </div>
                                        )
                                    ) : filteredProjects.length > 0 ? (
                                        visibleProjects.map((project) => (
                                            <button
                                                key={project.id}
                                                type="button"
                                                onClick={() =>
                                                    setSelectedProjectId(
                                                        project.id,
                                                    )
                                                }
                                                className={`w-full text-left p-3 rounded border transition-colors ${
                                                    project.id ===
                                                    selectedProjectId
                                                        ? "border-sky-500/50 bg-sky-500/10"
                                                        : "border-border hover:border-sky-500/30 bg-background"
                                                }`}
                                                disabled={creating}
                                            >
                                                <div className="flex items-start justify-between gap-3">
                                                    <div className="min-w-0">
                                                        <p className="text-sm font-semibold text-foreground">
                                                            {project.name}
                                                        </p>
                                                        {project.description && (
                                                            <p className="text-xs text-muted-foreground mt-1 line-clamp-1">
                                                                {
                                                                    project.description
                                                                }
                                                            </p>
                                                        )}
                                                    </div>
                                                </div>
                                            </button>
                                        ))
                                    ) : (
                                        <div className="py-10 text-center text-sm text-muted-foreground">
                                            未找到可用项目
                                        </div>
                                    )}
                                </div>
                                {!lockProjectSelection &&
                                    filteredProjects.length > 0 && (
                                        <div className="flex items-center justify-between gap-3 text-xs text-muted-foreground">
                                            <span>每页 3 个项目卡片</span>
                                            <div className="flex items-center gap-2">
                                                <Button
                                                    type="button"
                                                    variant="outline"
                                                    className="cyber-btn-outline h-8 px-3"
                                                    onClick={() =>
                                                        setProjectPage(
                                                            Math.max(
                                                                1,
                                                                projectPage - 1,
                                                            ),
                                                        )
                                                    }
                                                    disabled={
                                                        creating ||
                                                        projectPage <= 1
                                                    }
                                                >
                                                    上一页
                                                </Button>
                                                <span>
                                                    第 {projectPage} /{" "}
                                                    {projectTotalPages} 页
                                                </span>
                                                <Button
                                                    type="button"
                                                    variant="outline"
                                                    className="cyber-btn-outline h-8 px-3"
                                                    onClick={() =>
                                                        setProjectPage(
                                                            Math.min(
                                                                projectTotalPages,
                                                                projectPage + 1,
                                                            ),
                                                        )
                                                    }
                                                    disabled={
                                                        creating ||
                                                        projectPage >=
                                                            projectTotalPages
                                                    }
                                                >
                                                    下一页
                                                </Button>
                                            </div>
                                        </div>
                                    )}
                            </div>
                        ) : (
                            <div className="space-y-3 border border-border rounded-lg p-4">
                                <div>
                                    <p className="text-xs uppercase tracking-wider text-muted-foreground mb-1">
                                        项目名称
                                    </p>
                                    <Input
                                        value={newProjectName}
                                        onChange={(event) =>
                                            setNewProjectName(
                                                event.target.value,
                                            )
                                        }
                                        placeholder="请输入项目名称"
                                        className="h-9 cyber-input"
                                        disabled={creating}
                                    />
                                </div>
                                <div>
                                    <p className="text-xs uppercase tracking-wider text-muted-foreground mb-2">
                                        源码压缩包
                                    </p>
                                    <label className="inline-flex">
                                        <input
                                            type="file"
                                            accept={
                                                SUPPORTED_ARCHIVE_INPUT_ACCEPT
                                            }
                                            className="hidden"
                                            onChange={
                                                handleNewProjectFileSelect
                                            }
                                            disabled={creating}
                                        />
                                        <span className="cyber-btn-outline h-9 px-3 inline-flex items-center cursor-pointer">
                                            <Upload className="w-4 h-4 mr-2" />
                                            选择压缩包
                                        </span>
                                    </label>
                                    {newProjectFile && (
                                        <p className="text-xs text-emerald-400 mt-2">
                                            {newProjectFile.name}
                                        </p>
                                    )}
                                </div>
                            </div>
                        )}

                        {mode === "static" ? (
                            <div className="border border-border rounded-lg p-4 space-y-3">
                                <div className="flex items-center justify-between">
                                    <p className="text-sm font-semibold text-foreground">
                                        静态审计引擎
                                    </p>
                                </div>
                                <div className="grid grid-cols-1 md:grid-cols-3 gap-2">
                                    {staticEngineItems.map((item) => (
                                        <div
                                            key={item.key}
                                            className="border border-border rounded p-3 flex items-center justify-between gap-3 hover:border-sky-500/30"
                                        >
                                            <label className="flex min-w-0 items-center gap-3 cursor-pointer">
                                                <Checkbox
                                                    checked={item.checked}
                                                    onCheckedChange={(
                                                        checked,
                                                    ) =>
                                                        item.setChecked(
                                                            Boolean(checked),
                                                        )
                                                    }
                                                    disabled={creating}
                                                    className="data-[state=checked]:bg-sky-500 data-[state=checked]:border-sky-500"
                                                />
                                                <div>
                                                    <p className="text-sm text-foreground font-semibold">
                                                        {item.title}
                                                    </p>
                                                </div>
                                            </label>
                                            <Button
                                                type="button"
                                                variant="ghost"
                                                size="icon"
                                                className="h-8 w-8 shrink-0 text-muted-foreground hover:text-foreground hover:bg-sky-500/10"
                                                onClick={() =>
                                                    setConfigEngine(item.key)
                                                }
                                                disabled={creating}
                                                aria-label={`配置 ${item.title} 引擎`}
                                            >
                                                <Settings2 className="h-4 w-4" />
                                            </Button>
                                        </div>
                                    ))}
                                </div>
                            </div>
                        ) : null}

                        {shouldShowAgentPrecheckHint && (
                            <div className="space-y-3">
                                <div className="rounded-lg border border-violet-500/20 bg-violet-500/5 p-3">
                                    <div className="flex items-start justify-between gap-3">
                                        <div>
                                            <p className="text-sm text-violet-200">
                                                {t(
                                                    "task.llmPrecheckHint",
                                                    "LLM 配置自动化验证",
                                                )}
                                            </p>
                                        </div>
                                        <Button
                                            type="button"
                                            variant="outline"
                                            className="cyber-btn-outline h-8 shrink-0"
                                            onClick={openLlmQuickFixPanelManual}
                                            disabled={
                                                creating ||
                                                quickFixSaving ||
                                                quickFixTesting ||
                                                quickFixPanelOpening
                                            }
                                        >
                                            {quickFixPanelOpening ? (
                                                <>
                                                    <Loader2 className="w-3.5 h-3.5 animate-spin mr-1.5" />
                                                    加载中...
                                                </>
                                            ) : showLlmQuickFixPanel ? (
                                                t(
                                                    "task.llmConfigCollapse",
                                                    "收起配置",
                                                )
                                            ) : (
                                                t(
                                                    "task.llmConfigTest",
                                                    "配置测试",
                                                )
                                            )}
                                        </Button>
                                    </div>
                                </div>

                                {showLlmQuickFixPanel && (
                                    <div className="rounded-lg border border-amber-500/30 bg-amber-500/5 p-4 space-y-3">
                                        <div className="flex items-start justify-between gap-2">
                                            <div className="space-y-1">
                                                <p className="text-sm font-semibold text-amber-100">
                                                    {t(
                                                        "task.llmQuickFixTitle",
                                                        "LLM 快速补配",
                                                    )}
                                                </p>
                                                <p className="text-xs text-amber-200/85 leading-relaxed">
                                                    {lastPreflightMessage ||
                                                        t(
                                                            "task.llmQuickFixDesc",
                                                            "未通过时可在下方直接补配并测试连接。",
                                                        )}
                                                </p>
                                            </div>
                                            <Badge className="cyber-badge-info uppercase">
                                                {getCreateProjectScanProviderLabel(
                                                    llmProviderOptions.find(
                                                        (provider) =>
                                                            provider.id ===
                                                            normalizeCreateProjectScanProvider(
                                                                llmQuickConfig.provider,
                                                            ),
                                                    ),
                                                ) ||
                                                    normalizeCreateProjectScanProvider(
                                                        llmQuickConfig.provider,
                                                    )}
                                            </Badge>
                                        </div>
                                        <Button
                                            type="button"
                                            variant="ghost"
                                            className="h-8 px-2 text-xs text-amber-100 hover:bg-amber-500/10"
                                            onClick={onNavigateToAdvancedLlmConfig}
                                            disabled={creating || quickFixSaving || quickFixTesting}
                                        >
                                            <Settings2 className="mr-1.5 h-3.5 w-3.5" />
                                            高级配置
                                        </Button>

                                        <div className="grid grid-cols-1 gap-3">
                                            <div className="grid grid-cols-1 gap-3 sm:grid-cols-[minmax(0,180px)_minmax(0,1fr)]">
                                                <div className="space-y-1">
                                                    <p className="text-xs uppercase tracking-wider text-muted-foreground">
                                                        提供商
                                                    </p>
                                                    <Select
                                                        value={normalizeCreateProjectScanProvider(
                                                            llmQuickConfig.provider,
                                                        )}
                                                        onValueChange={
                                                            handleQuickFixProviderChange
                                                        }
                                                        disabled={
                                                            creating ||
                                                            quickFixSaving ||
                                                            quickFixTesting
                                                        }
                                                    >
                                                        <SelectTrigger className="h-9 cyber-input">
                                                            <SelectValue placeholder="选择提供商" />
                                                        </SelectTrigger>
                                                        <SelectContent>
                                                            {llmProviderOptions.map(
                                                                (provider) => (
                                                                    <SelectItem
                                                                        key={
                                                                            provider.id
                                                                        }
                                                                        value={
                                                                            provider.id
                                                                        }
                                                                    >
                                                                        {getCreateProjectScanProviderLabel(
                                                                            provider,
                                                                        )}
                                                                    </SelectItem>
                                                                ),
                                                            )}
                                                        </SelectContent>
                                                    </Select>
                                                </div>

                                                <div className="space-y-1">
                                                    <p className="text-xs uppercase tracking-wider text-muted-foreground">
                                                        模型
                                                    </p>
                                                    <Input
                                                        value={
                                                            llmQuickConfig.model
                                                        }
                                                        onChange={(event) =>
                                                            handleQuickFixConfigChange(
                                                                "model",
                                                                event.target
                                                                    .value,
                                                            )
                                                        }
                                                        placeholder="例如：gpt-5"
                                                        className={`h-9 cyber-input ${missingFieldClass("llmModel")}`}
                                                        disabled={
                                                            creating ||
                                                            quickFixSaving ||
                                                            quickFixTesting
                                                        }
                                                    />
                                                </div>
                                            </div>

                                            <div className="space-y-1">
                                                <p className="text-xs uppercase tracking-wider text-muted-foreground">
                                                    Base URL
                                                </p>
                                                <Input
                                                    value={
                                                        llmQuickConfig.baseUrl
                                                    }
                                                    onChange={(event) =>
                                                        handleQuickFixConfigChange(
                                                            "baseUrl",
                                                            event.target.value,
                                                        )
                                                    }
                                                    placeholder="例如：https://api.openai.com/v1"
                                                    className={`h-9 cyber-input ${missingFieldClass("llmBaseUrl")}`}
                                                    disabled={
                                                        creating ||
                                                        quickFixSaving ||
                                                        quickFixTesting
                                                    }
                                                />
                                            </div>

                                            <div className="space-y-1">
                                                <p className="text-xs uppercase tracking-wider text-muted-foreground">
                                                    Token
                                                </p>
                                                <Input
                                                    type="password"
                                                    value={
                                                        llmQuickConfig.apiKey
                                                    }
                                                    onChange={(event) =>
                                                        handleQuickFixConfigChange(
                                                            "apiKey",
                                                            event.target.value,
                                                        )
                                                    }
                                                    placeholder={
                                                        "请输入 API Key"
                                                    }
                                                    className={`h-9 cyber-input ${missingFieldClass("llmApiKey")}`}
                                                    disabled={
                                                        creating ||
                                                        quickFixSaving ||
                                                        quickFixTesting
                                                    }
                                                />
                                            </div>
                                        </div>

                                        {llmTestBlockedMessage ? (
                                            <p className="text-xs text-amber-200/90">
                                                {llmTestBlockedMessage}
                                            </p>
                                        ) : null}

                                        {quickFixTestResult && (
                                            <p
                                                className={`text-xs ${
                                                    quickFixTestResult.success
                                                        ? "text-emerald-300"
                                                        : "text-rose-300"
                                                }`}
                                            >
                                                {quickFixTestResult.success
                                                    ? `测试成功：${quickFixTestResult.model || llmQuickConfig.model}`
                                                    : `测试失败：${quickFixTestResult.message}`}
                                            </p>
                                        )}

                                        <div className="flex items-center justify-end gap-2">
                                            <Button
                                                type="button"
                                                variant="outline"
                                                className="cyber-btn-outline h-9"
                                                onClick={handleQuickFixTest}
                                                disabled={
                                                    creating ||
                                                    quickFixSaving ||
                                                    quickFixTesting ||
                                                    disableQuickFixTest
                                                }
                                            >
                                                {quickFixTesting ? (
                                                    <>
                                                        <Loader2 className="w-4 h-4 animate-spin mr-2" />
                                                        测试中...
                                                    </>
                                                ) : (
                                                    "测试连接"
                                                )}
                                            </Button>
                                            <Button
                                                type="button"
                                                className="cyber-btn-primary h-9"
                                                onClick={handleQuickFixSave}
                                                disabled={
                                                    creating ||
                                                    quickFixSaving ||
                                                    quickFixTesting
                                                }
                                            >
                                                {quickFixSaving ? (
                                                    <>
                                                        <Loader2 className="w-4 h-4 animate-spin mr-2" />
                                                        保存中...
                                                    </>
                                                ) : (
                                                    "保存配置"
                                                )}
                                            </Button>
                                        </div>
                                    </div>
                                )}
                            </div>
                        )}
                    </div>

                    <div className="px-6 py-4 border-t border-border bg-muted flex justify-end gap-2">
                        {showReturnButton && onReturn && (
                            <Button
                                type="button"
                                variant="outline"
                                className="cyber-btn-outline"
                                onClick={onReturn}
                                disabled={creating}
                            >
                                返回
                            </Button>
                        )}
                        <Button
                            type="button"
                            variant="outline"
                            className="cyber-btn-outline"
                            onClick={() => onOpenChange(false)}
                            disabled={creating}
                        >
                            取消
                        </Button>
                        <Button
                            type="button"
                            className="cyber-btn-primary"
                            onClick={() => handleCreate("primary")}
                            disabled={!canCreate || creating}
                        >
                            {creating ? (
                                <>
                                    <Loader2 className="w-4 h-4 animate-spin mr-2" />
                                    创建中...
                                </>
                            ) : (
                                <>
                                    <Shield className="w-4 h-4 mr-2" />
                                    {primaryCreateLabel}
                                </>
                            )}
                        </Button>
                        {createButtonVariant === "dual" && (
                            <Button
                                type="button"
                                className="cyber-btn-primary"
                                onClick={() => handleCreate("secondary")}
                                disabled={!canCreate || creating}
                            >
                                {creating ? (
                                    <>
                                        <Loader2 className="w-4 h-4 animate-spin mr-2" />
                                        创建中...
                                    </>
                                ) : (
                                    <>
                                        <Shield className="w-4 h-4 mr-2" />
                                        {secondaryCreateLabel}
                                    </>
                                )}
                            </Button>
                        )}
                    </div>
                </DialogContent>
            </Dialog>
            <StaticEngineConfigDialog
                engine={configEngine ?? "opengrep"}
                open={configEngine !== null}
                onOpenChange={(nextOpen) => {
                    if (!nextOpen) setConfigEngine(null);
                }}
                scanMode="static"
                enabled={
                    configEngine
                        ? (staticEngineItems.find(
                              (item) => item.key === configEngine,
                          )?.checked ?? false)
                        : false
                }
                creating={creating}
                blockedReason={
                    configEngine === "pmd"
                        ? isPmdBlockedProject
                            ? pmdBlockedMessage
                            : null
                        : null
                }
                onNavigateToEngineConfig={onNavigateToEngineConfig}
            />
        </>
    );
}
