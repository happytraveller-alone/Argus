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
import { Textarea } from "@/components/ui/textarea";
import {
	AlertCircle,
	AlertTriangle,
	ChevronLeft,
	ChevronRight,
	Database,
	Search,
	Tag,
} from "lucide-react";
import {
	batchUpdateGitleaksRules,
	createGitleaksRule,
	deleteGitleaksRule,
	getGitleaksRules,
	type GitleaksRule,
	updateGitleaksRule,
} from "@/shared/api/gitleaks";

type EngineTab = "opengrep" | "gitleaks" | "bandit" | "phpstan";

interface GitleaksRulesProps {
	showEngineSelector?: boolean;
	engineValue?: EngineTab;
	onEngineChange?: (value: EngineTab) => void;
}

const SOURCE_LABEL_MAP: Record<string, string> = {
	builtin: "内置规则",
	custom: "自定义规则",
};

const getSourceLabel = (source?: string) => {
	if (!source) return "未知来源";
	return SOURCE_LABEL_MAP[source] ?? source;
};

const DEFAULT_FORM = {
	name: "",
	description: "",
	rule_id: "",
	secret_group: "0",
	regex: "",
	keywords: "",
	path: "",
	tags: "",
	entropy: "",
	source: "custom",
	is_active: true,
};

