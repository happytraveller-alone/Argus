import { useMemo } from "react";
import {
	AlertTriangle,
	SearchCheck,
	ShieldAlert,
} from "lucide-react";
import { Link, Navigate, useSearchParams } from "react-router-dom";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import OpengrepRules from "@/pages/OpengrepRules";
import { Button } from "@/components/ui/button";

type EngineTab = "opengrep" | "gitleaks";

const ENGINE_TABS: EngineTab[] = ["opengrep", "gitleaks"];

export default function ScanConfigEngines() {
	const [searchParams, setSearchParams] = useSearchParams();
	const rawTab = (searchParams.get("tab") || "").toLowerCase();
	if (rawTab === "llm") {
		return <Navigate to="/scan-config/intelligent-engine" replace />;
	}
	const currentTab = useMemo<EngineTab>(() => {
		return ENGINE_TABS.includes(rawTab as EngineTab)
			? (rawTab as EngineTab)
			: "opengrep";
	}, [rawTab]);

	const handleTabChange = (value: string) => {
		const next = ENGINE_TABS.includes(value as EngineTab)
			? (value as EngineTab)
			: "opengrep";
		const nextParams = new URLSearchParams(searchParams);
		nextParams.set("tab", next);
		setSearchParams(nextParams, { replace: true });
	};

	return (
		<div className="space-y-6 p-6 bg-background min-h-screen relative">
			<div className="absolute inset-0 cyber-grid-subtle pointer-events-none" />
			<div className="relative z-10">
				<Tabs
					value={currentTab}
					onValueChange={handleTabChange}
					className="space-y-4"
				>
					<div className="cyber-card p-4">
						<TabsList className="w-full h-auto bg-muted/30 border border-border/60 rounded-xl p-1 grid grid-cols-1 md:grid-cols-2 gap-1">
							<TabsTrigger
								value="opengrep"
								className="justify-start md:justify-center gap-2 font-mono data-[state=active]:bg-primary/20 data-[state=active]:text-primary"
							>
								<SearchCheck className="w-4 h-4" />
								opengrep
							</TabsTrigger>
							<TabsTrigger
								value="gitleaks"
								className="justify-start md:justify-center gap-2 font-mono data-[state=active]:bg-primary/20 data-[state=active]:text-primary"
							>
								<ShieldAlert className="w-4 h-4" />
								gitleaks
							</TabsTrigger>
						</TabsList>
					</div>

					<TabsContent value="opengrep" className="mt-0">
						<div className="cyber-card p-0">
							<OpengrepRules embedded />
						</div>
					</TabsContent>

					<TabsContent value="gitleaks" className="mt-0">
						<div className="cyber-card p-5 space-y-4">
							<div className="section-header mb-1">
								<ShieldAlert className="w-4 h-4 text-primary" />
								<div className="font-mono font-bold uppercase text-sm text-foreground">
									Gitleaks 引擎配置
								</div>
							</div>
							<div className="rounded-lg border border-border/70 bg-muted/20 p-4 space-y-2">
								<div className="inline-flex items-center gap-2 text-amber-300 text-sm">
									<AlertTriangle className="w-4 h-4" />
									当前版本提供扫描联动能力，独立参数面板将在后续版本补充。
								</div>
								<p className="text-sm text-muted-foreground">
									你可以先在静态扫描任务中启用 Gitleaks，
									并通过静态扫描详情查看与 Opengrep 的联合结果。
								</p>
								<Button
									asChild
									className="h-9 px-4 bg-blue-600 hover:bg-blue-500 text-white"
								>
									<Link to="/tasks/static">前往静态扫描</Link>
								</Button>
							</div>
						</div>
					</TabsContent>
				</Tabs>
			</div>
		</div>
	);
}
