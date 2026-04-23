import { useMemo } from "react";
import { Navigate, useSearchParams } from "react-router-dom";
import OpengrepRules from "@/pages/OpengrepRules";
import {
  DEFAULT_SCAN_ENGINE_TAB,
  isScanEngineTab,
} from "@/shared/constants/scanEngines";

const DATA_TABLE_URL_STATE_KEYS = ["q", "sort", "order", "page", "pageSize", "filters"];

export function buildScanConfigEngineSearchParams(
  currentParams: URLSearchParams,
  value: string,
) {
  const next = value === "opengrep" ? value : DEFAULT_SCAN_ENGINE_TAB;
  const nextParams = new URLSearchParams(currentParams);
  for (const key of DATA_TABLE_URL_STATE_KEYS) {
    nextParams.delete(key);
  }
  nextParams.set("tab", next);
  return nextParams;
}

export default function ScanConfigEngines() {
	const [searchParams, setSearchParams] = useSearchParams();
	const rawTab = (searchParams.get("tab") || "").toLowerCase();
	if (rawTab === "llm") {
		return <Navigate to="/scan-config/intelligent-engine" replace />;
	}

	const currentTab = useMemo(() => {
		return rawTab === "opengrep" && isScanEngineTab(rawTab)
			? rawTab
			: DEFAULT_SCAN_ENGINE_TAB;
	}, [rawTab]);

	const handleEngineChange = (value: string) => {
		setSearchParams(buildScanConfigEngineSearchParams(searchParams, value), { replace: true });
	};

	return (
		<div className="space-y-6 p-6 bg-background min-h-screen relative">
			<div className="absolute inset-0 cyber-grid-subtle pointer-events-none" />
			<div className="relative z-10">
				<div className="cyber-card p-0">
					<OpengrepRules
						embedded
						showEngineSelector
						engineValue={currentTab}
						onEngineChange={handleEngineChange}
					/>
				</div>
			</div>
		</div>
	);
}
