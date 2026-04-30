import {
  getEstimatedTaskProgressPercent,
  INTERRUPTED_STATUSES,
} from "./taskProgress";

export type TaskDisplayStatusSummary = {
  normalizedStatus: string;
  statusLabel: string;
  badgeClassName: string;
  progressBarClassName: string;
  progressHint: string;
};

export type FormatTaskDurationOptions = {
  showMsWhenSubSecond?: boolean;
};

function normalizeTaskStatus(status: string | null | undefined): string {
  return String(status || "").trim().toLowerCase();
}

export function getTaskDisplayStatusSummary(
  status: string | null | undefined,
): TaskDisplayStatusSummary {
  const normalized = normalizeTaskStatus(status);

  if (normalized === "completed") {
    return {
      normalizedStatus: normalized,
      statusLabel: "任务完成",
      badgeClassName: "cyber-badge-success",
      progressBarClassName: "bg-emerald-400",
      progressHint: "扫描已结束，全部引擎已完成",
    };
  }

  if (normalized === "running") {
    return {
      normalizedStatus: normalized,
      statusLabel: "任务运行中",
      badgeClassName: "cyber-badge-info",
      progressBarClassName: "bg-sky-200",
      progressHint: "扫描进行中，仍有引擎正在执行",
    };
  }

  if (normalized === "pending") {
    return {
      normalizedStatus: normalized,
      statusLabel: "任务待处理",
      badgeClassName: "cyber-badge-info",
      progressBarClassName: "bg-sky-400",
      progressHint: "扫描排队中，等待引擎启动",
    };
  }

  if (normalized === "failed") {
    return {
      normalizedStatus: normalized,
      statusLabel: "任务失败",
      badgeClassName: "cyber-badge-danger",
      progressBarClassName: "bg-rose-400",
      progressHint: "扫描已结束，至少一个引擎失败",
    };
  }

  if (INTERRUPTED_STATUSES.has(normalized)) {
    return {
      normalizedStatus: normalized,
      statusLabel: "任务中止",
      badgeClassName: "cyber-badge-warning",
      progressBarClassName: "bg-orange-400",
      progressHint: "扫描已结束，任务已中断",
    };
  }

  return {
    normalizedStatus: normalized,
    statusLabel: normalized || "未知状态",
    badgeClassName: "cyber-badge-muted",
    progressBarClassName: "bg-muted-foreground",
    progressHint: "扫描状态未知",
  };
}

export function getTaskDisplayProgressPercent(input: {
  status: string | null | undefined;
  createdAt: string | null | undefined;
  startedAt?: string | null | undefined;
  nowMs?: number;
}): number {
  return getEstimatedTaskProgressPercent(
    {
      status: input.status,
      createdAt: input.createdAt,
      startedAt: input.startedAt,
    },
    input.nowMs,
  );
}

export function formatTaskDuration(
  durationMs: number,
  options: FormatTaskDurationOptions = {},
): string {
  const safe = Number.isFinite(durationMs)
    ? Math.max(0, Math.floor(durationMs))
    : 0;
  if (safe <= 0) {
    return options.showMsWhenSubSecond ? "0 ms" : "00:00:00";
  }
  if (options.showMsWhenSubSecond && safe < 1000) {
    return `${safe} ms`;
  }

  const totalSeconds = Math.floor(safe / 1000);
  const hours = Math.floor(totalSeconds / 3600);
  const minutes = Math.floor((totalSeconds % 3600) / 60);
  const seconds = totalSeconds % 60;
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${pad(hours)}:${pad(minutes)}:${pad(seconds)}`;
}
