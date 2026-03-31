import { useEffect, useMemo, useState } from "react";
import type { ColumnDef } from "@tanstack/react-table";
import { toast } from "sonner";
import { Code2, Copy, Database, Shield, Tag } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
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
	areDataTableQueryStatesEqual,
	DataTable,
	type AppColumnDef,
	type DataTableQueryState,
	type DataTableSelectionContext,
	useDataTableUrlState,
} from "@/components/data-table";
import {
	importYasaRuleConfig,
	updateYasaRuntimeConfig,
	type YasaRule,
	type YasaRuleConfig,
	type YasaRuntimeConfig,
} from "@/shared/api/yasa";
import {
	loadYasaRulesPageData,
	YASA_CUSTOM_RULE_CONFIGS_LOAD_ERROR_FALLBACK,
	YASA_RUNTIME_CONFIG_LOAD_ERROR_FALLBACK,
	type YasaRulesLoaderResult,
} from "@/pages/yasaRulesLoader";
import {
	SCAN_ENGINE_SELECTOR_OPTIONS,
	type ScanEngineTab,
	isScanEngineTab,
} from "@/shared/constants/scanEngines";

interface YasaRulesProps {
	showEngineSelector?: boolean;
	engineValue?: ScanEngineTab;
	onEngineChange?: (value: ScanEngineTab) => void;
}

export interface YasaRuntimeConfigDialogProps {
	open: boolean;
	onOpenChange: (open: boolean) => void;
	runtimeConfigContent: YasaRuntimeConfigContentProps;
}

export interface YasaRuntimeConfigContentProps {
	runtimeConfigForm: YasaRuntimeConfig | null;
	runtimeConfigLoadError: string | null;
	savingRuntimeConfig: boolean;
	isRuntimeConfigDirty: boolean;
	onSave: () => void | Promise<void>;
	onUpdateRuntimeField: (key: keyof YasaRuntimeConfig, value: string) => void;
}

export interface YasaRuleRowViewModel {
	id: string;
	ruleName: string;
	languages: string[];
	source: "内置规则" | "自定义规则";
	confidence: "低";
	activeStatus: "已启用" | "已禁用";
	verifyStatus: "✓ 可用";
	createdAt: "-";
	checkerPacks: string[];
	checkerPath: string;
	demoRuleConfigPath: string;
	description: string;
	ruleConfigJson?: string;
}

function DetailSectionTitle({ children }: { children: string }) {
	return (
		<h3 className="font-mono font-bold uppercase text-sm text-muted-foreground border-b border-border pb-2">
			{children}
		</h3>
	);
}

function DetailInfoCard({
	label,
	value,
	mono = false,
}: {
	label: string;
	value: string;
	mono?: boolean;
}) {
	return (
		<div className="rounded-md border border-border/60 bg-muted/30 p-3">
			<p className="text-xs uppercase tracking-[0.16em] text-muted-foreground">
				{label}
			</p>
			<p
				className={`mt-2 text-sm text-foreground break-all ${mono ? "font-mono" : ""}`}
			>
				{value}
			</p>
		</div>
	);
}

function formatYasaBadgeItems(items: string[]) {
	return items.filter((item) => item && item.trim());
}

