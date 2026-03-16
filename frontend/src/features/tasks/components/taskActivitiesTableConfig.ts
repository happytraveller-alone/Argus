export const TASK_ACTIVITIES_TABLE_HEADERS = [
	"序号",
	"扫描项目",
	"创建时间",
	"用时",
	"扫描进度",
	"扫描状态",
	"漏洞统计",
	"操作",
] as const;

export const TASK_ACTIVITIES_TABLE_COLSPAN =
	TASK_ACTIVITIES_TABLE_HEADERS.length;
