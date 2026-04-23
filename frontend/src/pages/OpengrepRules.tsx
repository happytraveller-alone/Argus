/**
 * Opengrep Rules Management Page
 * Cyberpunk Terminal Aesthetic
 */

import { useEffect, useMemo, useState } from "react";
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
import { Textarea } from "@/components/ui/textarea";
import { Checkbox } from "@/components/ui/checkbox";
import { toast } from "sonner";
import {
	Trash2,
	Copy,
	PencilLine,
	Save,
	Code,
	AlertTriangle,
	ArrowLeft,
	Database,
} from "lucide-react";
import { useLocation, useNavigate } from "react-router-dom";
import {
	type AppColumnDef,
	createDefaultDataTableState,
	DataTable,
	type DataTableQueryState,
	type DataTableSelectionContext,
} from "@/components/data-table";
import {
	getOpengrepRules,
	getOpengrepRule,
	getGeneratingRules,
	toggleOpengrepRule,
	deleteOpengrepRule,
	generateOpengrepRule,
	uploadOpengrepRuleJSON,
	uploadOpengrepRulesCompressed,
	uploadOpengrepRulesDirectory,
	uploadPatchArchive,
	uploadPatchDirectory,
	updateOpengrepRule,
	batchUpdateOpengrepRules,
	RULE_SOURCES,
	ACTIVE_STATUS,
	type OpengrepRule,
	type OpengrepRuleDetail,
} from "@/shared/api/opengrep";
import {
	formatCweDisplayLabel,
	normalizeCweId,
	resolveCweDisplay,
} from "@/shared/security/cweCatalog";
import { setOpengrepActiveRules } from "@/shared/stores/opengrepRulesStore";
import { useI18n } from "@/shared/i18n";
import {
	SCAN_ENGINE_SELECTOR_OPTIONS,
	type ScanEngineTab,
	isScanEngineTab,
} from "@/shared/constants/scanEngines";

export function formatRuleCweDisplayLabel(cwe?: string) {
	return formatCweDisplayLabel(cwe);
}

function formatRuleCweDisplayTitle(cwe?: string) {
	const display = resolveCweDisplay({ cwe });
	return display.tooltip || display.label;
}

interface OpengrepRulesProps {
	embedded?: boolean;
	showEngineSelector?: boolean;
	engineValue?: ScanEngineTab;
	onEngineChange?: (value: ScanEngineTab) => void;
}

const DEFAULT_PAGE_SIZE = 10;

function getColumnFilterValue(state: DataTableQueryState, columnId: string) {
	return state.columnFilters.find((filter) => filter.id === columnId)?.value;
}

function getStringColumnFilter(
	state: DataTableQueryState,
	columnId: string,
	fallback = "",
) {
	const value = getColumnFilterValue(state, columnId);
	return typeof value === "string" ? value : fallback;
}