export function YasaRuleDetailPanel({
	rule,
	onCopyRawContent,
}: {
	rule: YasaRuleRowViewModel;
	onCopyRawContent: () => void | Promise<void>;
}) {
	const languages = formatYasaBadgeItems(rule.languages);
	const checkerPacks = formatYasaBadgeItems(rule.checkerPacks);
	const rawRuleConfig = rule.ruleConfigJson?.trim() || "";
	const hasRawRuleConfig = rawRuleConfig.length > 0;

	return (
		<div className="flex-1 overflow-y-auto p-6">
			<div className="space-y-6">
				<div className="rounded-md border border-border/60 bg-muted/30 p-4">
					<div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
						<div className="space-y-2">
							<p className="font-mono text-xs uppercase tracking-[0.22em] text-primary">
								Rule Overview
							</p>
							<div>
								<h3 className="text-xl font-semibold break-all text-foreground">
									{rule.ruleName}
								</h3>
								<p className="mt-1 font-mono text-xs text-muted-foreground break-all">
									{rule.id}
								</p>
							</div>
						</div>
						<div className="flex flex-wrap gap-2">
							<Badge className="cyber-badge cyber-badge-info">
								{rule.source}
							</Badge>
							<Badge
								className={
									rule.activeStatus === "已启用"
										? "cyber-badge cyber-badge-success"
										: "cyber-badge cyber-badge-muted"
								}
							>
								{rule.activeStatus}
							</Badge>
							<Badge className="cyber-badge cyber-badge-info">
								{rule.confidence}
							</Badge>
							<Badge className="cyber-badge cyber-badge-success">
								{rule.verifyStatus}
							</Badge>
						</div>
					</div>
				</div>

				<div className="space-y-3">
					<DetailSectionTitle>基本信息</DetailSectionTitle>
					<div className="grid grid-cols-1 gap-4 md:grid-cols-2">
						<DetailInfoCard
							label="规则名称"
							value={rule.ruleName || "-"}
							mono
						/>
						<DetailInfoCard label="规则 ID" value={rule.id || "-"} mono />
						<div className="rounded-md border border-border/60 bg-muted/30 p-3">
							<p className="text-xs uppercase tracking-[0.16em] text-muted-foreground">
								编程语言
							</p>
							<div className="mt-2 flex flex-wrap gap-2">
								{languages.length > 0 ? (
									languages.map((language) => (
										<Badge
											key={`${rule.id}-${language}`}
											className="cyber-badge cyber-badge-info"
										>
											{language}
										</Badge>
									))
								) : (
									<span className="text-sm text-muted-foreground">未标注</span>
								)}
							</div>
						</div>
						<div className="rounded-md border border-border/60 bg-muted/30 p-3">
							<p className="text-xs uppercase tracking-[0.16em] text-muted-foreground">
								CheckerPack
							</p>
							<div className="mt-2 flex flex-wrap gap-2">
								{checkerPacks.length > 0 ? (
									checkerPacks.map((pack) => (
										<Badge
											key={`${rule.id}-${pack}`}
											className="cyber-badge cyber-badge-muted"
										>
											{pack}
										</Badge>
									))
								) : (
									<span className="text-sm text-muted-foreground">未配置</span>
								)}
							</div>
						</div>
					</div>
				</div>

				<div className="space-y-3">
					<DetailSectionTitle>说明信息</DetailSectionTitle>
					<div className="rounded-md border border-border/60 bg-muted/20 p-4">
						<p className="whitespace-pre-wrap break-words text-sm leading-7 text-foreground">
							{rule.description?.trim() || "暂无规则说明"}
						</p>
					</div>
				</div>

				<div className="space-y-3">
					<DetailSectionTitle>技术路径</DetailSectionTitle>
					<div className="grid grid-cols-1 gap-4 md:grid-cols-2">
						<DetailInfoCard
							label="规则路径"
							value={rule.checkerPath?.trim() || "暂无规则路径"}
							mono
						/>
						<DetailInfoCard
							label="Demo Rule Config 路径"
							value={rule.demoRuleConfigPath?.trim() || "暂无 demo 配置路径"}
							mono
						/>
					</div>
				</div>

				{hasRawRuleConfig ? (
					<div className="space-y-3">
						<div className="flex items-center justify-between gap-3">
							<DetailSectionTitle>规则配置</DetailSectionTitle>
							<Button
								size="sm"
								variant="ghost"
								onClick={() => void onCopyRawContent()}
								className="cyber-btn-ghost h-7 text-xs"
							>
								<Copy className="mr-1 h-3 w-3" />
								复制配置
							</Button>
						</div>
						<div className="rounded-md border border-border bg-background/70 p-4 shadow-inner">
							<pre className="max-h-[360px] overflow-auto whitespace-pre-wrap break-words font-mono text-xs leading-6 text-foreground">
								{rawRuleConfig}
							</pre>
						</div>
					</div>
				) : null}
			</div>
		</div>
	);
}

function toViewModel(rule: YasaRule): YasaRuleRowViewModel {
	return {
		id: rule.checker_id,
		ruleName: rule.checker_id,
		languages: rule.languages || [],
		source: "内置规则",
		confidence: "低",
		activeStatus: "已启用",
		verifyStatus: "✓ 可用",
		createdAt: "-",
		checkerPacks: rule.checker_packs || [],
		checkerPath: rule.checker_path || "-",
		demoRuleConfigPath: rule.demo_rule_config_path || "-",
		description: rule.description || "-",
	};
}

