import catalog from "./cweCatalog.generated.json";

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
  reviewedAt?: string;
  source?: string;
  translationSource?: string;
  entryCount?: number;
  entries?: CweCatalogEntry[];
};

export type CweCatalogHydrationPayload = {
  data?: CweCatalogEntry[];
  entries?: CweCatalogEntry[];
  total?: number;
  limit?: number;
  offset?: number;
  sourceVersion?: string;
  sourceDate?: string;
  sourceSha256?: string;
  translationSource?: string;
  translationReviewedAt?: string;
  contentVersion?: string;
  contentDate?: string;
  generatedAt?: string;
  reviewedAt?: string;
  entryCount?: number;
};

type CweCatalogHydrationListener = () => void;

export type CweCatalogMetadata = {
  contentVersion: string;
  contentDate: string;
  generatedAt: string;
  reviewedAt: string;
  entryCount: number;
  source: "static" | "backend";
  sourceSha256?: string;
  translationSource?: string;
  translationReviewedAt?: string;
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
const entryMap = buildEntryMap(entries);
const staticMetadata: CweCatalogMetadata = {
  contentVersion: String(payload.contentVersion || ""),
  contentDate: String(payload.contentDate || ""),
  generatedAt: String(payload.generatedAt || ""),
  reviewedAt: String(payload.reviewedAt || ""),
  entryCount: Number(payload.entryCount || entries.length || 0),
  source: "static",
  translationSource:
    typeof payload.translationSource === "string"
      ? payload.translationSource
      : undefined,
  translationReviewedAt:
    typeof payload.reviewedAt === "string" ? payload.reviewedAt : undefined,
};

let runtimeEntryMap: Map<string, CweCatalogEntry> | null = null;
let runtimeMetadata: CweCatalogMetadata | null = null;
const hydrationListeners = new Set<CweCatalogHydrationListener>();

function buildEntryMap(items: CweCatalogEntry[]): Map<string, CweCatalogEntry> {
  return new Map(items.map((entry) => [entry.id.toUpperCase(), entry]));
}

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
    normalizedFallback
      .toUpperCase()
      .startsWith(`${normalizedCweId.toUpperCase()} `)
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
  return (
    runtimeEntryMap?.get(normalizedCweId.toUpperCase()) ||
    entryMap.get(normalizedCweId.toUpperCase()) ||
    null
  );
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

export function getCweCatalogMetadata(): CweCatalogMetadata {
  return runtimeMetadata || staticMetadata;
}

export function hydrateCweCatalog(payload: unknown): boolean {
  const validated = validateHydrationPayload(payload);
  if (!validated) return false;
  runtimeEntryMap = buildEntryMap(validated.entries);
  runtimeMetadata = validated.metadata;
  notifyHydrationListeners();
  return true;
}

export function subscribeCweCatalogHydration(
  listener: CweCatalogHydrationListener,
): () => void {
  hydrationListeners.add(listener);
  return () => hydrationListeners.delete(listener);
}

export function resetCweCatalogForTests(): void {
  runtimeEntryMap = null;
  runtimeMetadata = null;
  notifyHydrationListeners();
}

function notifyHydrationListeners(): void {
  for (const listener of hydrationListeners) {
    listener();
  }
}

function validateHydrationPayload(payloadValue: unknown):
  | {
      entries: CweCatalogEntry[];
      metadata: CweCatalogMetadata;
    }
  | null {
  if (!payloadValue || typeof payloadValue !== "object") return null;
  const payload = payloadValue as CweCatalogHydrationPayload;
  const candidateEntries = Array.isArray(payload.data)
    ? payload.data
    : Array.isArray(payload.entries)
      ? payload.entries
      : null;
  if (!candidateEntries || candidateEntries.length === 0) return null;
  const total = Number(payload.total ?? payload.entryCount ?? candidateEntries.length);
  if (!Number.isInteger(total) || total !== candidateEntries.length) return null;

  const seen = new Set<string>();
  const normalizedEntries: CweCatalogEntry[] = [];
  for (const candidate of candidateEntries) {
    const entry = normalizeHydrationEntry(candidate);
    if (!entry) return null;
    const key = entry.id.toUpperCase();
    if (seen.has(key)) return null;
    seen.add(key);
    normalizedEntries.push(entry);
  }

  return {
    entries: normalizedEntries,
    metadata: {
      contentVersion: String(payload.sourceVersion || payload.contentVersion || ""),
      contentDate: String(payload.sourceDate || payload.contentDate || ""),
      generatedAt: String(payload.generatedAt || ""),
      reviewedAt: String(payload.translationReviewedAt || payload.reviewedAt || ""),
      entryCount: total,
      source: "backend",
      sourceSha256:
        typeof payload.sourceSha256 === "string" ? payload.sourceSha256 : undefined,
      translationSource:
        typeof payload.translationSource === "string"
          ? payload.translationSource
          : undefined,
      translationReviewedAt:
        typeof payload.translationReviewedAt === "string"
          ? payload.translationReviewedAt
          : undefined,
    },
  };
}

function normalizeHydrationEntry(value: unknown): CweCatalogEntry | null {
  if (!value || typeof value !== "object") return null;
  const raw = value as Partial<CweCatalogEntry>;
  const id = normalizeCweId(raw.id);
  const numericId = Number(raw.numericId);
  if (!id || !Number.isInteger(numericId) || numericId < 1) return null;
  if (Number.parseInt(id.replace("CWE-", ""), 10) !== numericId) return null;

  const nameEnOfficial = String(raw.nameEnOfficial || "").trim();
  const nameEnShort = String(raw.nameEnShort || nameEnOfficial).trim();
  const nameZh = String(raw.nameZh || "").trim();
  if (!nameEnOfficial || !nameEnShort || !nameZh) return null;
  if (!/[\u4e00-\u9fff]/.test(nameZh)) return null;

  return {
    id,
    numericId,
    nameEnOfficial,
    nameEnShort,
    nameZh,
  };
}
