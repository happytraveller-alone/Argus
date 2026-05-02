import { useEffect, useRef, useState } from "react";

export interface SseEvent {
  kind: string;
  timestamp: string;
  message?: string;
  data?: Record<string, unknown>;
}

interface UseSseStreamOptions {
  enabled?: boolean;
}

interface UseSseStreamResult {
  events: SseEvent[];
  isConnected: boolean;
  isComplete: boolean;
  error: string | null;
}

const TERMINAL_KINDS = ["completed", "failed", "cancelled"];

function isTerminalKind(kind: string): boolean {
  return TERMINAL_KINDS.some((t) => kind.includes(t));
}

export function useSseStream(
  url: string,
  options: UseSseStreamOptions = {},
): UseSseStreamResult {
  const { enabled = true } = options;

  const [events, setEvents] = useState<SseEvent[]>([]);
  const [isConnected, setIsConnected] = useState(false);
  const [isComplete, setIsComplete] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const abortRef = useRef<AbortController | null>(null);

  useEffect(() => {
    if (!enabled || !url) return;

    const ctrl = new AbortController();
    abortRef.current = ctrl;

    setEvents([]);
    setIsConnected(false);
    setIsComplete(false);
    setError(null);

    void (async () => {
      try {
        const response = await fetch(url, { signal: ctrl.signal });
        if (!response.ok) {
          const errText = await response.text();
          let detail = errText;
          try {
            detail = (JSON.parse(errText) as { detail?: string })?.detail ?? errText;
          } catch {
            // use raw text
          }
          setError(`HTTP ${response.status}: ${detail}`);
          return;
        }

        if (!response.body) {
          setError("No response body");
          return;
        }

        setIsConnected(true);

        const reader = response.body.getReader();
        const decoder = new TextDecoder();
        let buffer = "";

        while (true) {
          const { done, value } = await reader.read();
          if (done) break;

          buffer += decoder.decode(value, { stream: true });
          const chunks = buffer.split("\n\n");
          buffer = chunks.pop() ?? "";

          for (const chunk of chunks) {
            const dataLines = chunk
              .split("\n")
              .filter((line) => line.startsWith("data:"))
              .map((line) => line.slice(5).trim());
            if (dataLines.length === 0) continue;
            try {
              const parsed = JSON.parse(dataLines.join("\n")) as SseEvent;
              setEvents((prev) => [...prev, parsed]);
              if (isTerminalKind(parsed.kind)) {
                setIsComplete(true);
              }
            } catch {
              // skip malformed json
            }
          }
        }

        setIsComplete(true);
      } catch (err: unknown) {
        if ((err as Error)?.name !== "AbortError") {
          setError((err as Error)?.message ?? "Unknown error");
        }
      } finally {
        setIsConnected(false);
      }
    })();

    return () => {
      ctrl.abort();
    };
  }, [url, enabled]);

  return { events, isConnected, isComplete, error };
}
