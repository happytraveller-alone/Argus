import { useMemo } from "react";
import { Navigate, useSearchParams } from "react-router-dom";
import OpengrepRules from "@/pages/OpengrepRules";
import CodeqlRules from "@/pages/CodeqlRules";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
	DEFAULT_SCAN_ENGINE_TAB,
	SCAN_ENGINE_SELECTOR_OPTIONS,
	isScanEngineTab,
	type ScanEngineTab,
} from "@/shared/constants/scanEngines";

const DATA_TABLE_URL_STATE_KEYS = [
	"q",
	"sort",
	"order",
	"page",
	"pageSize",
	"filters",
];

export function buildScanConfigEngineSearchParams(
	currentParams: URLSearchParams,
	value: string,
) {
	const next = isScanEngineTab(value) ? value : DEFAULT_SCAN_ENGINE_TAB;
	const nextParams = new URLSearchParams(currentParams);
	for (const key of DATA_TABLE_URL_STATE_KEYS) {
		nextParams.delete(key);
	}
	nextParams.set("tab", next);
	return nextParams;
}

function JoernEngineNotice({
	currentTab,
	onEngineChange,
}: {
	currentTab: ScanEngineTab;
	onEngineChange: (value: ScanEngineTab) => void;
}) {
	return (
		<div className="space-y-6 font-mono">
			<div className="flex flex-wrap items-center justify-between gap-3">
				<div>
					<h1 className="text-xl font-semibold tracking-[0.12em] text-foreground">
						Joern 图结构扫描
					</h1>
					<p className="mt-2 max-w-3xl text-sm leading-6 text-muted-foreground">
						Joern 首版作为后端托管的一等静态扫描引擎运行：使用后端配置的 Joern 镜像、
						内置查询资产和任务结果 API。此处不提供任务级查询编辑或规则管理界面。
					</p>
				</div>
				<div className="flex flex-wrap gap-2">
					{SCAN_ENGINE_SELECTOR_OPTIONS.map((option) => (
						<Button
							key={option.value}
							type="button"
							size="sm"
							variant={option.value === currentTab ? "default" : "outline"}
							className={
								option.value === currentTab
									? "cyber-btn-primary h-8"
									: "cyber-btn-outline h-8"
							}
							onClick={() => onEngineChange(option.value)}
						>
							{option.label}
						</Button>
					))}
				</div>
			</div>

			<div className="rounded-lg border border-border bg-muted/30 p-5">
				<div className="mb-4 flex flex-wrap gap-2">
					<Badge className="cyber-badge-info">后端镜像配置</Badge>
					<Badge className="cyber-badge-muted">内置 C/C++ 查询</Badge>
					<Badge className="cyber-badge-warning">无规则管理 UI</Badge>
				</div>
				<div className="grid gap-3 text-sm text-muted-foreground md:grid-cols-3">
					<div className="rounded border border-border/70 bg-background/60 p-3">
						<p className="text-xs uppercase tracking-wider text-foreground">
							镜像
						</p>
						<p className="mt-2 break-all">SCANNER_JOERN_IMAGE</p>
					</div>
					<div className="rounded border border-border/70 bg-background/60 p-3">
						<p className="text-xs uppercase tracking-wider text-foreground">
							资源限制
						</p>
						<p className="mt-2">JOERN_* timeout / stdout / stderr / memory</p>
					</div>
					<div className="rounded border border-border/70 bg-background/60 p-3">
						<p className="text-xs uppercase tracking-wider text-foreground">
							查询资产
						</p>
						<p className="mt-2 break-all">
							assets/scan_rule_assets/rules_joern/c/argus-joern-scan.sc
						</p>
					</div>
				</div>
				<p className="mt-4 text-sm leading-6 text-muted-foreground">
					验收目标聚焦 libplist 的 CPG/图结构构建和 CVE-2017-6439 缓冲区溢出检出；
					不在前端泛化多语言规则管理能力。
				</p>
			</div>
		</div>
	);
}

export default function ScanConfigEngines() {
	const [searchParams, setSearchParams] = useSearchParams();
	const rawTab = (searchParams.get("tab") || "").toLowerCase();
	if (rawTab === "llm") {
		return <Navigate to="/scan-config/intelligent-engine" replace />;
	}

	const currentTab = useMemo(() => {
		return isScanEngineTab(rawTab) ? rawTab : DEFAULT_SCAN_ENGINE_TAB;
	}, [rawTab]);

	const handleEngineChange = (value: string) => {
		setSearchParams(buildScanConfigEngineSearchParams(searchParams, value), {
			replace: true,
		});
	};

	return (
		<div className="min-h-screen bg-background p-6">
			{currentTab === "joern" ? (
				<JoernEngineNotice
					currentTab={currentTab}
					onEngineChange={handleEngineChange}
				/>
			) : currentTab === "codeql" ? (
				<CodeqlRules
					embedded
					showEngineSelector
					engineValue={currentTab}
					onEngineChange={handleEngineChange}
				/>
			) : (
				<OpengrepRules
					embedded
					showEngineSelector
					engineValue={currentTab}
					onEngineChange={handleEngineChange}
				/>
			)}
		</div>
	);
}
