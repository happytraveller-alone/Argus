const TERMINAL_STATUSES = new Set([
  "completed",
  "failed",
  "cancelled",
  "interrupted",
]);

export function getTerminalStatusTransitionPolicy(input: {
  previousStatus?: string | null;
  currentStatus?: string | null;
}): {
  didEnterTerminal: boolean;
  shouldReconcileLogs: boolean;
  shouldBackfill: boolean;
  shouldMarkBoundaryFromStatus: boolean;
} {
  const previousStatus = String(input.previousStatus || "").trim().toLowerCase();
  const currentStatus = String(input.currentStatus || "").trim().toLowerCase();
  const didEnterTerminal =
    (previousStatus === "running" || previousStatus === "pending") &&
    Boolean(currentStatus) &&
    TERMINAL_STATUSES.has(currentStatus);

  return {
    didEnterTerminal,
    shouldReconcileLogs: didEnterTerminal,
    shouldBackfill: didEnterTerminal,
    // Terminal sequence boundaries must come from terminal events, not status polling.
    shouldMarkBoundaryFromStatus: false,
  };
}

