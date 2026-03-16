import catalog from "./cweCatalog.generated.json" with { type: "json" };

export type CweCatalogEntry = {
  id: string;
  numericId: number;
  nameEnOfficial: string;
  nameEnShort: string;
  nameZh: string;
};

type CweCatalogPayload = {
  contentVersion?: string;
  contentDate?: string;
  generatedAt?: string;
  entries?: CweCatalogEntry[];
};

export type CweDisplay = {
  cweId: string | null;
  label: string;
  tooltip: string | null;
  nameZh: string | null;
  nameEn: string | null;
  matched: boolean;
};

const payload = catalog as CweCatalogPayload;
const entries = Array.isArray(payload.entries) ? payload.entries : [];
const entryMap = new Map(
  entries.map((entry) => [String(entry.id || "").toUpperCase(), entry]),
);

function extractFirstCweText(value: unknown): string {
  if (value == null) return "";

  if (Array.isArray(value)) {
    for (const item of value) {
      const normalized = extractFirstCweText(item);
      if (normalized) return normalized;
    }
    return "";
  }

  if (typeof value === "object") {
    const record = value as Record<string, unknown>;
    for (const key of ["cwe", "cwe_id", "id"]) {
      if (key in record) {
        const normalized = extractFirstCweText(record[key]);
        if (normalized) return normalized;
      }
    }
    return "";
  }

  return String(value).trim();
}

function buildCatalogMissLabel(
  normalizedCweId: string,
  fallbackLabel: string,
): string {
  const normalizedFallback = fallbackLabel.trim();
  if (!normalizedFallback) return normalizedCweId;
  if (
    normalizedFallback.toUpperCase() === normalizedCweId.toUpperCase() ||
    normalizedFallback.toUpperCase().startsWith(`${normalizedCweId.toUpperCase()} `)
  ) {
    return normalizedFallback;
  }
  return `${normalizedCweId} ${normalizedFallback}`.trim();
}

export function normalizeCweId(value: unknown): string | null {
  if (value == null) return null;

  if (Array.isArray(value)) {
    for (const item of value) {
      const normalized = normalizeCweId(item);
      if (normalized) return normalized;
    }
    return null;
  }

  if (typeof value === "object") {
    const record = value as Record<string, unknown>;
    for (const key of ["cwe", "cwe_id", "id"]) {
      if (key in record) {
        const normalized = normalizeCweId(record[key]);
        if (normalized) return normalized;
      }
    }
    return null;
  }

  const raw = String(value).trim();
  if (!raw) return null;

  const cweMatch = raw.match(/CWE[\s:_-]*(\d{1,6})/i);
  if (cweMatch?.[1]) return `CWE-${Number.parseInt(cweMatch[1], 10)}`;

  const definitionMatch = raw.match(/definitions\/(\d{1,6})(?:\.html)?/i);
  if (definitionMatch?.[1]) {
    return `CWE-${Number.parseInt(definitionMatch[1], 10)}`;
  }

  if (/^\d{1,6}$/.test(raw)) {
    return `CWE-${Number.parseInt(raw, 10)}`;
  }

  return null;
}

export function resolveCweEntry(cwe: unknown): CweCatalogEntry | null {
  const normalizedCweId = normalizeCweId(cwe);
  if (!normalizedCweId) return null;
  return entryMap.get(normalizedCweId.toUpperCase()) || null;
}

export function resolveCweDisplay(input: {
  cwe?: unknown;
  fallbackLabel?: string | null;
}): CweDisplay {
  const normalizedCweId = normalizeCweId(input.cwe);
  const entry = resolveCweEntry(input.cwe);
  const rawCweLabel = extractFirstCweText(input.cwe);
  const fallbackLabel = String(input.fallbackLabel || "").trim();

  if (entry) {
    return {
      cweId: entry.id,
      label: `${entry.id} ${entry.nameZh}`.trim(),
      tooltip: entry.nameEnShort || entry.nameEnOfficial || null,
      nameZh: entry.nameZh,
      nameEn: entry.nameEnShort || entry.nameEnOfficial || null,
      matched: true,
    };
  }

  if (normalizedCweId) {
    return {
      cweId: normalizedCweId,
      label: buildCatalogMissLabel(normalizedCweId, fallbackLabel),
      tooltip: null,
      nameZh: null,
      nameEn: null,
      matched: false,
    };
  }

  const readableLabel = fallbackLabel || rawCweLabel;
  return {
    cweId: null,
    label: readableLabel || "-",
    tooltip: null,
    nameZh: null,
    nameEn: null,
    matched: false,
  };
}

export function formatCweDisplayLabel(
  cwe: unknown,
  fallbackLabel?: string | null,
): string {
  return resolveCweDisplay({ cwe, fallbackLabel }).label;
}

export function formatCweDisplayTooltip(cwe: unknown): string | null {
  return resolveCweDisplay({ cwe }).tooltip;
}

export function getCweCatalogMetadata() {
  return {
    contentVersion: String(payload.contentVersion || ""),
    contentDate: String(payload.contentDate || ""),
    generatedAt: String(payload.generatedAt || ""),
    entryCount: entries.length,
  };
}
