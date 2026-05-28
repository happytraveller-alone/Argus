export const SCAN_ENGINE_TABS = [
  "opengrep",
  "codeql",
  "joern",
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
  {
    label: "Joern",
    value: "joern" as const,
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
    case "joern":
      return "Joern";
  }
}

export function buildScanEngineConfigRoute(value: ScanEngineTab): string {
  return `/scan-config/engines?tab=${value}`;
}

export interface ScanEngineTabMeta {
  value: ScanEngineTab;
  label: string;
  requiresCppProject: boolean;
}

export const SCAN_ENGINE_TAB_META: Record<ScanEngineTab, ScanEngineTabMeta> = {
  opengrep: { value: "opengrep", label: "Opengrep", requiresCppProject: false },
  codeql: { value: "codeql", label: "CodeQL", requiresCppProject: true },
  joern: { value: "joern", label: "Joern", requiresCppProject: true },
};
