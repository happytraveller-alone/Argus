import { Code, ListChecks, Wrench, type LucideIcon } from "lucide-react";
import type { I18nKey } from "@/shared/i18n";

export type SidebarNavGroupId = "task" | "scanConfig" | "devTest";

export interface SidebarNavGroupConfig {
	id: SidebarNavGroupId;
	titleKey: I18nKey;
	fallbackLabel: string;
	icon: LucideIcon;
	defaultEntryPath: string;
}

export const SIDEBAR_NAV_GROUPS: SidebarNavGroupConfig[] = [
	{
		id: "task",
		titleKey: "route.taskManagement",
		fallbackLabel: "任务管理",
		icon: ListChecks,
		defaultEntryPath: "/tasks/static",
	},
	{
		id: "scanConfig",
		titleKey: "route.scanConfig",
		fallbackLabel: "扫描配置",
		icon: Wrench,
		defaultEntryPath: "/scan-config/engines",
	},
	{
		id: "devTest",
		titleKey: "route.devTest",
		fallbackLabel: "开发测试",
		icon: Code,
		defaultEntryPath: "/data-management",
	},
];
