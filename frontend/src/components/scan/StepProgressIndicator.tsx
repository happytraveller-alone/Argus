import type { SseEvent } from "@/hooks/useSseStream";

const STEP_LABELS: Record<string, string> = {
  config_resolve: "配置解析",
  input_read: "输入读取",
  llm_invoke: "LLM调用",
};

function getStepLabel(step: string): string {
  return STEP_LABELS[step] ?? step;
}

function formatTimestamp(ts: string): string {
  try {
    return new Date(ts).toLocaleTimeString("zh-CN", { hour12: false });
  } catch {
    return ts;
  }
}

type StepState = "completed" | "active" | "pending";

interface StepEntry {
  step: string;
  state: StepState;
  startedAt: string;
  completedAt?: string;
}

function buildSteps(events: SseEvent[]): StepEntry[] {
  const order: string[] = [];
  const startedAt: Record<string, string> = {};
  const completedAt: Record<string, string> = {};

  for (const ev of events) {
    const step = typeof ev.data?.step === "string" ? ev.data.step : null;
    if (!step) continue;

    if (ev.kind === "step_started") {
      if (!order.includes(step)) order.push(step);
      startedAt[step] = ev.timestamp;
    } else if (ev.kind === "step_completed") {
      if (!order.includes(step)) order.push(step);
      completedAt[step] = ev.timestamp;
    }
  }

  return order.map((step) => {
    const state: StepState = completedAt[step]
      ? "completed"
      : startedAt[step]
        ? "active"
        : "pending";
    return {
      step,
      state,
      startedAt: startedAt[step] ?? "",
      completedAt: completedAt[step],
    };
  });
}

interface StepProgressIndicatorProps {
  events: SseEvent[];
}

export function StepProgressIndicator({ events }: StepProgressIndicatorProps) {
  const steps = buildSteps(events);

  if (steps.length === 0) return null;

  return (
    <div className="flex flex-col gap-0">
      {steps.map((entry, idx) => (
        <div key={entry.step} className="flex items-start gap-3">
          {/* Timeline connector + icon */}
          <div className="flex flex-col items-center">
            {/* Icon */}
            {entry.state === "completed" ? (
              <div className="flex h-5 w-5 items-center justify-center rounded-full border border-emerald-500/40 bg-emerald-500/10">
                <svg
                  className="h-3 w-3 text-emerald-400"
                  fill="none"
                  stroke="currentColor"
                  viewBox="0 0 24 24"
                  aria-hidden="true"
                >
                  <path
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    strokeWidth={2.5}
                    d="M5 13l4 4L19 7"
                  />
                </svg>
              </div>
            ) : entry.state === "active" ? (
              <div className="flex h-5 w-5 items-center justify-center rounded-full border border-cyan-500/40 bg-cyan-500/10">
                <span className="h-2 w-2 rounded-full bg-cyan-400 animate-pulse" />
              </div>
            ) : (
              <div className="flex h-5 w-5 items-center justify-center rounded-full border border-border/40 bg-muted/20">
                <span className="h-1.5 w-1.5 rounded-full bg-muted-foreground/30" />
              </div>
            )}
            {/* Vertical line (not on last item) */}
            {idx < steps.length - 1 && (
              <div className="mt-0.5 w-px flex-1 bg-border/30" style={{ minHeight: "1rem" }} />
            )}
          </div>

          {/* Step content */}
          <div className="pb-3 pt-0.5 min-w-0">
            <div className="flex items-baseline gap-2">
              <span
                className={`font-mono text-xs font-medium ${
                  entry.state === "completed"
                    ? "text-emerald-300"
                    : entry.state === "active"
                      ? "text-cyan-300"
                      : "text-muted-foreground/50"
                }`}
              >
                {getStepLabel(entry.step)}
              </span>
              {entry.state === "active" && (
                <span className="font-mono text-[10px] text-cyan-400/70">进行中...</span>
              )}
              {entry.state === "completed" && entry.completedAt && (
                <span className="font-mono text-[10px] text-muted-foreground">
                  {formatTimestamp(entry.completedAt)}
                </span>
              )}
              {entry.state !== "completed" && entry.startedAt && (
                <span className="font-mono text-[10px] text-muted-foreground">
                  {formatTimestamp(entry.startedAt)}
                </span>
              )}
            </div>
          </div>
        </div>
      ))}
    </div>
  );
}
