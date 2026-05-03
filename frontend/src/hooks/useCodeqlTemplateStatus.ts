import { useCallback, useEffect, useRef, useState } from "react";
import {
  getCodeqlCppTemplateStatus,
  getCodeqlCppTemplateStreamUrl,
  invalidateCodeqlCppTemplate,
  provisionCodeqlCppTemplate,
  type CubesandboxTemplateRecord,
  type CubesandboxTemplateStatus,
} from "@/shared/api/cubesandboxTemplates";

interface UseCodeqlTemplateStatusOptions {
  enabled?: boolean;
  pollIntervalMs?: number;
}

export interface UseCodeqlTemplateStatusResult {
  status: CubesandboxTemplateStatus;
  templateId: string | null;
  jobId: string | null;
  errorMessage: string | null;
  buildLogTail: string;
  record: CubesandboxTemplateRecord | null;
  isLoading: boolean;
  isMutating: boolean;
  refresh: () => Promise<void>;
  provision: () => Promise<void>;
  invalidate: () => Promise<void>;
}

const ACTIVE_STATUSES: ReadonlyArray<CubesandboxTemplateStatus> = [
  "pending",
  "building",
];

function isActive(status: CubesandboxTemplateStatus): boolean {
  return ACTIVE_STATUSES.includes(status);
}

export function useCodeqlTemplateStatus(
  options: UseCodeqlTemplateStatusOptions = {},
): UseCodeqlTemplateStatusResult {
  const { enabled = true, pollIntervalMs = 5000 } = options;

  const [record, setRecord] = useState<CubesandboxTemplateRecord | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [isMutating, setIsMutating] = useState(false);
  const eventSourceRef = useRef<EventSource | null>(null);

  const refresh = useCallback(async () => {
    if (!enabled) return;
    setIsLoading(true);
    try {
      const next = await getCodeqlCppTemplateStatus();
      setRecord(next);
    } catch (error) {
      console.warn("getCodeqlCppTemplateStatus failed", error);
    } finally {
      setIsLoading(false);
    }
  }, [enabled]);

  const provision = useCallback(async () => {
    if (!enabled) return;
    setIsMutating(true);
    try {
      const next = await provisionCodeqlCppTemplate();
      setRecord(next);
    } finally {
      setIsMutating(false);
    }
  }, [enabled]);

  const invalidate = useCallback(async () => {
    if (!enabled) return;
    setIsMutating(true);
    try {
      await invalidateCodeqlCppTemplate();
      await refresh();
    } finally {
      setIsMutating(false);
    }
  }, [enabled, refresh]);

  // Initial load + polling.
  useEffect(() => {
    if (!enabled) return;
    void refresh();
    const status = record?.status ?? "absent";
    const intervalId = window.setInterval(() => {
      void refresh();
    }, isActive(status) ? Math.min(pollIntervalMs, 3000) : pollIntervalMs);
    return () => window.clearInterval(intervalId);
  }, [enabled, refresh, pollIntervalMs, record?.status]);

  // SSE while building.
  useEffect(() => {
    if (!enabled) return;
    const status = record?.status;
    if (status !== "building" && status !== "pending") {
      eventSourceRef.current?.close();
      eventSourceRef.current = null;
      return;
    }
    if (eventSourceRef.current) return;
    const url = getCodeqlCppTemplateStreamUrl();
    const source = new EventSource(url);
    eventSourceRef.current = source;
    source.addEventListener("snapshot", (event) => {
      try {
        const parsed = JSON.parse((event as MessageEvent).data) as CubesandboxTemplateRecord;
        setRecord(parsed);
      } catch (error) {
        console.warn("snapshot parse failed", error);
      }
    });
    source.addEventListener("event", () => {
      void refresh();
    });
    source.onerror = () => {
      source.close();
      if (eventSourceRef.current === source) {
        eventSourceRef.current = null;
      }
    };
    return () => {
      source.close();
      if (eventSourceRef.current === source) {
        eventSourceRef.current = null;
      }
    };
  }, [enabled, record?.status, refresh]);

  const status = record?.status ?? "absent";
  return {
    status,
    templateId: record?.templateId ?? null,
    jobId: record?.jobId ?? null,
    errorMessage: record?.errorMessage ?? null,
    buildLogTail: record?.buildLogTail ?? "",
    record,
    isLoading,
    isMutating,
    refresh,
    provision,
    invalidate,
  };
}