function buildSelectionSummary({
	selectedCount,
	filteredCount,
}: DataTableSelectionContext<OpengrepRule>) {
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

function createInitialTableState(globalFilter = ""): DataTableQueryState {
	return createDefaultDataTableState({
		globalFilter,
		pagination: {
			pageIndex: 0,
			pageSize: DEFAULT_PAGE_SIZE,
		},
	});
}

export default function OpengrepRules({
	embedded = false,
	showEngineSelector = false,
	engineValue = "opengrep",
	onEngineChange,
}: OpengrepRulesProps) {
	const activeEngine = showEngineSelector ? engineValue : "opengrep";
	const isGitleaksEngine = activeEngine === "gitleaks";
	const showGitleaksNotReady = () => {
		toast.info("gitleaks 规则管理暂未接入");
	};

	const { t } = useI18n();
	const navigate = useNavigate();
	const location = useLocation();
	const [rules, setRules] = useState<OpengrepRule[]>([]);
	const [ruleStats, setRuleStats] = useState({
		total: 0,
		active: 0,
		inactive: 0,
		languageCount: 0,
		vulnerabilityTypeCount: 0,
	});
	const [loading, setLoading] = useState(true);
	const [loadError, setLoadError] = useState<string | null>(null);
	const [showRuleDetail, setShowRuleDetail] = useState(false);
	const [selectedRule, setSelectedRule] = useState<OpengrepRuleDetail | null>(
		null,
	);
	const [isEditingRule, setIsEditingRule] = useState(false);
	const [savingRule, setSavingRule] = useState(false);
	const [editRuleForm, setEditRuleForm] = useState({
		name: "",
		language: "",
		severity: "ERROR",
		pattern_yaml: "",
	});
	const [loadingDetail, setLoadingDetail] = useState(false);
	const [availableLanguages, setAvailableLanguages] = useState<string[]>([]);
	const [showRuleTypeDialog, setShowRuleTypeDialog] = useState(false);
	const [showGenericDialog, setShowGenericDialog] = useState(false);
	const [showEventDialog, setShowEventDialog] = useState(false);
	const [generatingRule, setGeneratingRule] = useState(false);
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
	const [eventRuleUploadTab, setEventRuleUploadTab] = useState<
		"manual" | "archive" | "directory"
	>("manual");
	const [patchArchive, setPatchArchive] = useState<File | null>(null);
	const [patchDirectoryFiles, setPatchDirectoryFiles] = useState<File[]>([]);
	const [genericRuleUploadTab, setGenericRuleUploadTab] = useState<
		"manual" | "compressed" | "directory"
	>("manual");
	const [compressedFile, setCompressedFile] = useState<File | null>(null);
	const [directoryFiles, setDirectoryFiles] = useState<File[]>([]);
	const [uploadingRules, setUploadingRules] = useState(false);
	const [generatingRules, setGeneratingRules] = useState<
		Map<
			string,
			{ name: string; progress: number; status: string; doneAt?: number }
		>
	>(new Map());
	const [showGeneratingQueue, setShowGeneratingQueue] = useState(false);
	const [manualRuleForm, setManualRuleForm] = useState({
		id: "",
		name: "",
		language: "python",
		pattern_yaml: "",
		severity: "ERROR",
		confidence: "",
		description: "",
		cwe: [] as string[],
		source: "json",
		patch: "",
		correct: true,
		is_active: true,
	});
	const sanitizeRuleSearchKeyword = (value?: string | null) =>
		String(value || "")
			.trim()
			.replace(/^(?:tmp[-_]+|tem[-_]+)/i, "");
	const queryParams = new URLSearchParams(location.search);
	const highlightRuleKeyword = sanitizeRuleSearchKeyword(
		queryParams.get("highlightRule"),
	);
	const returnTo = queryParams.get("returnTo") || "";
	const [tableState, setTableState] = useState<DataTableQueryState>(() =>
		createInitialTableState(highlightRuleKeyword),
	);
	const languageFilter = getStringColumnFilter(tableState, "language");
	const sourceFilter = getStringColumnFilter(tableState, "source");
	const confidenceFilter = getStringColumnFilter(tableState, "confidence");
	const activeFilter = getStringColumnFilter(tableState, "status");

	useEffect(() => {
		if (isGitleaksEngine) {
			setGeneratingRules(new Map());
			setShowGeneratingQueue(false);
		}
		void loadRules();
		void loadRuleStats();
		if (!isGitleaksEngine) {
			void loadGeneratingRules();
		}
	}, [activeEngine, isGitleaksEngine]);

	useEffect(() => {
		if (!highlightRuleKeyword) return;
		setTableState((current) => ({
			...current,
			globalFilter: highlightRuleKeyword,
			pagination: {
				...current.pagination,
				pageIndex: 0,
			},
		}));
	}, [highlightRuleKeyword]);

	const loadGeneratingRules = async () => {
		try {
			const generatingRulesList = await getGeneratingRules();
			const existingMap = new Map(generatingRules);
			const incomingIds = new Set(generatingRulesList.map((rule) => rule.id));
			const allIds = new Set<string>([...existingMap.keys(), ...incomingIds]);

			if (allIds.size === 0) {
				setGeneratingRules(new Map());
				setShowGeneratingQueue(false);
				return;
			}

			const detailResults = await Promise.all(
				Array.from(allIds).map(async (ruleId) => {
					const listRule = generatingRulesList.find(
						(rule) => rule.id === ruleId,
					);
					try {
						const detail = await getOpengrepRule(ruleId);
						return { ruleId, listRule, detail, error: null };
					} catch (error) {
						return { ruleId, listRule, detail: null, error };
					}
				}),
			);

			const now = Date.now();
			const nextMap = new Map<
				string,
				{ name: string; progress: number; status: string; doneAt?: number }
			>();

			for (const { ruleId, listRule, detail } of detailResults) {
				const existing = existingMap.get(ruleId);
				const name = detail?.name || listRule?.name || existing?.name || ruleId;

				let status = "生成中...";
				let doneAt = existing?.doneAt;

				if (detail?.correct === true) {
					status = "✓ 生成成功";
					doneAt = doneAt ?? now;
				} else if (
					typeof detail?.pattern_yaml === "string" &&
					detail.pattern_yaml.includes("error")
				) {
					status = "✗ 生成失败";
					doneAt = doneAt ?? now;
				}

				const shouldKeep =
					incomingIds.has(ruleId) ||
					(doneAt !== undefined && now - doneAt < 5000);

				if (shouldKeep) {
					nextMap.set(ruleId, {
						name,
						progress: 0,
						status,
						doneAt,
					});
				}
			}

			if (nextMap.size === 0) {
				setGeneratingRules(new Map());
				setShowGeneratingQueue(false);
				return;
			}

			setGeneratingRules(nextMap);
			setShowGeneratingQueue(true);
		} catch (error) {
			console.error("Failed to load generating rules:", error);
		}
	};

	useEffect(() => {
		if (isGitleaksEngine || generatingRules.size === 0) {
			return;
		}
		const timer = window.setInterval(() => {
			void loadGeneratingRules();
		}, 2000);
		return () => window.clearInterval(timer);
	}, [generatingRules.size, isGitleaksEngine]);

	const loadRules = async (options?: { silent?: boolean }) => {
		const silent = options?.silent ?? false;
		try {
			if (!silent) {
				setLoading(true);
			}
			setLoadError(null);

			if (isGitleaksEngine) {
				setRules([]);
				setAvailableLanguages([]);
				setOpengrepActiveRules([]);
				return;
			}

			const data = await getOpengrepRules();
			const severeRules = data.filter(
				(rule) => String(rule.severity || "").toUpperCase() === "ERROR",
			);
			setRules(severeRules);

			const languages = Array.from(
				new Set(severeRules.map((rule) => rule.language)),
			).sort();
			setAvailableLanguages(languages);

			setOpengrepActiveRules(severeRules.filter((rule) => rule.is_active));
		} catch (error) {
			console.error("Failed to load rules:", error);
			setLoadError("加载规则失败");
			toast.error("加载规则失败");
		} finally {
			if (!silent) {
				setLoading(false);
			}
		}
	};

	const loadRuleStats = async () => {
		try {
			const allRules = (await getOpengrepRules()).filter(
				(rule) => String(rule.severity || "").toUpperCase() === "ERROR",
			);
			const languageSet = new Set<string>();
			const vulnerabilityTypeSet = new Set<string>();

			for (const rule of allRules) {
				const normalizedLanguage = String(rule.language || "")
					.trim()
					.toLowerCase();
				if (normalizedLanguage) {
					languageSet.add(normalizedLanguage);
				}

				if (Array.isArray(rule.cwe)) {
					for (const cwe of rule.cwe) {
						const normalizedCwe = normalizeCweId(cwe);
						if (normalizedCwe) {
							vulnerabilityTypeSet.add(normalizedCwe);
						}
					}
				}
			}

			const activeCount = allRules.filter((rule) => rule.is_active).length;

			setRuleStats({
				total: allRules.length,
				active: activeCount,
				inactive: Math.max(allRules.length - activeCount, 0),
				languageCount: languageSet.size,
				vulnerabilityTypeCount: vulnerabilityTypeSet.size,
			});
		} catch (error) {
			console.error("Failed to load rule stats:", error);
		}
	};

	const syncEditForm = (detail: OpengrepRuleDetail) => {
		setEditRuleForm({
			name: detail.name,
			language: detail.language,
			severity: detail.severity,
			pattern_yaml: detail.pattern_yaml,
		});
	};

	const handleViewRule = async (
		rule: OpengrepRule,
		options?: { edit?: boolean },
	) => {
		try {
			setLoadingDetail(true);
			const detail = await getOpengrepRule(rule.id);
			setSelectedRule(detail);
			syncEditForm(detail);
			setIsEditingRule(options?.edit ?? false);
			setShowRuleDetail(true);
		} catch (error) {
			console.error("Failed to load rule detail:", error);
			toast.error("加载规则详情失败");
		} finally {
			setLoadingDetail(false);
		}
	};

	const handleViewRuleById = async (ruleId: string) => {
		try {
			setLoadingDetail(true);
			const detail = await getOpengrepRule(ruleId);
			setSelectedRule(detail);
			syncEditForm(detail);
			setIsEditingRule(false);
			setShowRuleDetail(true);
		} catch (error) {
			console.error("Failed to load rule detail:", error);
			toast.error("加载规则详情失败");
		} finally {
			setLoadingDetail(false);
		}
	};

	const handleToggleRule = async (rule: OpengrepRule) => {
		if (isGitleaksEngine) {
			showGitleaksNotReady();
			return;
		}
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
			setOpengrepActiveRules(previousRules.filter((item) => item.is_active));
			console.error("Failed to toggle rule:", error);
			toast.error("更新规则失败");
		}
	};

	const handleStartEditRule = () => {
		if (!selectedRule) return;
		syncEditForm(selectedRule);
		setIsEditingRule(true);
	};

	const handleCancelEditRule = () => {
		if (selectedRule) {
			syncEditForm(selectedRule);
		}
		setIsEditingRule(false);
	};

	const handleSaveRule = async () => {
		if (isGitleaksEngine) {
			showGitleaksNotReady();
			return;
		}
		if (!selectedRule) return;

		const name = editRuleForm.name.trim();
		const language = editRuleForm.language.trim();
		const patternYaml = editRuleForm.pattern_yaml.trim();
		const severity = "ERROR";

		if (!name || !language || !patternYaml) {
			toast.error("请填写规则名称、语言和规则文本");
			return;
		}

		try {
			setSavingRule(true);
			const result = await updateOpengrepRule(selectedRule.id, {
				name,
				language,
				severity,
				pattern_yaml: patternYaml,
			});

			const updatedRule = result.rule;
			setSelectedRule(updatedRule);
			syncEditForm(updatedRule);
			setIsEditingRule(false);

			const nextRules = rules.map((ruleItem) =>
				ruleItem.id === updatedRule.id
					? {
							...ruleItem,
							name: updatedRule.name,
							language: updatedRule.language,
							severity: updatedRule.severity,
							source: updatedRule.source,
							correct: updatedRule.correct,
							is_active: updatedRule.is_active,
							created_at: updatedRule.created_at,
						}
					: ruleItem,
			);
			setRules(nextRules);
			setOpengrepActiveRules(nextRules.filter((item) => item.is_active));

			toast.success(result.message || "规则保存成功");
			loadRuleStats();
		} catch (error: any) {
			console.error("Failed to update rule:", error);
			const message = error?.response?.data?.detail || "保存规则失败";
			toast.error(message);
		} finally {
			setSavingRule(false);
		}
	};

	const handleDeleteRule = async () => {
		if (isGitleaksEngine) {
			showGitleaksNotReady();
			return;
		}
		if (!pendingDeleteRule) return;
		const deletingTarget = pendingDeleteRule;
		try {
			setDeletingRule(true);
			await deleteOpengrepRule(deletingTarget.id);
			toast.success(`规则「${deletingTarget.name}」删除成功`);
			setGeneratingRules((prev) => {
				if (!prev.has(deletingTarget.id)) {
					return prev;
				}
				const next = new Map(prev);
				next.delete(deletingTarget.id);
				if (next.size === 0) {
					setShowGeneratingQueue(false);
				}
				return next;
			});
			await loadRules({ silent: true });
			await loadRuleStats();
			// 从生成队列中移除已删除的规则
			await loadGeneratingRules();
			setShowRuleDetail(false);
			setIsEditingRule(false);
			setPendingDeleteRule(null);
		} catch (error) {
			console.error("Failed to delete rule:", error);
			toast.error("删除规则失败");
		} finally {
			setDeletingRule(false);
		}
	};

	const handleGenerateRule = async () => {
		if (isGitleaksEngine) {
			showGitleaksNotReady();
			return;
		}
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
		if (isGitleaksEngine) {
			showGitleaksNotReady();
			return;
		}
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
				severity: "ERROR",
				...(manualRuleForm.confidence && {
					confidence: manualRuleForm.confidence,
				}),
				...(manualRuleForm.description && {
					description: manualRuleForm.description,
				}),
				...(manualRuleForm.cwe.length > 0 && { cwe: manualRuleForm.cwe }),
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
				severity: "ERROR",
				confidence: "",
				description: "",
				cwe: [],
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
		if (isGitleaksEngine) {
			showGitleaksNotReady();
			return;
		}
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
		if (isGitleaksEngine) {
			showGitleaksNotReady();
			return;
		}
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

	const handleUploadPatchArchive = async () => {
		if (isGitleaksEngine) {
			showGitleaksNotReady();
			return;
		}
		if (!patchArchive) {
			toast.error("请选择 Patch 压缩包");
			return;
		}
		try {
			setUploadingRules(true);
			const result = await uploadPatchArchive(patchArchive);

			const { message, rule_ids } = result;

			toast.success(`${message}`);

			// 关闭上传对话框
			setShowEventDialog(false);
			setPatchArchive(null);
			setEventRuleUploadTab("manual");

			if (rule_ids.length > 0) {
				void startPollingRules(rule_ids);
			} else {
				await loadGeneratingRules();
			}
		} catch (error: any) {
			const message =
				error?.response?.data?.detail ||
				error?.message ||
				"上传 Patch 压缩包失败";
			toast.error(message);
		} finally {
			setUploadingRules(false);
		}
	};

	const handleUploadPatchDirectory = async () => {
		if (isGitleaksEngine) {
			showGitleaksNotReady();
			return;
		}
		if (patchDirectoryFiles.length === 0) {
			toast.error("请选择 Patch 文件");
			return;
		}
		try {
			setUploadingRules(true);
			const result = await uploadPatchDirectory(patchDirectoryFiles);

			const { message, rule_ids } = result;

			toast.success(`${message}`);

			// 关闭上传对话框
			setShowEventDialog(false);
			setPatchDirectoryFiles([]);
			setEventRuleUploadTab("manual");

			if (rule_ids.length > 0) {
				void startPollingRules(rule_ids);
			} else {
				await loadGeneratingRules();
			}
		} catch (error: any) {
			const message =
				error?.response?.data?.detail ||
				error?.message ||
				"上传 Patch 目录失败";
			toast.error(message);
		} finally {
			setUploadingRules(false);
		}
	};

	const startPollingRules = async (ruleIds: string[]) => {
		if (isGitleaksEngine) {
			showGitleaksNotReady();
			return;
		}
		// 初始化生成队列显示，先获取所有规则信息
		const initialProgress = new Map<
			string,
			{ name: string; progress: number; status: string }
		>();

		for (const ruleId of ruleIds) {
			try {
				const rule = await getOpengrepRule(ruleId);
				initialProgress.set(ruleId, {
					name: rule.name || ruleId,
					progress: 0,
					status: "等待处理中...",
				});
			} catch (error) {
				console.error(`获取规则信息失败 ${ruleId}:`, error);
				initialProgress.set(ruleId, {
					name: ruleId,
					progress: 0,
					status: "加载中...",
				});
			}
		}

		setGeneratingRules(initialProgress);
		setShowGeneratingQueue(true);

		// 启动后台轮询任务
		const maxAttempts = 300; // 5 分钟（300 * 1000ms）
		const pollInterval = 1000; // 1 秒

		for (let attempt = 0; attempt < maxAttempts; attempt++) {
			let allComplete = true;
			let successCount = 0;
			let failedCount = 0;
			const progressMap = new Map<
				string,
				{ name: string; progress: number; status: string }
			>();

			for (let index = 0; index < ruleIds.length; index++) {
				const ruleId = ruleIds[index];
				const elapsed = (attempt * pollInterval) / 1000;

				try {
					const rule = await getOpengrepRule(ruleId);

					// 获取最新的规则名称
					const ruleName = rule.name || ruleId;

					if (rule.correct === true) {
						// 规则生成成功
						successCount++;
						progressMap.set(ruleId, {
							name: ruleName,
							progress: 100,
							status: "✓ 生成成功",
						});
					} else if (
						rule.correct === false &&
						rule.pattern_yaml &&
						rule.pattern_yaml.includes("error")
					) {
						// 规则生成失败
						failedCount++;
						progressMap.set(ruleId, {
							name: ruleName,
							progress: 100,
							status: "✗ 生成失败",
						});
					} else {
						// 仍在生成中
						allComplete = false;
						// 估计进度（基于已用时间）
						const estimatedProgress = Math.min(
							Math.floor((elapsed / 30) * 100),
							95,
						);
						progressMap.set(ruleId, {
							name: ruleName,
							progress: estimatedProgress,
							status: "生成中...",
						});
					}
				} catch (error) {
					console.error(`轮询规则 ${ruleId} 失败:`, error);
					// 保留之前的规则名称，只更新状态
					const existing = generatingRules.get(ruleId);
					progressMap.set(ruleId, {
						name: existing?.name || ruleId,
						progress: 0,
						status: "查询失败",
					});
					allComplete = false;
				}
			}

			// 更新进度显示
			setGeneratingRules(new Map(progressMap));

			if (allComplete) {
				// 所有规则处理完成
				toast.success(
					`规则生成完成: 成功 ${successCount}，失败 ${failedCount}`,
					{ duration: 5 },
				);

				// 关闭生成队列显示
				setTimeout(() => {
					setShowGeneratingQueue(false);
					setGeneratingRules(new Map());
				}, 3000);

				await loadRules({ silent: true });
				await loadRuleStats();
				await loadGeneratingRules();
				break;
			}

			// 等待后再轮询
			await new Promise((resolve) => setTimeout(resolve, pollInterval));
		}

		// 超时未完成，关闭显示但保留在队列中
		setShowGeneratingQueue(false);
		// 最后一次更新生成队列状态
		await loadGeneratingRules();
	};

	const handleBatchUpdateRules = async (
		selectedRows: OpengrepRule[],
		filteredRows: OpengrepRule[],
		isActive: boolean,
	) => {
		if (isGitleaksEngine) {
			showGitleaksNotReady();
			return;
		}
		const targetRows = selectedRows.length > 0 ? selectedRows : filteredRows;
		if (targetRows.length === 0) {
			toast.error("当前没有可操作的规则");
			return;
		}

		try {
			setBatchOperating(true);
			const result = await batchUpdateOpengrepRules({
				rule_ids: targetRows.map((row) => row.id),
				is_active: isActive,
			});
			toast.success(result.message);
			setTableState((current) => ({ ...current, rowSelection: {} }));
			await loadRules({ silent: true });
			await loadRuleStats();
		} catch (error) {
			console.error("Batch operation failed:", error);
			toast.error("批量操作失败");
		} finally {
			setBatchOperating(false);
		}
	};

	const isHighlightedRule = (rule: OpengrepRule) => {
		if (!highlightRuleKeyword) return false;
		const keyword = highlightRuleKeyword.toLowerCase();
		return (
			rule.id.toLowerCase().includes(keyword) ||
			rule.name.toLowerCase().includes(keyword)
		);
	};

	function normalizeConfidence(confidence?: string | null) {
		const normalized = confidence?.trim().toUpperCase();
		if (!normalized) return "";
		if (normalized === "MIDIUM" || normalized === "MIDDLE") {
			return "MEDIUM";
		}
		return normalized;
	}

	const getConfidenceLabel = (confidence?: string | null) => {
		const normalized = normalizeConfidence(confidence);
		if (!normalized) return "";
		if (normalized === "HIGH") return "高";
		if (normalized === "MEDIUM") return "中";
		if (normalized === "LOW") return "低";
		return normalized;
	};

	const getConfidenceColor = (confidence?: string | null) => {
		const normalized = normalizeConfidence(confidence);
		if (normalized === "HIGH") {
			return "bg-emerald-500/20 text-emerald-300 border-emerald-500/30";
		}
		if (normalized === "MEDIUM") {
			return "bg-amber-500/20 text-amber-300 border-amber-500/30";
		}
		return "bg-sky-500/20 text-sky-300 border-sky-500/30";
	};

	const getSourceBadge = (source: string) => {
		return source === "patch" ? "补丁生成" : "内置规则";
	};

	const languageOptions = useMemo(
		() =>
			availableLanguages.map((language) => ({
				label: language,
				value: language,
			})),
		[availableLanguages],
	);

	const sourceOptions = useMemo(
		() =>
			RULE_SOURCES.map((source) => ({
				label: source.label,
				value: source.value,
			})),
		[],
	);

	const confidenceOptions = useMemo(
		() => [
			{ label: getConfidenceLabel("HIGH"), value: "HIGH" },
			{ label: getConfidenceLabel("MEDIUM"), value: "MEDIUM" },
			{ label: getConfidenceLabel("LOW"), value: "LOW" },
		],
		[],
	);

	const columns = useMemo<AppColumnDef<OpengrepRule, unknown>[]>(
		() => [
			{
				id: "rowNumber",
				header: "序号",
				enableSorting: false,
				enableHiding: false,
				meta: { label: "序号", align: "center", width: 72 },
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
				id: "ruleName",
				accessorFn: (row) => [row.name, row.id].filter(Boolean).join(" "),
				header: "规则名称",
				meta: { label: "规则名称", minWidth: 240, filterVariant: "text" },
				cell: ({ row }) => (
					<div
						className={
							isHighlightedRule(row.original)
								? "rounded-sm border border-primary/40 bg-primary/10 p-2"
								: "space-y-0.5"
						}
					>
						<div className="font-semibold text-foreground break-all">
							{row.original.name}
						</div>
						{/* <div className="font-mono text-xs text-muted-foreground break-all">
							{row.original.id}
						</div> */}
					</div>
				),
			},
			{
				id: "language",
				accessorFn: (row) => row.language || "",
				header: "语言",
				enableSorting: false,
				enableHiding: false,
				meta: {
					label: "语言",
					width: 120,
					filterVariant: "select",
					filterOptions: languageOptions,
				},
				cell: ({ row }) => (
					<span className="font-mono text-sm text-muted-foreground">
						{row.original.language}
					</span>
				),
			},
			{
				id: "source",
				accessorFn: (row) => row.source || "",
				header: "规则来源",
				enableSorting: false,
				enableHiding: false,
				meta: {
					label: "规则来源",
					width: 120,
					filterVariant: "select",
					filterOptions: sourceOptions,
				},
				cell: ({ row }) => (
					<Badge
						className={`cyber-badge ${
							row.original.source === "patch"
								? "cyber-badge-warning"
								: "cyber-badge-info"
						}`}
					>
						{getSourceBadge(row.original.source)}
					</Badge>
				),
			},
			{
				id: "confidence",
				accessorFn: (row) => normalizeConfidence(row.confidence),
				header: "置信度",
				enableSorting: false,
				enableHiding: false,
				meta: {
					label: "置信度",
					width: 120,
					filterVariant: "select",
					filterOptions: confidenceOptions,
				},
				cell: ({ row }) =>
					row.original.confidence ? (
						<Badge
							className={`cyber-badge ${getConfidenceColor(row.original.confidence)}`}
						>
							{getConfidenceLabel(row.original.confidence)}
						</Badge>
					) : (
						<span className="text-sm text-muted-foreground">-</span>
					),
			},
			{
				id: "status",
				accessorFn: (row) => String(row.is_active),
				header: "启用状态",
				enableSorting: false,
				enableHiding: false,
				meta: {
					label: "启用状态",
					width: 136,
					filterVariant: "select",
					filterOptions: ACTIVE_STATUS.filter(
						(status) => status.value === "true" || status.value === "false",
					),
				},
				cell: ({ row }) => (
					<Badge
						className={
							row.original.is_active
								? "cyber-badge cyber-badge-success"
								: "cyber-badge cyber-badge-muted"
						}
					>
						{row.original.is_active ? "已启用" : "已禁用"}
					</Badge>
				),
			},
			// {
			// 	id: "correct",
			// 	accessorFn: (row) => (row.correct ? "correct" : "uncertain"),
			// 	header: "验证状态",
			// 	meta: { label: "验证状态", width: 120 },
			// 	cell: ({ row }) => (
			// 		<span
			// 			className={
			// 				row.original.correct
			// 					? "text-sm text-emerald-400"
			// 					: "text-sm text-amber-400"
			// 			}
			// 		>
			// 			{row.original.correct ? "✓ 正确" : "⚠ 未验证"}
			// 		</span>
			// 	),
			// },
			// {
			// 	id: "createdAt",
			// 	accessorFn: (row) => row.created_at || "",
			// 	header: "创建时间",
			// 	meta: { label: "创建时间", width: 150 },
			// 	cell: ({ row }) => (
			// 		<span className="text-sm text-muted-foreground">
			// 			{new Date(row.original.created_at).toLocaleDateString("zh-CN")}
			// 		</span>
			// 	),
			// },
			{
				id: "actions",
				header: "操作",
				enableSorting: false,
				enableHiding: false,
				meta: { label: "操作", minWidth: 320 },
				cell: ({ row }) => (
					<div className="flex flex-wrap items-center gap-2">
						<Button
							size="sm"
							variant="outline"
							onClick={() => void handleViewRule(row.original)}
							className="cyber-btn-outline h-8 text-xs"
						>
							详情
						</Button>
						<Button
							size="sm"
							variant="outline"
							onClick={() => void handleViewRule(row.original, { edit: true })}
							className="cyber-btn-outline h-8 text-xs"
						>
							编辑
						</Button>
						<Button
							size="sm"
							variant="outline"
							onClick={() => void handleToggleRule(row.original)}
							className={
								row.original.is_active
									? "cyber-btn-outline h-8 text-xs"
									: "cyber-btn-primary h-8 text-xs"
							}
						>
							{row.original.is_active ? "禁用" : "启用"}
						</Button>
						<Button
							size="sm"
							variant="outline"
							onClick={() =>
								setPendingDeleteRule({
									id: row.original.id,
									name: row.original.name,
								})
							}
							className="cyber-btn-outline h-8 text-xs"
						>
							删除
						</Button>
					</div>
				),
			},
		],
		[availableLanguages, confidenceOptions, highlightRuleKeyword],
	);

	return (
		<div
			className={`flex flex-col bg-background font-mono relative ${embedded ? "" : "h-screen overflow-hidden"}`}
		>
			{/* Grid background */}
			<div className="absolute inset-0 cyber-grid-subtle pointer-events-none" />

			{/* Scrollable Content */}
			<div className={`flex-1 ${embedded ? "" : "overflow-y-auto"}`}>
				<div className="space-y-6 p-6 relative z-10">
					{returnTo && (
						<div className="cyber-card p-3 border border-primary/40 bg-primary/5 flex items-center justify-between gap-3">
							<div className="text-xs text-muted-foreground font-mono">
								{highlightRuleKeyword
									? `已跳转命中规则：${highlightRuleKeyword}`
									: "已从扫描结果跳转到规则详情"}
							</div>
							<Button
								type="button"
								variant="outline"
								className="cyber-btn-outline h-8"
								onClick={() => navigate(returnTo)}
							>
								<ArrowLeft className="w-3 h-3 mr-1" />
								返回扫描结果
							</Button>
						</div>
					)}

					{/* Stats Cards */}
					<div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4 relative z-10">
						<div className="cyber-card p-4">
							<div className="flex items-center justify-between">
								<div>
									<p className="stat-label">有效规则总数</p>
									<div className="flex items-end gap-3">
										<p className="stat-value">{ruleStats.total}</p>
										<p className="text-sm mb-1 flex items-center gap-3">
											<span className="inline-flex items-center gap-1 text-emerald-400">
												<span className="w-2 h-2 rounded-full bg-emerald-400" />
												已启用 {ruleStats.active}
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
									<p className="stat-label">支持编程语言个数</p>
									<p className="stat-value">{ruleStats.languageCount}</p>
								</div>
								<div className="stat-icon text-indigo-400">
									<Code className="w-6 h-6" />
								</div>
							</div>
						</div>

						<div className="cyber-card p-4">
							<div className="flex items-center justify-between">
								<div>
									<p className="stat-label">支持漏洞类型数量</p>
									<p className="stat-value">
										{ruleStats.vulnerabilityTypeCount}
									</p>
								</div>
								<div className="stat-icon text-amber-400">
									<AlertTriangle className="w-6 h-6" />
								</div>
							</div>
						</div>
					</div>

					<div className="cyber-card relative z-10 overflow-hidden">
						{generatingRules.size > 0 && (
							<div className="border-b border-cyan-500/30 bg-background/70">
								<div className="space-y-4 p-4">
									<div className="flex items-center justify-between">
										<div className="flex items-center gap-3">
											<div className="relative h-5 w-5">
												<div className="absolute inset-0 rounded-full bg-cyan-500 opacity-50 animate-pulse" />
												<div
													className="absolute inset-1 rounded-full border border-cyan-400 animate-spin"
													style={{ animationDuration: "2s" }}
												/>
											</div>
											<h3 className="font-mono text-lg font-bold text-cyan-400">
												补丁规则生成队列
											</h3>
											<Badge
												variant="outline"
												className="border-cyan-500 text-cyan-400"
											>
												{generatingRules.size} 个
											</Badge>
										</div>
										<Button
											variant="ghost"
											size="sm"
											onClick={() =>
												setShowGeneratingQueue(!showGeneratingQueue)
											}
											className="text-muted-foreground hover:text-cyan-400"
										>
											{showGeneratingQueue ? "▼" : "▶"}
										</Button>
									</div>

									{showGeneratingQueue ? (
										<div className="max-h-96 space-y-3 overflow-y-auto">
											{Array.from(generatingRules.entries()).map(
												([ruleId, { name, status }]) => (
													<div
														key={ruleId}
														className="space-y-2 rounded border border-cyan-500/30 bg-black/30 p-3"
													>
														<div className="flex items-center justify-between">
															<div className="flex-1">
																<p className="truncate font-mono text-sm text-cyan-300">
																	{name}
																</p>
															</div>
															<span className="ml-2 whitespace-nowrap font-mono text-xs text-muted-foreground">
																{status}
															</span>
														</div>
														<div className="flex items-center justify-between">
															<span className="font-mono text-xs text-muted-foreground">
																状态
															</span>
															<Button
																variant="ghost"
																size="sm"
																onClick={() => {
																	void handleViewRuleById(ruleId);
																}}
																className="h-auto px-2 py-1 text-xs text-cyan-400 hover:text-cyan-300"
															>
																查看详情
															</Button>
														</div>
													</div>
												),
											)}
										</div>
									) : null}
								</div>
							</div>
						)}

						<DataTable
							data={rules}
							columns={columns}
							state={tableState}
							onStateChange={setTableState}
							loading={loading}
							error={loadError || undefined}
							emptyState={{
								title: "未找到规则",
								description:
									tableState.globalFilter ||
									languageFilter ||
									sourceFilter ||
									confidenceFilter ||
									activeFilter
										? "调整筛选条件尝试"
										: "暂无规则数据",
							}}
							toolbar={{
								searchPlaceholder: t(
									"opengrep.searchPlaceholder",
									"搜索规则名称或ID...",
								),
								leadingActions: showEngineSelector ? (
									<div className="min-w-[150px]">
										<Select
											value={engineValue}
											onValueChange={(value) => {
												if (isScanEngineTab(value)) {
													onEngineChange?.(value);
												}
											}}
										>
											<SelectTrigger className="cyber-input h-10 min-w-[150px]">
												<SelectValue placeholder="选择引擎" />
											</SelectTrigger>
											<SelectContent className="cyber-dialog border-border">
												{SCAN_ENGINE_SELECTOR_OPTIONS.filter(
													(option) => option.value === "opengrep",
												).map((option) => (
													<SelectItem key={option.value} value={option.value}>
														{option.label}
													</SelectItem>
												))}
											</SelectContent>
										</Select>
									</div>
								) : undefined,
								trailingActions: (
									<>
										{/* {generatingRules.size > 0 ? (
											<Button
												onClick={() => setShowGeneratingQueue(!showGeneratingQueue)}
												className="cyber-btn-primary h-9 bg-cyan-950 border-cyan-500 hover:bg-cyan-900"
											>
												<div className="relative mr-2 h-3 w-3">
													<div className="absolute inset-0 rounded-full bg-cyan-400 opacity-50 animate-pulse" />
												</div>
												生成队列 ({generatingRules.size})
											</Button>
										) : null} */}
									</>
								),
								showGlobalSearch: false,
								showColumnVisibility: false,
								showDensityToggle: false,
								showReset: false,
							}}
							selection={
								!loading && rules.length > 0
									? {
											enableRowSelection: true,
											summary: buildSelectionSummary,
											actions: ({ selectedRows, table }) => {
												const filteredRows = table
													.getFilteredRowModel()
													.rows.map((row) => row.original);
												return (
													<>
														<Button
															onClick={() =>
																void handleBatchUpdateRules(
																	selectedRows,
																	filteredRows,
																	true,
																)
															}
															disabled={batchOperating}
															className="cyber-btn-primary h-8 text-sm"
														>
															{batchOperating ? "处理中..." : "批量启用"}
														</Button>
														<Button
															onClick={() =>
																void handleBatchUpdateRules(
																	selectedRows,
																	filteredRows,
																	false,
																)
															}
															disabled={batchOperating}
															className="cyber-btn-outline h-8 text-sm"
														>
															{batchOperating ? "处理中..." : "批量禁用"}
														</Button>
														<Button
															onClick={() => {
																if (isGitleaksEngine) {
																	showGitleaksNotReady();
																	return;
																}
																setShowRuleTypeDialog(true);
															}}
															className="cyber-btn-primary h-9"
														>
															新建规则
														</Button>
													</>
												);
											},
										}
									: undefined
							}
							pagination={{ enabled: true, pageSizeOptions: [10, 20, 50, 100] }}
							tableClassName="min-w-[1380px]"
							getRowId={(row) => row.id}
						/>
					</div>

					{/* Rule Detail Dialog */}
					<Dialog
						open={showRuleDetail}
						onOpenChange={(open) => {
							setShowRuleDetail(open);
							if (!open) {
								setIsEditingRule(false);
							}
						}}
					>
						<DialogContent
							aria-describedby={undefined}
							className="!w-[min(90vw,900px)] !max-w-none max-h-[90vh] flex flex-col p-0 gap-0 cyber-dialog border border-border rounded-lg"
						>
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
										{/* Basic Info */}
										<div className="space-y-3">
											<h3 className="font-mono font-bold uppercase text-sm text-muted-foreground border-b border-border pb-2">
												基本信息
											</h3>
											<div className="grid grid-cols-2 gap-4 text-sm font-mono">
												<div>
													<p className="text-muted-foreground">名称</p>
													{isEditingRule ? (
														<Input
															value={editRuleForm.name}
															onChange={(e) =>
																setEditRuleForm((prev) => ({
																	...prev,
																	name: e.target.value,
																}))
															}
															className="cyber-input mt-1.5 h-9"
														/>
													) : (
														<p className="text-foreground font-bold mt-1">
															{selectedRule.name}
														</p>
													)}
												</div>
												<div>
													<p className="text-muted-foreground">规则ID</p>
													<p className="text-foreground font-bold mt-1 break-all">
														{selectedRule.id}
													</p>
												</div>
												<div>
													<p className="text-muted-foreground">编程语言</p>
													{isEditingRule ? (
														<Input
															value={editRuleForm.language}
															onChange={(e) =>
																setEditRuleForm((prev) => ({
																	...prev,
																	language: e.target.value,
																}))
															}
															className="cyber-input mt-1.5 h-9"
														/>
													) : (
														<p className="text-foreground font-bold mt-1">
															{selectedRule.language}
														</p>
													)}
												</div>
												<div>
													<p className="text-muted-foreground">规则来源</p>
													<Badge
														className={`cyber-badge mt-1 ${selectedRule.source === "patch" ? "cyber-badge-warning" : "cyber-badge-info"}`}
													>
														{getSourceBadge(selectedRule.source)}
													</Badge>
												</div>
												<div>
													<p className="text-muted-foreground">
														验证状态 / 置信度 / 相关CWE
													</p>
													<div className="mt-2 flex flex-wrap gap-2">
														<Badge
															className={`cyber-badge ${
																selectedRule.correct
																	? "bg-emerald-500/20 text-emerald-300 border-emerald-500/30"
																	: "bg-amber-500/20 text-amber-300 border-amber-500/30"
															}`}
														>
															{selectedRule.correct ? "✓ 正确" : "⚠ 未验证"}
														</Badge>
														{selectedRule.confidence && (
															<Badge
																className={`cyber-badge ${getConfidenceColor(selectedRule.confidence)}`}
															>
																{getConfidenceLabel(selectedRule.confidence)}
															</Badge>
														)}
														{selectedRule.cwe && selectedRule.cwe.length > 0 ? (
															selectedRule.cwe.map((cwe, idx) => (
																<Badge
																	key={idx}
																	className="cyber-badge bg-violet-500/20 text-violet-300 border-violet-500/30"
																	title={formatRuleCweDisplayTitle(cwe)}
																>
																	{formatRuleCweDisplayLabel(cwe)}
																</Badge>
															))
														) : (
															<span className="text-xs text-muted-foreground mt-1">
																未关联CWE
															</span>
														)}
													</div>
												</div>
											</div>
										</div>

										{/* Description */}
										{selectedRule.description && (
											<div className="space-y-3">
												<h3 className="font-mono font-bold uppercase text-sm text-muted-foreground border-b border-border pb-2">
													规则描述
												</h3>
												<p className="text-sm text-foreground whitespace-pre-wrap break-words">
													{selectedRule.description}
												</p>
											</div>
										)}

										<div className="space-y-3">
											<div className="flex items-center justify-between">
												<h3 className="font-mono font-bold uppercase text-sm text-muted-foreground">
													规则模式
												</h3>
												{!isEditingRule && (
													<Button
														size="sm"
														variant="ghost"
														onClick={() => {
															navigator.clipboard.writeText(
																selectedRule.pattern_yaml,
															);
															toast.success("已复制到剪贴板");
														}}
														className="cyber-btn-ghost h-7 text-xs"
													>
														<Copy className="w-3 h-3" />
													</Button>
												)}
											</div>
											<div className="bg-muted border border-border rounded p-4">
												{isEditingRule ? (
													<Textarea
														value={editRuleForm.pattern_yaml}
														onChange={(e) =>
															setEditRuleForm((prev) => ({
																...prev,
																pattern_yaml: e.target.value,
															}))
														}
														className="cyber-input font-mono text-xs min-h-80 cursor-text"
													/>
												) : (
													<pre className="text-xs font-mono text-foreground whitespace-pre-wrap break-words">
														{selectedRule.pattern_yaml}
													</pre>
												)}
											</div>
										</div>

										{/* Patch Info */}
										{selectedRule.source === "patch" && selectedRule.patch && (
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
													{new Date(selectedRule.created_at).toLocaleString(
														"zh-CN",
													)}
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
										onClick={handleSaveRule}
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
								) : (
									<Button
										variant="outline"
										onClick={handleStartEditRule}
										className="cyber-btn-outline"
									>
										<PencilLine className="w-4 h-4 mr-2" />
										编辑规则
									</Button>
								)}
								<Button
									variant="outline"
									onClick={() =>
										selectedRule &&
										setPendingDeleteRule({
											id: selectedRule.id,
											name: selectedRule.name,
										})
									}
									disabled={isEditingRule || savingRule}
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
						<DialogContent
							aria-describedby={undefined}
							className="cyber-dialog max-w-xl border-border"
						>
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
										通用型漏洞检测规则
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
										CVE漏洞检测规则
									</span>
								</Button>
							</div>
						</DialogContent>
					</Dialog>

					{/* Generic Rule Dialog */}
					<Dialog open={showGenericDialog} onOpenChange={setShowGenericDialog}>
						<DialogContent
							aria-describedby={undefined}
							className="cyber-dialog max-w-3xl border-border max-h-[90vh] flex flex-col"
						>
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
													规则 ID{" "}
													<span className="text-muted-foreground/60">
														(可选)
													</span>
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

											{/* Confidence (Optional) */}
											<div>
												<Label className="font-mono font-bold uppercase text-xs text-muted-foreground">
													置信度{" "}
													<span className="text-muted-foreground/60">
														(可选)
													</span>
												</Label>
												<Select
													value={manualRuleForm.confidence}
													onValueChange={(value) =>
														setManualRuleForm({
															...manualRuleForm,
															confidence: value,
														})
													}
												>
													<SelectTrigger className="cyber-input mt-1.5 font-mono text-xs">
														<SelectValue placeholder="未设置" />
													</SelectTrigger>
													<SelectContent>
														<SelectItem value="HIGH">
															{getConfidenceLabel("HIGH")}
														</SelectItem>
														<SelectItem value="MEDIUM">
															{getConfidenceLabel("MEDIUM")}
														</SelectItem>
														<SelectItem value="LOW">
															{getConfidenceLabel("LOW")}
														</SelectItem>
													</SelectContent>
												</Select>
											</div>

											{/* Description (Optional) */}
											<div className="col-span-2">
												<Label className="font-mono font-bold uppercase text-xs text-muted-foreground">
													规则描述{" "}
													<span className="text-muted-foreground/60">
														(可选)
													</span>
												</Label>
												<Textarea
													value={manualRuleForm.description}
													onChange={(e) =>
														setManualRuleForm({
															...manualRuleForm,
															description: e.target.value,
														})
													}
													placeholder="描述这个规则的作用和检测目标"
													className="cyber-input mt-1.5 font-mono text-xs min-h-20 cursor-text"
												/>
											</div>

											{/* CWE (Optional) */}
											<div className="col-span-2">
												<Label className="font-mono font-bold uppercase text-xs text-muted-foreground">
													CWE{" "}
													<span className="text-muted-foreground/60">
														(可选，用逗号分隔)
													</span>
												</Label>
												<Input
													value={manualRuleForm.cwe.join(", ")}
													onChange={(e) =>
														setManualRuleForm({
															...manualRuleForm,
															cwe: e.target.value
																.split(",")
																.map((c) => c.trim())
																.filter((c) => c),
														})
													}
													placeholder="例如: CWE-89, CWE-79, CWE-20"
													className="cyber-input mt-1.5 font-mono text-xs"
												/>
											</div>

											{/* Patch Link (Optional) */}
											<div className="col-span-2">
												<Label className="font-mono font-bold uppercase text-xs text-muted-foreground">
													补丁或相关链接{" "}
													<span className="text-muted-foreground/60">
														(可选)
													</span>
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
											<span className="text-rose-400">*</span> 表示必填项，规则
											YAML 必须包含 rules 数组和规则 id
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
											<div
												className="mt-1.5 border-2 border-dashed border-border rounded-lg p-6 text-center hover:border-primary/50 transition-colors cursor-pointer"
												onClick={() => {
													const input = document.createElement("input");
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
															✓ {compressedFile.name}
														</p>
														<p className="text-xs text-muted-foreground mt-1">
															({(compressedFile.size / 1024 / 1024).toFixed(2)}
															MB)
														</p>
													</div>
												) : (
													<div>
														<p className="text-sm font-mono text-muted-foreground">
															点击选择或拖拽上传
														</p>
														<p className="text-xs text-muted-foreground mt-2">
															支持: ZIP, TAR, TAR.GZ, TAR.BZ2, 7Z, RAR
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
											<div
												className="mt-1.5 border-2 border-dashed border-border rounded-lg p-6 text-center hover:border-primary/50 transition-colors cursor-pointer"
												onClick={() => {
													const input = document.createElement("input");
													input.type = "file";
													input.multiple = true;
													input.accept = ".yaml,.yml";
													input.onchange = (e) => {
														const files = Array.from(
															(e.target as HTMLInputElement).files || [],
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
															✓ 已选择 {directoryFiles.length} 个文件
														</p>
														<div className="text-xs text-muted-foreground mt-2 space-y-1 max-h-32 overflow-y-auto">
															{directoryFiles.slice(0, 5).map((f) => (
																<p key={f.name}>{f.name}</p>
															))}
															{directoryFiles.length > 5 && (
																<p>
																	... 及其他 {directoryFiles.length - 5} 个文件
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
															支持选择多个 YAML/YML 规则文件
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
											severity: "ERROR",
											confidence: "",
											description: "",
											cwe: [],
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
											} else if (genericRuleUploadTab === "compressed") {
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
											(genericRuleUploadTab === "compressed" &&
												!compressedFile) ||
											(genericRuleUploadTab === "directory" &&
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
												genericRuleUploadTab === "manual"
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
					<Dialog open={showEventDialog} onOpenChange={setShowEventDialog}>
						<DialogContent
							aria-describedby={undefined}
							className="cyber-dialog max-w-3xl border-border max-h-[90vh] flex flex-col"
						>
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
									事件型规则（Patch 规则）
								</DialogTitle>
							</DialogHeader>

							{/* Tab Selection */}
							<div className="flex-shrink-0 px-6 flex gap-2 border-b border-border">
								<button
									onClick={() => setEventRuleUploadTab("manual")}
									className={`px-4 py-2 font-mono text-xs font-bold uppercase border-b-2 transition-colors ${
										eventRuleUploadTab === "manual"
											? "border-primary text-primary"
											: "border-transparent text-muted-foreground hover:text-foreground"
									}`}
								>
									手动输入
								</button>
								<button
									onClick={() => setEventRuleUploadTab("archive")}
									className={`px-4 py-2 font-mono text-xs font-bold uppercase border-b-2 transition-colors ${
										eventRuleUploadTab === "archive"
											? "border-primary text-primary"
											: "border-transparent text-muted-foreground hover:text-foreground"
									}`}
								>
									压缩包上传
								</button>
								<button
									onClick={() => setEventRuleUploadTab("directory")}
									className={`px-4 py-2 font-mono text-xs font-bold uppercase border-b-2 transition-colors ${
										eventRuleUploadTab === "directory"
											? "border-primary text-primary"
											: "border-transparent text-muted-foreground hover:text-foreground"
									}`}
								>
									目录上传
								</button>
							</div>

							<div className="flex-1 overflow-y-auto p-6 space-y-4">
								{/* Manual Input Tab */}
								{eventRuleUploadTab === "manual" && (
									<>
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
									</>
								)}

								{/* Archive Upload Tab */}
								{eventRuleUploadTab === "archive" && (
									<div className="space-y-4">
										<div className="border border-dashed border-border rounded-lg p-6 text-center">
											<input
												type="file"
												id="patch-archive-input"
												accept=".zip"
												onChange={(e) => {
													const file = e.target.files?.[0];
													if (file) setPatchArchive(file);
												}}
												className="hidden"
											/>
											<Label
												htmlFor="patch-archive-input"
												className="cursor-pointer inline-flex flex-col items-center gap-2"
											>
												<div className="text-muted-foreground">
													点击选择 .zip 压缩包
												</div>
												{patchArchive && (
													<div className="text-xs text-primary font-mono">
														已选择: {patchArchive.name}
													</div>
												)}
											</Label>
										</div>
										<div className="text-xs text-muted-foreground font-mono space-y-1">
											<div>• 支持 .zip 格式压缩包</div>
											<div>
												• 压缩包内的 .patch 文件名格式:
												仓库owner_仓库名_哈希.patch
											</div>
											<div>• 系统会自动解压并处理所有 .patch 文件</div>
										</div>
									</div>
								)}

								{/* Directory Upload Tab */}
								{eventRuleUploadTab === "directory" && (
									<div className="space-y-4">
										<div className="border border-dashed border-border rounded-lg p-6 text-center">
											<input
												type="file"
												id="patch-directory-input"
												multiple
												onChange={(e) => {
													const files = Array.from(e.target.files || []);
													setPatchDirectoryFiles(files);
												}}
												ref={(node) => {
													if (!node) return;
													node.setAttribute("webkitdirectory", "");
													node.setAttribute("directory", "");
												}}
												className="hidden"
											/>
											<Label
												htmlFor="patch-directory-input"
												className="cursor-pointer inline-flex flex-col items-center gap-2"
											>
												<div className="text-muted-foreground">
													点击选择目录
												</div>
												{patchDirectoryFiles.length > 0 && (
													<div className="text-xs text-primary font-mono">
														已选择 {patchDirectoryFiles.length} 个文件
													</div>
												)}
											</Label>
										</div>
										<div className="text-xs text-muted-foreground font-mono space-y-1">
											<div>• 选择包含 .patch 文件的目录</div>
											<div>• 文件名格式: 仓库owner_仓库名_哈希.patch</div>
											<div>• 系统会自动过滤并处理所有 .patch 文件</div>
										</div>
									</div>
								)}
							</div>

							<div className="flex-shrink-0 flex justify-between gap-3 px-6 py-4 bg-muted border-t border-border">
								<Button
									variant="outline"
									onClick={() => {
										setShowEventDialog(false);
										setShowRuleTypeDialog(true);
									}}
									className="cyber-btn-outline"
									disabled={generatingRule || uploadingRules}
								>
									返回
								</Button>
								<div className="flex items-center gap-3">
									<Button
										variant="outline"
										onClick={() => setShowEventDialog(false)}
										className="cyber-btn-outline"
										disabled={generatingRule || uploadingRules}
									>
										取消
									</Button>
									{eventRuleUploadTab === "manual" && (
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
									)}
									{eventRuleUploadTab === "archive" && (
										<Button
											onClick={handleUploadPatchArchive}
											className="cyber-btn-primary"
											disabled={uploadingRules || !patchArchive}
										>
											{uploadingRules ? (
												<>
													<div className="loading-spinner mr-2" />
													上传中...
												</>
											) : (
												<>上传压缩包</>
											)}
										</Button>
									)}
									{eventRuleUploadTab === "directory" && (
										<Button
											onClick={handleUploadPatchDirectory}
											className="cyber-btn-primary"
											disabled={
												uploadingRules || patchDirectoryFiles.length === 0
											}
										>
											{uploadingRules ? (
												<>
													<div className="loading-spinner mr-2" />
													上传中...
												</>
											) : (
												<>上传目录</>
											)}
										</Button>
									)}
								</div>
							</div>
						</DialogContent>
					</Dialog>
				</div>
			</div>
		</div>
	);
}
