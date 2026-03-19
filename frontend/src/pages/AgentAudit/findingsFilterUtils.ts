import type { RealtimeMergedFindingItem } from "./components/RealtimeFindingsPanel";
import type { FindingsViewFilters } from "./types";

const VERIFIED_PROGRESS_TOKEN = "verified";

function normalizeProgress(value?: string | null): string {
  return String(value || "").trim().toLowerCase();
}

export function isVerifiedFinding(item?: RealtimeMergedFindingItem | null): boolean {
  if (!item) return false;
  if (item.is_verified) return true;
  return normalizeProgress(item.verification_progress) === VERIFIED_PROGRESS_TOKEN;
}

export function hasAnyVerifiedFinding(params: {
  persisted: RealtimeMergedFindingItem[];
  realtime: RealtimeMergedFindingItem[];
}): boolean {
  return (
    params.persisted.some((item) => isVerifiedFinding(item)) ||
    params.realtime.some((item) => isVerifiedFinding(item))
  );
}

export interface AutoApplyVerifiedFilterParams {
  hasVerifiedFinding: boolean;
  userOverride: boolean;
  alreadyApplied: boolean;
  currentVerificationFilter: FindingsViewFilters["verification"];
}

export function shouldAutoApplyVerifiedFilter(params: AutoApplyVerifiedFilterParams): boolean {
  if (!params.hasVerifiedFinding) return false;
  if (params.userOverride) return false;
  if (params.alreadyApplied) return false;
  return params.currentVerificationFilter !== "verified";
}
