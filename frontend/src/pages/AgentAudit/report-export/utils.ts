export function getReportExportSeverityColor(severity: string): string {
  const colors: Record<string, string> = {
    critical: "text-rose-600 dark:text-rose-400",
    high: "text-orange-600 dark:text-orange-400",
    medium: "text-amber-600 dark:text-amber-400",
    low: "text-sky-600 dark:text-sky-400",
    info: "text-muted-foreground",
  };
  return colors[severity.toLowerCase()] || colors.info;
}

export function formatReportExportBytes(bytes: number): string {
  if (bytes === 0) return "0 B";
  const k = 1024;
  const sizes = ["B", "KB", "MB"];
  const i = Math.floor(Math.log(bytes) / Math.log(k));
  return `${parseFloat((bytes / Math.pow(k, i)).toFixed(1))} ${sizes[i]}`;
}

export function getReportExportScoreColor(score: number): {
  text: string;
  bg: string;
  glow: string;
} {
  if (score >= 80) {
    return {
      text: "text-emerald-600 dark:text-emerald-400",
      bg: "stroke-emerald-500",
      glow: "",
    };
  }
  if (score >= 60) {
    return {
      text: "text-amber-600 dark:text-amber-400",
      bg: "stroke-amber-500",
      glow: "",
    };
  }
  if (score >= 40) {
    return {
      text: "text-orange-600 dark:text-orange-400",
      bg: "stroke-orange-500",
      glow: "",
    };
  }
  return {
    text: "text-rose-600 dark:text-rose-400",
    bg: "stroke-rose-500",
    glow: "",
  };
}
