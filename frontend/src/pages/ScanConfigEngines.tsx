import { useMemo } from "react";
import { Navigate, useSearchParams } from "react-router-dom";
import OpengrepRules from "@/pages/OpengrepRules";
import GitleaksRules from "@/pages/GitleaksRules";
import BanditRules from "@/pages/BanditRules";
import PhpstanRules from "@/pages/PhpstanRules";

type EngineTab = "opengrep" | "gitleaks" | "bandit" | "phpstan";

const ENGINE_TABS: EngineTab[] = ["opengrep", "gitleaks", "bandit", "phpstan"];

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

	const handleEngineChange = (value: string) => {
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
				<div className="cyber-card p-0">
					{currentTab === "opengrep" ? (
						<OpengrepRules
							embedded
							showEngineSelector
							engineValue={currentTab}
							onEngineChange={handleEngineChange}
						/>
					) : currentTab === "gitleaks" ? (
						<GitleaksRules
							showEngineSelector
							engineValue={currentTab}
							onEngineChange={handleEngineChange}
						/>
					) : currentTab === "bandit" ? (
						<BanditRules
							showEngineSelector
							engineValue={currentTab}
							onEngineChange={handleEngineChange}
						/>
					) : (
						<PhpstanRules
							showEngineSelector
							engineValue={currentTab}
							onEngineChange={handleEngineChange}
						/>
					)}
				</div>
			</div>
		</div>
	);
}
