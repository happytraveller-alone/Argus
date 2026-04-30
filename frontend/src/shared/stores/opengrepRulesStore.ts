import type { OpengrepRule } from "@/shared/api/opengrep";

type Listener = (rules: OpengrepRule[]) => void;

const STORAGE_KEY = "opengrep_active_rules";
let cachedRules: OpengrepRule[] = [];
const listeners = new Set<Listener>();

const notify = () => {
  for (const listener of listeners) {
    listener(cachedRules);
  }
};

export const setOpengrepActiveRules = (rules: OpengrepRule[]) => {
  cachedRules = rules;
  if (typeof window !== "undefined") {
    try {
      window.localStorage.setItem(STORAGE_KEY, JSON.stringify(rules));
    } catch {
    }
  }
  notify();
};

export const getOpengrepActiveRules = (): OpengrepRule[] => {
  if (cachedRules.length > 0) return cachedRules;
  if (typeof window === "undefined") return [];
  try {
    const raw = window.localStorage.getItem(STORAGE_KEY);
    if (!raw) return [];
    const parsed = JSON.parse(raw);
    if (Array.isArray(parsed)) {
      cachedRules = parsed as OpengrepRule[];
      return cachedRules;
    }
  } catch {
    return [];
  }
  return [];
};

export const subscribeOpengrepActiveRules = (listener: Listener) => {
  listeners.add(listener);
  return () => listeners.delete(listener);
};
