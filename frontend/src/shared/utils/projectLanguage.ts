import type { Project } from "@/shared/types";

// Source of truth for the threshold is the backend env var ARGUS_CPP_PROJECT_THRESHOLD.
// Frontend hardcodes the default for UX gating; backend re-checks on submit (AC4).
// TODO(ops): expose via GET /config/scan-gates if threshold drift becomes a real ops surface.
export const CPP_PROJECT_THRESHOLD_DEFAULT = 0.5;

export type CppGateReason = "qualifies" | "pending" | "not_cpp";

export interface CppGateResult {
  qualifies: boolean;
  reason: CppGateReason;
}

export const CPP_GATE_COPY: Record<Exclude<CppGateReason, "qualifies">, string> = {
  pending: "项目语言检测未完成，完成后才可使用",
  not_cpp: "当前功能仅支持 C/C++ 项目",
};

export function isCppProject(
  project: Pick<Project, "programming_languages" | "language_info" | "info_status">,
  threshold = CPP_PROJECT_THRESHOLD_DEFAULT,
): CppGateResult {
  // Fail-closed: any info_status other than "completed" blocks the gate.
  if (project.info_status !== "completed") {
    return { qualifies: false, reason: "pending" };
  }
  const langs = parseLangList(project.programming_languages);
  if (langs.length === 0) {
    return { qualifies: false, reason: "pending" };
  }
  const info = parseLangInfo(project.language_info);
  if (!info || Object.keys(info).length === 0) {
    return { qualifies: false, reason: "pending" };
  }
  const c = numericProportion(info.C);
  const cpp = numericProportion(info["C++"]);
  if (c + cpp >= threshold) {
    return { qualifies: true, reason: "qualifies" };
  }
  return { qualifies: false, reason: "not_cpp" };
}

function parseLangList(raw: string): string[] {
  if (!raw) return [];
  try {
    const v = JSON.parse(raw);
    return Array.isArray(v) ? v.filter((x) => typeof x === "string") : [];
  } catch {
    return [];
  }
}

function parseLangInfo(raw: string): Record<string, { proportion?: number }> | null {
  if (!raw) return null;
  try {
    const v = JSON.parse(raw);
    if (v && typeof v === "object" && v.languages && typeof v.languages === "object") {
      return v.languages as Record<string, { proportion?: number }>;
    }
  } catch {
    /* fall through */
  }
  return null;
}

function numericProportion(entry: { proportion?: number } | undefined): number {
  if (!entry) return 0;
  const p = entry.proportion;
  return typeof p === "number" && Number.isFinite(p) ? p : 0;
}
