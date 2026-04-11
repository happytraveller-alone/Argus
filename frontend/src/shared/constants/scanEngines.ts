export const SCAN_ENGINE_TABS = [
  "opengrep",
  "gitleaks",
  "bandit",
  "phpstan",
  "pmd",
] as const;

export type ScanEngineTab = (typeof SCAN_ENGINE_TABS)[number];

export const DEFAULT_SCAN_ENGINE_TAB: ScanEngineTab = "opengrep";

export const SCAN_ENGINE_SELECTOR_OPTIONS = SCAN_ENGINE_TABS.map((value) => ({
  label: value,
  value,
}));

export function isScanEngineTab(value: string): value is ScanEngineTab {
  return SCAN_ENGINE_TABS.includes(value as ScanEngineTab);
}

export function getScanEngineDisplayName(value: ScanEngineTab): string {
  switch (value) {
    case "opengrep":
      return "Opengrep";
    case "gitleaks":
      return "Gitleaks";
    case "bandit":
      return "Bandit";
    case "phpstan":
      return "PHPStan";
    case "pmd":
      return "PMD";
  }
}

export function buildScanEngineConfigRoute(value: ScanEngineTab): string {
  return `/scan-config/engines?tab=${value}`;
}
