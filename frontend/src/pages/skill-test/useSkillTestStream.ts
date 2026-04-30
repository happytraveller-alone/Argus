import { useCallback, useRef, useState } from "react";
import { toast } from "sonner";

import type { SkillTestEvent, SkillTestResult, ToolTestPreset } from "./types";

export function useSkillTestStream(skillId: string) {
  const [events, setEvents] = useState<SkillTestEvent[]>([]);
  const [running, setRunning] = useState(false);
  const [result, setResult] = useState<SkillTestResult | null>(null);
  const abortRef = useRef<AbortController | null>(null);
  const idRef = useRef(0);

  const streamRequest = useCallback(
    async (url: string, body: Record<string, unknown>) => {
      if (running || !skillId.trim()) return;

      setEvents([]);
      setResult(null);
      setRunning(true);

      const ctrl = new AbortController();
      abortRef.current = ctrl;

      try {
        const response = await fetch(url, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(body),
          signal: ctrl.signal,
        });

        if (!response.ok) {
          const errText = await response.text();
          let detail = errText;
          try {
            detail = JSON.parse(errText)?.detail ?? errText;
          } catch {
          }
          toast.error(`请求失败: ${detail}`);
          return;
        }

        const reader = response.body?.getReader();
        if (!reader) {
          toast.error("响应流不可用");
          return;
        }

        const decoder = new TextDecoder();
        let buffer = "";

        while (true) {
          const { done, value } = await reader.read();
          if (done) break;
          buffer += decoder.decode(value, { stream: true });

          const parts = buffer.split("\n\n");
          buffer = parts.pop() ?? "";

          for (const part of parts) {
            if (!part.trim()) continue;
            const dataLines = part
              .split("\n")
              .filter((line) => line.startsWith("data:"))
              .map((line) => line.slice(5).trim());
            if (dataLines.length === 0) continue;
            try {
              const parsed = JSON.parse(dataLines.join("\n")) as Omit<SkillTestEvent, "id">;
              const event: SkillTestEvent = { ...parsed, id: idRef.current++ };
              if (event.type === "result" && event.data) {
                setResult(event.data as SkillTestResult);
              }
              setEvents((prev) => [...prev, event]);
            } catch {
            }
          }
        }
      } catch (error: unknown) {
        if ((error as Error)?.name !== "AbortError") {
          toast.error(`连接错误: ${(error as Error)?.message}`);
        }
      } finally {
        abortRef.current = null;
        setRunning(false);
      }
    },
    [running, skillId],
  );

  const runPrompt = useCallback(
    async (prompt: string, maxIterations = 4) => {
      return streamRequest(`/api/v1/skills/${encodeURIComponent(skillId)}/test`, {
        prompt,
        max_iterations: maxIterations,
      });
    },
    [skillId, streamRequest],
  );

  const runStructured = useCallback(
    async (requestPayload: ToolTestPreset) => {
      return streamRequest(`/api/v1/skills/${encodeURIComponent(skillId)}/tool-test`, requestPayload);
    },
    [skillId, streamRequest],
  );

  const stop = useCallback(() => {
    abortRef.current?.abort();
    setRunning(false);
  }, []);

  return { events, running, result, runPrompt, runStructured, stop };
}