function toViewModelFromConfig(config: YasaRuleConfig): YasaRuleRowViewModel {
	return {
		id: config.id,
		ruleName: config.name,
		languages: [config.language],
		source: "自定义规则",
		confidence: "低",
		activeStatus: config.is_active ? "已启用" : "已禁用",
		verifyStatus: "✓ 可用",
		createdAt: "-",
		checkerPacks: (config.checker_pack_ids || "")
			.split(",")
			.map((item) => item.trim())
			.filter(Boolean),
		checkerPath: "-",
		demoRuleConfigPath: "-",
		description: config.description || "-",
		ruleConfigJson: config.rule_config_json,
	};
}

function buildColumns(
	onOpenDetail: (row: YasaRuleRowViewModel) => void,
	onCopyRule: (row: YasaRuleRowViewModel) => Promise<void>,
	checkerPackFilterOptions: { label: string; value: string }[],
): AppColumnDef<YasaRuleRowViewModel, unknown>[] {
	return [
		{
			id: "rowNumber",
			header: "序号",
			enableSorting: false,
			meta: {
				label: "序号",
				align: "center",
				width: 64,
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
		},
		{
			accessorKey: "ruleName",
			header: "规则名称",
			meta: {
				label: "规则名称",
				filterVariant: "text",
			},
			cell: ({ row }) => (
				<span className="font-mono text-xs">{row.original.ruleName}</span>
			),
		},
		{
			id: "languages",
			accessorFn: (row) => row.languages.join(","),
			header: "编程语言",
			enableSorting: false,
			enableHiding: false,
			meta: {
				label: "编程语言",
				filterVariant: "select",
				filterOptions: [
					{ label: "java", value: "java" },
					{ label: "golang", value: "golang" },
					{ label: "typescript", value: "typescript" },
					{ label: "python", value: "python" },
				],
			},
			filterFn: (row, filterValue) => {
				if (!filterValue) return true;
				const languages = row.original.languages || [];
				return languages.includes(String(filterValue));
			},
			cell: ({ row }) => (
				<div className="flex flex-wrap gap-1">
					{row.original.languages.length > 0 ? (
						row.original.languages.map((language) => (
							<Badge
								key={`${row.original.id}-${language}`}
								className="cyber-badge-info"
							>
								{language}
							</Badge>
						))
					) : (
						<span className="text-xs text-muted-foreground">未标注</span>
					)}
				</div>
			),
		},
		{
			accessorKey: "source",
			header: "规则来源",
			enableSorting: false,
			enableHiding: false,
			meta: {
				label: "规则来源",
				filterVariant: "select",
				filterOptions: [
					{ label: "内置规则", value: "内置规则" },
					{ label: "自定义规则", value: "自定义规则" },
				],
			},
			cell: ({ row }) => (
				<Badge className="cyber-badge-info">{row.original.source}</Badge>
			),
		},
		{
			accessorKey: "confidence",
			header: "置信度",
			enableSorting: false,
			enableHiding: false,
			meta: {
				label: "置信度",
				filterVariant: "select",
				filterOptions: [{ label: "低", value: "低" }],
			},
			cell: ({ row }) => (
				<Badge className="cyber-badge-info">{row.original.confidence}</Badge>
			),
		},
		{
			accessorKey: "activeStatus",
			header: "启用状态",
			enableSorting: false,
			enableHiding: false,
			meta: {
				label: "启用状态",
				filterVariant: "select",
				filterOptions: [
					{ label: "已启用", value: "已启用" },
					{ label: "已禁用", value: "已禁用" },
				],
			},
			cell: ({ row }) => (
				<Badge
					className={
						row.original.activeStatus === "已启用"
							? "cyber-badge-success"
							: "cyber-badge-muted"
					}
				>
					{row.original.activeStatus}
				</Badge>
			),
		},
		{
			accessorKey: "verifyStatus",
			header: "验证状态",
			meta: {
				label: "验证状态",
			},
			cell: ({ row }) => (
				<span className="text-emerald-400">{row.original.verifyStatus}</span>
			),
		},
		// {
		//   accessorKey: "createdAt",
		//   header: "创建时间",
		//   meta: {
		//     label: "创建时间",
		//   },
		// },
		{
			id: "checkerPack",
			accessorFn: (row) => row.checkerPacks.join(","),
			header: "CheckerPack",
			meta: {
				label: "CheckerPack",
				filterVariant: "select",
				filterOptions: checkerPackFilterOptions,
			},
			cell: ({ row }) => (
				<div className="flex flex-wrap gap-1">
					{row.original.checkerPacks.length > 0 ? (
						row.original.checkerPacks.map((pack) => (
							<Badge
								key={`${row.original.id}-${pack}`}
								className="cyber-badge-muted"
							>
								{pack}
							</Badge>
						))
					) : (
						<span className="text-xs text-muted-foreground">-</span>
					)}
				</div>
			),
		},
		{
			id: "actions",
			header: "操作",
			enableSorting: false,
			meta: {
				label: "操作",
				minWidth: 220,
			},
			cell: ({ row }) => (
				<div className="flex items-center gap-3 text-sm">
					<button
						type="button"
						className="text-primary hover:text-primary/80"
						onClick={() => onOpenDetail(row.original)}
					>
						详情
					</button>
					<button
						type="button"
						className="inline-flex items-center gap-1 text-primary hover:text-primary/80"
						onClick={() => void onCopyRule(row.original)}
					>
						<Copy className="h-3 w-3" />
						复制
					</button>
					<span className="cursor-not-allowed text-muted-foreground/50">
						编辑
					</span>
					<span className="cursor-not-allowed text-muted-foreground/50">
						禁用
					</span>
					<span className="cursor-not-allowed text-muted-foreground/50">
						删除
					</span>
				</div>
			),
		},
	];
}

function buildSelectionSummary({
	selectedCount,
	filteredCount,
}: DataTableSelectionContext<YasaRuleRowViewModel>) {
	if (selectedCount > 0) {
		return (
			<>
				已选择 <span className="font-bold text-primary">{selectedCount}</span>{" "}
				条规则
			</>
		);
	}
	return (
		<>
			将对全部 <span className="font-bold text-primary">{filteredCount}</span>{" "}
			条规则进行操作
		</>
	);
}

export function YasaRuntimeConfigDialog({
	open,
	onOpenChange,
	runtimeConfigContent,
}: YasaRuntimeConfigDialogProps) {
	return (
		<Dialog open={open} onOpenChange={onOpenChange}>
			<DialogContent className="!w-[min(92vw,760px)] !max-w-none p-0 gap-0 cyber-dialog border border-border rounded-lg">
				<YasaRuntimeConfigContent
					{...runtimeConfigContent}
					onRequestClose={() => onOpenChange(false)}
				/>
			</DialogContent>
		</Dialog>
	);
}

export function YasaRuntimeConfigContent({
	runtimeConfigForm,
	runtimeConfigLoadError,
	savingRuntimeConfig,
	isRuntimeConfigDirty,
	onSave,
	onUpdateRuntimeField,
	onRequestClose,
}: YasaRuntimeConfigContentProps & { onRequestClose?: () => void }) {
	const saveDisabled =
		!runtimeConfigForm ||
		Boolean(runtimeConfigLoadError) ||
		savingRuntimeConfig ||
		!isRuntimeConfigDirty;

	return (
		<>
			<div className="px-5 py-4 border-b border-border bg-muted">
				<h2 className="font-mono text-base font-bold uppercase tracking-wider text-foreground">
					YASA 运行配置
				</h2>
				<p className="text-xs text-muted-foreground">
					修改后对后续新建任务全局生效
				</p>
			</div>
			<div className="space-y-4 px-5 py-4">
				{runtimeConfigLoadError ? (
					<div
						role="status"
						className="rounded-md border border-amber-500/30 bg-amber-500/5 px-3 py-2 text-xs text-amber-200"
					>
						{runtimeConfigLoadError}
					</div>
				) : runtimeConfigForm ? (
					<div className="grid grid-cols-1 gap-3 md:grid-cols-2">
						<div className="space-y-1">
							<Label className="text-xs">YASA超时(秒)</Label>
							<Input
								type="number"
								min={30}
								max={86400}
								value={runtimeConfigForm.yasa_timeout_seconds}
								onChange={(event) =>
									onUpdateRuntimeField(
										"yasa_timeout_seconds",
										event.target.value,
									)
								}
							/>
						</div>
						<div className="space-y-1">
							<Label className="text-xs">Orphan判定阈值(秒)</Label>
							<Input
								type="number"
								min={30}
								max={86400}
								value={runtimeConfigForm.yasa_orphan_stale_seconds}
								onChange={(event) =>
									onUpdateRuntimeField(
										"yasa_orphan_stale_seconds",
										event.target.value,
									)
								}
							/>
						</div>
						<div className="space-y-1">
							<Label className="text-xs">心跳间隔(秒)</Label>
							<Input
								type="number"
								min={1}
								max={3600}
								value={runtimeConfigForm.yasa_exec_heartbeat_seconds}
								onChange={(event) =>
									onUpdateRuntimeField(
										"yasa_exec_heartbeat_seconds",
										event.target.value,
									)
								}
							/>
						</div>
						<div className="space-y-1">
							<Label className="text-xs">进程回收宽限(秒)</Label>
							<Input
								type="number"
								min={1}
								max={60}
								value={runtimeConfigForm.yasa_process_kill_grace_seconds}
								onChange={(event) =>
									onUpdateRuntimeField(
										"yasa_process_kill_grace_seconds",
										event.target.value,
									)
								}
							/>
						</div>
					</div>
				) : (
					<p className="text-xs text-muted-foreground">正在加载运行配置...</p>
				)}
			</div>
			<div className="flex justify-end gap-3 px-5 py-4 border-t border-border bg-muted">
				{onRequestClose ? (
					<Button
						type="button"
						variant="outline"
						className="cyber-btn-outline"
						onClick={onRequestClose}
					>
						关闭
					</Button>
				) : null}
				<Button
					type="button"
					className="cyber-btn-primary"
					onClick={() => void onSave()}
					disabled={saveDisabled}
				>
					{savingRuntimeConfig ? "保存中..." : "保存配置"}
				</Button>
			</div>
		</>
	);
}

export default function YasaRules({
	showEngineSelector = false,
	engineValue = "yasa",
	onEngineChange,
}: YasaRulesProps) {
	const [rules, setRules] = useState<YasaRule[]>([]);
	const [customRuleConfigs, setCustomRuleConfigs] = useState<YasaRuleConfig[]>(
		[],
	);
	const [loading, setLoading] = useState(true);
	const [rulesLoadError, setRulesLoadError] = useState<string | null>(null);
	const [customConfigsLoadError, setCustomConfigsLoadError] = useState<
		string | null
	>(null);
	const [runtimeConfigLoadError, setRuntimeConfigLoadError] = useState<
		string | null
	>(null);
	const [detailRule, setDetailRule] = useState<YasaRuleRowViewModel | null>(
		null,
	);
	const [showDetail, setShowDetail] = useState(false);
	const [showImportDialog, setShowImportDialog] = useState(false);
	const [showAdvancedConfigDialog, setShowAdvancedConfigDialog] =
		useState(false);
	const [importing, setImporting] = useState(false);
	const [importName, setImportName] = useState("");
	const [importLanguage, setImportLanguage] = useState("golang");
	const [importDescription, setImportDescription] = useState("");
	const [importRuleConfigJson, setImportRuleConfigJson] = useState("");
	const [importRuleConfigFile, setImportRuleConfigFile] = useState<File | null>(
		null,
	);
	const [runtimeConfig, setRuntimeConfig] = useState<YasaRuntimeConfig | null>(
		null,
	);
	const [runtimeConfigForm, setRuntimeConfigForm] =
		useState<YasaRuntimeConfig | null>(null);
	const [savingRuntimeConfig, setSavingRuntimeConfig] = useState(false);
	const { initialState, syncStateToUrl } = useDataTableUrlState(true);
	const [tableState, setTableState] = useState<DataTableQueryState>(() =>
		createInitialTableState(initialState),
	);
	const resolvedUrlState = useMemo(
		() => createInitialTableState(initialState),
		[initialState],
	);

	const applyLoaderResult = (result: YasaRulesLoaderResult) => {
		setRules(result.rules);
		setCustomRuleConfigs(result.customRuleConfigs);
		setRulesLoadError(result.rulesLoadError);
		setCustomConfigsLoadError(result.customConfigsLoadError);
		setRuntimeConfigLoadError(result.runtimeConfigLoadError);
		setRuntimeConfig(result.runtimeConfig);
		setRuntimeConfigForm(result.runtimeConfig);
	};

	const loadPageData = async () => {
		try {
			setLoading(true);
			const result = await loadYasaRulesPageData();
			applyLoaderResult(result);
			if (result.rulesLoadError) {
				toast.error(result.rulesLoadError);
			}
			if (result.customConfigsLoadError) {
				toast.error(
					result.customConfigsLoadError ||
						YASA_CUSTOM_RULE_CONFIGS_LOAD_ERROR_FALLBACK,
				);
			}
			if (result.runtimeConfigLoadError) {
				toast.error(
					result.runtimeConfigLoadError ||
						YASA_RUNTIME_CONFIG_LOAD_ERROR_FALLBACK,
				);
			}
		} finally {
			setLoading(false);
		}
	};

	useEffect(() => {
		void loadPageData();
	}, []);

	useEffect(() => {
		setTableState((current) =>
			areDataTableQueryStatesEqual(current, resolvedUrlState)
				? current
				: resolvedUrlState,
		);
	}, [resolvedUrlState]);

	useEffect(() => {
		syncStateToUrl(tableState);
	}, [syncStateToUrl, tableState]);

	const rows = useMemo(
		() => [
			...rules.map(toViewModel),
			...customRuleConfigs.map(toViewModelFromConfig),
		],
		[rules, customRuleConfigs],
	);
	const checkerPackOptions = useMemo(
		() =>
			Array.from(
				new Set(
					rows
						.flatMap((rule) => rule.checkerPacks)
						.filter((item) => item && item.trim()),
				),
			).sort(),
		[rows],
	);

	const stats = useMemo(() => {
		const languageCount = new Set(rows.flatMap((item) => item.languages)).size;
		const activeCount = rows.filter(
			(item) => item.activeStatus === "已启用",
		).length;
		return {
			total: rows.length,
			active: activeCount,
			checkerPackCount: checkerPackOptions.length,
			languageCount,
		};
	}, [rows, checkerPackOptions.length]);

	const checkerPackFilterOptions = useMemo(
		() =>
			checkerPackOptions.map((option) => ({ label: option, value: option })),
		[checkerPackOptions],
	);

	const columns = useMemo<ColumnDef<YasaRuleRowViewModel>[]>(
		() =>
			buildColumns(
				(row) => {
					setDetailRule(row);
					setShowDetail(true);
				},
				async (row) => {
					try {
						const text = JSON.stringify(
							{
								checker_id: row.id,
								source: row.source,
								checker_packs: row.checkerPacks,
								languages: row.languages,
								checker_path: row.checkerPath,
								demo_rule_config_path: row.demoRuleConfigPath,
								rule_config_json: row.ruleConfigJson,
							},
							null,
							2,
						);
						await navigator.clipboard.writeText(text);
						toast.success(`已复制规则: ${row.id}`);
					} catch {
						toast.error("复制失败，请手动复制");
					}
				},
				checkerPackFilterOptions,
			),
		[checkerPackFilterOptions],
	);
	const isRuntimeConfigDirty = useMemo(() => {
		if (!runtimeConfig || !runtimeConfigForm) return false;
		return JSON.stringify(runtimeConfig) !== JSON.stringify(runtimeConfigForm);
	}, [runtimeConfig, runtimeConfigForm]);

	const updateRuntimeField = (key: keyof YasaRuntimeConfig, value: string) => {
		setRuntimeConfigForm((current) => {
			if (!current) return current;
			const parsed = Number(value);
			return {
				...current,
				[key]: Number.isFinite(parsed) ? parsed : 0,
			};
		});
	};

	const handleSaveRuntimeConfig = async () => {
		if (!runtimeConfigForm) return;
		try {
			setSavingRuntimeConfig(true);
			const saved = await updateYasaRuntimeConfig(runtimeConfigForm);
			setRuntimeConfig(saved);
			setRuntimeConfigForm(saved);
			toast.success("全语言统一超时已生效（对后续新任务）");
		} catch (error: any) {
			const detail = error?.response?.data?.detail || "保存 YASA 运行配置失败";
			toast.error(String(detail));
		} finally {
			setSavingRuntimeConfig(false);
		}
	};

	const engineSelector = showEngineSelector ? (
		<div className="min-w-[150px]">
			<Select
				value={engineValue}
				onValueChange={(val) => {
					if (isScanEngineTab(val)) {
						onEngineChange?.(val);
					}
				}}
			>
				<SelectTrigger className="cyber-input h-10 min-w-[150px]">
					<SelectValue placeholder="选择引擎" />
				</SelectTrigger>
				<SelectContent className="cyber-dialog border-border">
					{SCAN_ENGINE_SELECTOR_OPTIONS.map((option) => (
						<SelectItem key={option.value} value={option.value}>
							{option.label}
						</SelectItem>
					))}
				</SelectContent>
			</Select>
		</div>
	) : null;

	const handleImportCustomRuleConfig = async () => {
		if (!importName.trim()) {
			toast.error("请输入规则名称");
			return;
		}
		if (!importRuleConfigJson.trim() && !importRuleConfigFile) {
			toast.error("请填写 rule-config JSON 或上传文件");
			return;
		}
		try {
			setImporting(true);
			await importYasaRuleConfig({
				name: importName.trim(),
				description: importDescription.trim() || undefined,
				language: importLanguage,
				rule_config_json: importRuleConfigJson.trim() || undefined,
				rule_config_file: importRuleConfigFile || undefined,
			});
			toast.success("YASA 自定义规则导入成功");
			setShowImportDialog(false);
			setImportName("");
			setImportDescription("");
			setImportRuleConfigJson("");
			setImportRuleConfigFile(null);
			await loadPageData();
		} catch (error: any) {
			const detail = error?.response?.data?.detail || "导入失败";
			toast.error(String(detail));
		} finally {
			setImporting(false);
		}
	};

	return (
		<div className="space-y-6 p-4 md:p-6">
			<div className="relative z-10 grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
				<div className="cyber-card p-4">
					<div className="flex items-center justify-between">
						<div>
							<p className="stat-label">有效规则总数</p>
							<div className="flex items-end gap-3">
								<p className="stat-value">{stats.total}</p>
								<p className="mb-1 flex items-center gap-3 text-sm">
									<span className="inline-flex items-center gap-1 text-emerald-400">
										<span className="h-2 w-2 rounded-full bg-emerald-400" />
										已启用 {stats.active}
									</span>
								</p>
							</div>
						</div>
						<div className="stat-icon text-primary">
							<Database className="h-6 w-6" />
						</div>
					</div>
				</div>
				<div className="cyber-card p-4">
					<div className="flex items-center justify-between">
						<div>
							<p className="stat-label">CheckerPack 数量</p>
							<p className="stat-value">{stats.checkerPackCount}</p>
						</div>
						<div className="stat-icon text-indigo-400">
							<Tag className="h-6 w-6" />
						</div>
					</div>
				</div>
				<div className="cyber-card p-4">
					<div className="flex items-center justify-between">
						<div>
							<p className="stat-label">支持语言数量</p>
							<p className="stat-value">{stats.languageCount}</p>
						</div>
						<div className="stat-icon text-cyan-400">
							<Shield className="h-6 w-6" />
						</div>
					</div>
				</div>
			</div>

			{customConfigsLoadError ? (
				<div
					role="status"
					className="cyber-card border border-amber-500/30 bg-amber-500/5 p-3 text-xs text-amber-200"
				>
					{customConfigsLoadError}
				</div>
			) : null}

			<div className="cyber-card relative z-10 overflow-hidden">
				<DataTable
					data={rows}
					columns={columns}
					state={tableState}
					onStateChange={setTableState}
					loading={loading}
					error={rulesLoadError || undefined}
					emptyState={{
						title: "暂无符合条件的规则",
						description:
							rules.length === 0 && customRuleConfigs.length === 0
								? "当前没有可展示的 YASA 规则"
								: "调整筛选条件尝试",
					}}
					toolbar={{
						searchPlaceholder: "搜索规则名称或ID...",
						leadingActions: engineSelector,
						showGlobalSearch: false,
						showColumnVisibility: false,
						showDensityToggle: false,
						showReset: false,
					}}
					selection={{
						enableRowSelection: true,
						summary: buildSelectionSummary,
						actions: () => (
							<>
								<Button
									type="button"
									size="sm"
									className="cyber-btn-primary h-8"
									disabled
								>
									批量启用
								</Button>
								<Button
									type="button"
									size="sm"
									variant="outline"
									className="cyber-btn-outline h-8"
									disabled
								>
									批量禁用
								</Button>
								<Button
									type="button"
									size="sm"
									variant="ghost"
									className="h-8 text-muted-foreground"
									disabled
								>
									取消操作
								</Button>
								<Button
									type="button"
									size="sm"
									className="cyber-btn-primary h-9"
									onClick={() => setShowImportDialog(true)}
								>
									导入自定义规则
								</Button>
								<Button
									type="button"
									size="sm"
									className="cyber-btn-primary h-9"
									onClick={() => setShowAdvancedConfigDialog(true)}
								>
									高级配置
								</Button>
							</>
						),
					}}
					pagination={{
						enabled: true,
						pageSizeOptions: [10, 20, 50],
					}}
					tableClassName="min-w-[1240px]"
				/>
			</div>

			<Dialog open={showDetail} onOpenChange={setShowDetail}>
				<DialogContent className="!w-[min(92vw,980px)] !max-w-none max-h-[90vh] flex flex-col p-0 gap-0 cyber-dialog border border-border rounded-lg">
					<DialogHeader className="px-6 pt-4 flex-shrink-0 border-b border-border bg-muted/30">
						<DialogTitle className="font-mono text-lg uppercase tracking-wider flex items-center gap-2 text-foreground">
							<Code2 className="w-5 h-5 text-primary" />
							YASA 规则详情
						</DialogTitle>
					</DialogHeader>
					{detailRule ? (
						<YasaRuleDetailPanel
							rule={detailRule}
							onCopyRawContent={async () => {
								if (!detailRule.ruleConfigJson?.trim()) {
									toast.error("当前规则没有可复制的配置内容");
									return;
								}
								try {
									await navigator.clipboard.writeText(
										detailRule.ruleConfigJson,
									);
									toast.success("已复制规则配置");
								} catch {
									toast.error("复制失败，请手动复制");
								}
							}}
						/>
					) : null}
					<div className="flex-shrink-0 flex justify-end gap-3 px-6 py-4 bg-muted border-t border-border">
						<Button
							type="button"
							variant="outline"
							onClick={() => setShowDetail(false)}
							className="cyber-btn-outline"
						>
							关闭
						</Button>
					</div>
				</DialogContent>
			</Dialog>
			<Dialog open={showImportDialog} onOpenChange={setShowImportDialog}>
				<DialogContent className="cyber-dialog max-w-3xl border border-border">
					<DialogHeader>
						<DialogTitle>导入 YASA 自定义规则配置</DialogTitle>
					</DialogHeader>
					<div className="space-y-3 text-sm">
						<div className="space-y-1">
							<Label>规则名称</Label>
							<Input
								value={importName}
								onChange={(e) => setImportName(e.target.value)}
							/>
						</div>
						<div className="space-y-1">
							<Label>语言</Label>
							<Select value={importLanguage} onValueChange={setImportLanguage}>
								<SelectTrigger className="h-9 cyber-input max-w-[220px]">
									<SelectValue />
								</SelectTrigger>
								<SelectContent>
									<SelectItem value="java">java</SelectItem>
									<SelectItem value="golang">golang</SelectItem>
									<SelectItem value="typescript">typescript</SelectItem>
									<SelectItem value="python">python</SelectItem>
								</SelectContent>
							</Select>
						</div>
						<div className="space-y-1">
							<Label>描述（可选）</Label>
							<Input
								value={importDescription}
								onChange={(e) => setImportDescription(e.target.value)}
							/>
						</div>
						<div className="space-y-1">
							<Label>rule-config JSON（可粘贴）</Label>
							<Textarea
								rows={8}
								value={importRuleConfigJson}
								onChange={(e) => setImportRuleConfigJson(e.target.value)}
								placeholder='例如: [{"checkerIds":["taint_flow_go_input"],"...":"..."}]'
							/>
						</div>
						<div className="space-y-1">
							<Label>或上传 JSON 文件</Label>
							<Input
								type="file"
								accept=".json,application/json"
								onChange={(event) =>
									setImportRuleConfigFile(event.target.files?.[0] || null)
								}
							/>
						</div>
						<div className="flex justify-end">
							<Button
								type="button"
								className="cyber-btn-primary"
								disabled={importing}
								onClick={() => void handleImportCustomRuleConfig()}
							>
								{importing ? "导入中..." : "确认导入"}
							</Button>
						</div>
					</div>
				</DialogContent>
			</Dialog>
			<YasaRuntimeConfigDialog
				open={showAdvancedConfigDialog}
				onOpenChange={setShowAdvancedConfigDialog}
				runtimeConfigContent={{
					runtimeConfigForm,
					runtimeConfigLoadError,
					savingRuntimeConfig,
					isRuntimeConfigDirty,
					onSave: handleSaveRuntimeConfig,
					onUpdateRuntimeField: updateRuntimeField,
				}}
			/>
		</div>
	);
}

function createInitialTableState(
	initialState: DataTableQueryState,
): DataTableQueryState {
	return {
		...initialState,
		pagination: {
			pageIndex: initialState.pagination.pageIndex,
			pageSize: initialState.pagination.pageSize || 10,
		},
		columnVisibility: {
			...initialState.columnVisibility,
			checkerPack: false,
			verifyStatus: false,
			languages: false,
		},
	};
}