export default function GitleaksRules({
	showEngineSelector = false,
	engineValue = "gitleaks",
	onEngineChange,
}: GitleaksRulesProps) {
	const [rules, setRules] = useState<GitleaksRule[]>([]);
	const [loading, setLoading] = useState(true);
	const [searchTerm, setSearchTerm] = useState("");
	const [selectedSource, setSelectedSource] = useState("");
	const [selectedActiveStatus, setSelectedActiveStatus] = useState("");
	const [selectedEntropyRange, setSelectedEntropyRange] = useState("");
	const [selectedRuleIds, setSelectedRuleIds] = useState<Set<string>>(new Set());
	const [batchOperating, setBatchOperating] = useState(false);
	const [showEditDialog, setShowEditDialog] = useState(false);
	const [editingRule, setEditingRule] = useState<GitleaksRule | null>(null);
	const [savingRule, setSavingRule] = useState(false);
	const [currentPage, setCurrentPage] = useState(1);
	const [pageSize, setPageSize] = useState(10);
	const [formData, setFormData] = useState(DEFAULT_FORM);

	const loadRules = async () => {
		try {
			setLoading(true);
			const data = await getGitleaksRules();
			setRules(data);
		} catch (error) {
			console.error("Failed to load gitleaks rules:", error);
			toast.error("加载 gitleaks 规则失败");
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
		const highEntropyCount = rules.filter(
			(rule) => rule.entropy !== null && rule.entropy !== undefined && rule.entropy >= 3,
		).length;
		return {
			total: rules.length,
			active,
			inactive: Math.max(rules.length - active, 0),
			sourceCount: sources.size,
			highEntropyCount,
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
					rule.rule_id.toLowerCase().includes(keyword) ||
					rule.regex.toLowerCase().includes(keyword) ||
					rule.id.toLowerCase().includes(keyword);

				const matchSource = !selectedSource || rule.source === selectedSource;
				const matchStatus =
					!selectedActiveStatus ||
					(selectedActiveStatus === "true" && rule.is_active) ||
					(selectedActiveStatus === "false" && !rule.is_active);
				const entropy = rule.entropy;
				const matchEntropy =
					!selectedEntropyRange ||
					(selectedEntropyRange === "high" &&
						entropy !== null &&
						entropy !== undefined &&
						entropy >= 4) ||
					(selectedEntropyRange === "medium" &&
						entropy !== null &&
						entropy !== undefined &&
						entropy >= 3 &&
						entropy < 4) ||
					(selectedEntropyRange === "low" &&
						entropy !== null &&
						entropy !== undefined &&
						entropy > 0 &&
						entropy < 3) ||
					(selectedEntropyRange === "none" &&
						(entropy === null || entropy === undefined));

				return matchSearch && matchSource && matchStatus && matchEntropy;
			}),
		[rules, searchTerm, selectedSource, selectedActiveStatus, selectedEntropyRange],
	);

	const totalPages = Math.max(1, Math.ceil(filteredRules.length / pageSize));
	const paginatedRules = filteredRules.slice(
		(currentPage - 1) * pageSize,
		currentPage * pageSize,
	);

	const resetForm = () => {
		setFormData(DEFAULT_FORM);
		setEditingRule(null);
	};

	const openCreateDialog = () => {
		resetForm();
		setShowEditDialog(true);
	};

	const openEditDialog = (rule: GitleaksRule) => {
		setEditingRule(rule);
		setFormData({
			name: rule.name,
			description: rule.description || "",
			rule_id: rule.rule_id,
			secret_group: String(rule.secret_group ?? 0),
			regex: rule.regex,
			keywords: (rule.keywords || []).join(", "),
			path: rule.path || "",
			tags: (rule.tags || []).join(", "),
			entropy:
				rule.entropy !== null && rule.entropy !== undefined
					? String(rule.entropy)
					: "",
			source: rule.source || "custom",
			is_active: rule.is_active,
		});
		setShowEditDialog(true);
	};

	const submitRule = async () => {
		if (editingRule?.source === "builtin") {
			toast.error("内置规则不支持直接编辑，请复制后创建自定义规则");
			return;
		}
		if (!formData.name.trim() || !formData.rule_id.trim() || !formData.regex.trim()) {
			toast.error("请填写规则名称、规则ID、正则表达式");
			return;
		}

		const payload = {
			name: formData.name.trim(),
			description: formData.description.trim() || undefined,
			rule_id: formData.rule_id.trim(),
			secret_group: Number(formData.secret_group || 0),
			regex: formData.regex.trim(),
			keywords: formData.keywords
				.split(",")
				.map((s) => s.trim())
				.filter(Boolean),
			path: formData.path.trim() || undefined,
			tags: formData.tags
				.split(",")
				.map((s) => s.trim())
				.filter(Boolean),
			entropy: formData.entropy.trim() ? Number(formData.entropy) : undefined,
			source: formData.source.trim() || "custom",
			is_active: formData.is_active,
		};

		try {
			setSavingRule(true);
			if (editingRule) {
				await updateGitleaksRule(editingRule.id, payload);
				toast.success("规则更新成功");
			} else {
				await createGitleaksRule(payload);
				toast.success("规则创建成功");
			}
			setShowEditDialog(false);
			resetForm();
			await loadRules();
		} catch (error: any) {
			const message = error?.response?.data?.detail || "保存规则失败";
			toast.error(message);
		} finally {
			setSavingRule(false);
		}
	};

	const handleDeleteRule = async (rule: GitleaksRule) => {
		if (rule.source === "builtin") {
			toast.error("内置规则不允许删除");
			return;
		}
		try {
			await deleteGitleaksRule(rule.id);
			toast.success(`规则「${rule.name}」已删除`);
			await loadRules();
		} catch (error: any) {
			toast.error(error?.response?.data?.detail || "删除规则失败");
		}
	};

	const handleToggleRule = async (rule: GitleaksRule) => {
		try {
			await updateGitleaksRule(rule.id, { is_active: !rule.is_active });
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
			const result = await batchUpdateGitleaksRules(payload);
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
							<p className="stat-label">高熵规则数量</p>
							<p className="stat-value">{stats.highEntropyCount}</p>
						</div>
						<div className="stat-icon text-cyan-400">
							<Tag className="w-6 h-6" />
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
									placeholder="搜索名称/ID/正则..."
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
									熵值区间
								</Label>
								<Select
									value={selectedEntropyRange || "all"}
									onValueChange={(val) =>
										setSelectedEntropyRange(val === "all" ? "" : val)
									}
								>
									<SelectTrigger className="cyber-input h-10 mt-1.5">
										<SelectValue placeholder="所有区间" />
									</SelectTrigger>
									<SelectContent className="cyber-dialog border-border">
										<SelectItem value="all">所有区间</SelectItem>
										<SelectItem value="high">高熵 (≥ 4)</SelectItem>
										<SelectItem value="medium">中熵 (3 - 4)</SelectItem>
										<SelectItem value="low">低熵 (0 - 3)</SelectItem>
										<SelectItem value="none">未设置熵值</SelectItem>
									</SelectContent>
								</Select>
							</div>

							<div className="min-w-[150px] flex-1">
								<Label className="font-mono font-bold uppercase text-xs text-muted-foreground">
									启用状态
								</Label>
								<Select
									value={selectedActiveStatus || "all"}
									onValueChange={(val) =>
										setSelectedActiveStatus(val === "all" ? "" : val)
									}
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
										setSelectedEntropyRange("");
										setSelectedActiveStatus("");
										setCurrentPage(1);
										setSelectedRuleIds(new Set());
									}}
								>
									重置
								</Button>
								<Button className="cyber-btn-primary h-10 min-w-[116px]" onClick={openCreateDialog}>
									新建规则
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
									{searchTerm ||
									selectedSource ||
									selectedEntropyRange ||
									selectedActiveStatus
										? "调整筛选条件尝试"
										: "暂无规则数据（系统将自动同步内置规则）"}
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
									<TableHead className="min-w-[280px]">规则名称</TableHead>
									<TableHead className="w-[110px] text-center">关键词数</TableHead>
									<TableHead className="w-[120px] text-center">密钥分组</TableHead>
									<TableHead className="w-[110px] text-center">熵值</TableHead>
									<TableHead className="w-[120px]">来源</TableHead>
									<TableHead className="w-[110px]">启用状态</TableHead>
									<TableHead className="w-[140px]">创建时间</TableHead>
									<TableHead className="min-w-[280px]">操作</TableHead>
								</TableRow>
							</TableHeader>
							<TableBody>
								{paginatedRules.map((rule, index) => {
									const builtinLocked = rule.source === "builtin";
									return (
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
														<div className="font-semibold text-foreground break-all">
															{rule.name}
														</div>
														{rule.rule_id !== rule.name ? (
															<div className="font-mono text-xs text-muted-foreground break-all">
																{rule.rule_id}
															</div>
														) : null}
													</div>
												</TableCell>
											<TableCell className="text-center text-sm text-muted-foreground">
												{rule.keywords?.length || 0}
											</TableCell>
											<TableCell className="text-center text-sm text-muted-foreground">
												{rule.secret_group ?? 0}
											</TableCell>
											<TableCell className="text-center text-sm text-muted-foreground">
												{rule.entropy === null || rule.entropy === undefined ? "-" : rule.entropy}
											</TableCell>
												<TableCell>
													<Badge className={builtinLocked ? "cyber-badge cyber-badge-info" : "cyber-badge cyber-badge-warning"}>
														{getSourceLabel(rule.source)}
													</Badge>
												</TableCell>
											<TableCell>
												<Badge className={rule.is_active ? "cyber-badge cyber-badge-success" : "cyber-badge cyber-badge-muted"}>
													{rule.is_active ? "已启用" : "已禁用"}
												</Badge>
											</TableCell>
											<TableCell className="text-sm text-muted-foreground">
												{new Date(rule.created_at).toLocaleDateString("zh-CN")}
											</TableCell>
												<TableCell>
													<div className="flex items-center gap-2 flex-wrap">
														{builtinLocked ? (
															<Badge className="cyber-badge cyber-badge-muted h-8 inline-flex items-center">
																内置只读
															</Badge>
														) : (
															<>
																<Button
																	size="sm"
																	variant="outline"
																	onClick={() => openEditDialog(rule)}
																	className="cyber-btn-ghost h-8 px-3 min-w-[64px]"
																>
																	编辑
																</Button>
																<Button
																	size="sm"
																	variant="outline"
																	onClick={() => {
																		if (window.confirm(`确认删除规则「${rule.name}」？`)) {
																			void handleDeleteRule(rule);
																		}
																	}}
																	className="cyber-btn-ghost h-8 px-3 min-w-[64px] hover:bg-rose-500/10 hover:text-rose-400"
																>
																	删除
																</Button>
															</>
														)}
														<Button
															size="sm"
															variant="outline"
															onClick={() => void handleToggleRule(rule)}
															className="cyber-btn-ghost h-8 px-3 min-w-[64px]"
														>
															{rule.is_active ? "禁用" : "启用"}
														</Button>
													</div>
												</TableCell>
										</TableRow>
									);
								})}
							</TableBody>
						</Table>

						<div className="flex items-center justify-between p-4 border-t border-border bg-muted/20">
							<div className="flex items-center gap-2">
								<Label className="text-xs font-mono text-muted-foreground">每页显示:</Label>
								<Select
									value={String(pageSize)}
									onValueChange={(value) => {
										setPageSize(Number(value));
										setCurrentPage(1);
									}}
								>
									<SelectTrigger className="cyber-input w-[80px] h-8">
										<SelectValue />
									</SelectTrigger>
									<SelectContent className="cyber-dialog border-border">
										<SelectItem value="10">10</SelectItem>
										<SelectItem value="20">20</SelectItem>
										<SelectItem value="50">50</SelectItem>
									</SelectContent>
								</Select>
							</div>
							<div className="text-xs font-mono text-muted-foreground">
								第 {currentPage} / {totalPages} 页 (共 {filteredRules.length} 条)
							</div>
							<div className="flex items-center gap-2">
								<Button
									size="sm"
									variant="outline"
									onClick={() => setCurrentPage(Math.max(1, currentPage - 1))}
									disabled={currentPage === 1}
									className="cyber-btn-ghost h-8 px-2 w-8"
								>
									<ChevronLeft className="w-4 h-4" />
								</Button>
								<Button
									size="sm"
									variant="outline"
									onClick={() => setCurrentPage(Math.min(totalPages, currentPage + 1))}
									disabled={currentPage === totalPages}
									className="cyber-btn-ghost h-8 px-2 w-8"
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
				open={showEditDialog}
				onOpenChange={(open) => {
					setShowEditDialog(open);
					if (!open) resetForm();
				}}
			>
				<DialogContent className="cyber-dialog max-w-3xl border-border max-h-[90vh] overflow-y-auto">
					<DialogHeader>
						<DialogTitle>{editingRule ? "编辑 Gitleaks 规则" : "新建 Gitleaks 规则"}</DialogTitle>
					</DialogHeader>
					<div className="grid grid-cols-1 md:grid-cols-2 gap-4">
						<div>
							<Label>规则名称 *</Label>
							<Input value={formData.name} onChange={(e) => setFormData({ ...formData, name: e.target.value })} className="cyber-input mt-1.5" />
						</div>
						<div>
							<Label>规则ID *</Label>
							<Input value={formData.rule_id} onChange={(e) => setFormData({ ...formData, rule_id: e.target.value })} className="cyber-input mt-1.5" />
						</div>
							<div>
								<Label>密钥分组</Label>
								<Input value={formData.secret_group} onChange={(e) => setFormData({ ...formData, secret_group: e.target.value })} className="cyber-input mt-1.5" />
							</div>
							<div>
								<Label>来源</Label>
								<Input
									value={
										editingRule?.source === "builtin"
											? getSourceLabel(editingRule.source)
											: formData.source
									}
									onChange={(e) =>
										setFormData({ ...formData, source: e.target.value })
									}
									className="cyber-input mt-1.5"
									disabled={editingRule?.source === "builtin"}
								/>
							</div>
							<div className="md:col-span-2">
								<Label>规则正则 *</Label>
								<Textarea value={formData.regex} onChange={(e) => setFormData({ ...formData, regex: e.target.value })} className="cyber-input mt-1.5 min-h-24 font-mono text-xs" />
							</div>
						<div className="md:col-span-2">
							<Label>描述</Label>
							<Textarea value={formData.description} onChange={(e) => setFormData({ ...formData, description: e.target.value })} className="cyber-input mt-1.5 min-h-20" />
						</div>
							<div>
								<Label>关键词（逗号分隔）</Label>
								<Input value={formData.keywords} onChange={(e) => setFormData({ ...formData, keywords: e.target.value })} className="cyber-input mt-1.5" />
							</div>
							<div>
								<Label>标签（逗号分隔）</Label>
								<Input value={formData.tags} onChange={(e) => setFormData({ ...formData, tags: e.target.value })} className="cyber-input mt-1.5" />
							</div>
							<div>
								<Label>路径正则（可选）</Label>
								<Input value={formData.path} onChange={(e) => setFormData({ ...formData, path: e.target.value })} className="cyber-input mt-1.5" />
							</div>
							<div>
								<Label>熵值（可选）</Label>
								<Input value={formData.entropy} onChange={(e) => setFormData({ ...formData, entropy: e.target.value })} className="cyber-input mt-1.5" />
							</div>
						<div className="md:col-span-2 flex items-center gap-2 pt-1">
							<Checkbox
								checked={formData.is_active}
								onCheckedChange={(checked) =>
									setFormData({ ...formData, is_active: checked === true })
								}
							/>
							<span className="text-sm">创建后立即启用</span>
						</div>
					</div>

					<div className="flex justify-end gap-2 pt-4">
						<Button variant="outline" className="cyber-btn-outline" onClick={() => setShowEditDialog(false)}>
							取消
						</Button>
						<Button className="cyber-btn-primary" onClick={() => void submitRule()} disabled={savingRule || editingRule?.source === "builtin"}>
							{savingRule ? "保存中..." : "保存规则"}
						</Button>
					</div>
					<div className="text-xs text-muted-foreground flex items-center gap-1">
						<AlertTriangle className="w-3.5 h-3.5" />
						规则会在扫描执行前渲染为临时 TOML，传递给 gitleaks CLI。
					</div>
				</DialogContent>
			</Dialog>
		</div>
	);
}
