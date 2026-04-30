export const SCAN_ENGINE_TABS = [
  "opengrep",
  "codeql",
  "gitleaks",
  "bandit",
  "phpstan",
  "pmd",
] as const;

export type ScanEngineTab = (typeof SCAN_ENGINE_TABS)[number];

export const DEFAULT_SCAN_ENGINE_TAB: ScanEngineTab = "opengrep";

export const SCAN_ENGINE_SELECTOR_OPTIONS = [
  {
    label: "opengrep",
    value: "opengrep" as const,
  },
  {
    label: "CodeQL",
    value: "codeql" as const,
  },
];

export function isScanEngineTab(value: string): value is ScanEngineTab {
  return SCAN_ENGINE_TABS.includes(value as ScanEngineTab);
}

export function getScanEngineDisplayName(value: ScanEngineTab): string {
  switch (value) {
    case "opengrep":
      return "Opengrep";
    case "codeql":
      return "CodeQL";
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
