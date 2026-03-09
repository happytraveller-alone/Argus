export function isAgentAuditTerminalStatus(status: string | undefined): boolean {
	const normalized = String(status || "").trim().toLowerCase();
	return (
		normalized === "completed" ||
		normalized === "failed" ||
		normalized === "cancelled" ||
		normalized === "interrupted"
	);
}

export function toAgentAuditStatusLabel(status: string | undefined): string {
	const normalized = String(status || "").trim().toLowerCase();
	if (normalized === "interrupted") return "中止";
	if (normalized === "cancelled" || normalized === "canceled") return "已取消";
	if (normalized === "completed") return "已完成";
	if (normalized === "failed") return "失败";
	if (normalized === "running") return "运行中";
	if (normalized === "pending") return "待处理";
	if (normalized === "waiting") return "等待中";
	if (normalized === "created") return "已创建";
	return String(status || "");
}

export function buildAgentAuditStreamDisconnectTitle(
	source: "transport" | "stream_end",
	errorMessage: string,
): string {
	const prefix =
		source === "transport" ? "服务异常或连接失败" : "事件流连接中断";
	return `${prefix}：${errorMessage}；恢复后进行中的任务会自动标记为中止`;
}
