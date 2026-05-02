import { lazy } from "react";
import type { ReactNode } from "react";
import { Navigate, useLocation } from "react-router-dom";
import type { I18nKey } from "@/shared/i18n";
import type { SidebarNavGroupId } from "@/app/sidebarNavGroups";
import { buildOpengrepRulesRedirectPath } from "@/shared/utils/legacyRouteRedirect";
import InDevelopmentPlaceholder from "@/shared/components/InDevelopmentPlaceholder";

const Dashboard = lazy(() => import("@/pages/Dashboard"));
const DashboardMockPreview = lazy(() => import("@/pages/DashboardMockPreview"));
const Projects = lazy(() => import("@/pages/Projects"));
const ProjectCodeBrowser = lazy(() => import("@/pages/ProjectCodeBrowser"));
const ProjectDetail = lazy(() => import("@/pages/ProjectDetail"));
const StaticAnalysis = lazy(() => import("@/pages/StaticAnalysis"));
const AiAnalysisResult = lazy(() => import("@/pages/static-analysis/AiAnalysisResult"));
const StaticFindingDetail = lazy(() => import("@/pages/StaticFindingDetail"));
const FindingDetail = lazy(() => import("@/pages/FindingDetail"));
const ScanConfigEngines = lazy(() => import("@/pages/ScanConfigEngines"));
const ScanConfigIntelligentEngine = lazy(
	() => import("@/pages/ScanConfigIntelligentEngine"),
);
const ScanConfigExternalTools = lazy(
	() => import("@/pages/ScanConfigExternalTools"),
);
const ScanConfigExternalToolDetail = lazy(
	() => import("@/pages/ScanConfigExternalToolDetail"),
);
const TaskManagementStatic = lazy(() => import("@/pages/TaskManagementStatic"));
const TaskManagementIntelligent = lazy(
	() => import("@/pages/TaskManagementIntelligent"),
);
const DataManagementPage = lazy(() => import("@/pages/DataManagement"));
const AgentAuditDetail = lazy(() => import("@/pages/AgentAuditDetail"));

function LegacyOpengrepRulesRedirect() {
	const location = useLocation();
	return (
		<Navigate to={buildOpengrepRulesRedirectPath(location.search)} replace />
	);
}

export interface RouteConfig {
	name: string;
	nameKey?: I18nKey;
	path: string;
	element: ReactNode;
	visible?: boolean;
	navVisible?: boolean;
	navGroup?: "main" | SidebarNavGroupId;
	navOrder?: number;
	navParentPath?: string;
}

const routes: RouteConfig[] = [
	{
		name: "首页",
		nameKey: "route.home",
		path: "/",
		element: <Navigate to="/dashboard" replace />,
		visible: false,
		navVisible: false,
		navGroup: "main",
		navOrder: 10,
	},
	{
		name: "Agent扫描任务",
		nameKey: "route.agentTask",
		path: "/agent-audit/:taskId",
		element: <AgentAuditDetail />,
		visible: false,
		navVisible: false,
	},
	{
		name: "仪表盘",
		nameKey: "route.dashboard",
		path: "/dashboard",
		element: <Dashboard />,
		visible: true,
		navVisible: true,
		navGroup: "main",
		navOrder: 20,
	},
	{
		name: "仪表盘预览",
		path: "/dashboard/mock-preview",
		element: <DashboardMockPreview />,
		visible: false,
		navVisible: false,
	},
	{
		name: "项目管理",
		nameKey: "route.projects",
		path: "/projects",
		element: <Projects />,
		visible: true,
		navVisible: true,
		navGroup: "main",
		navOrder: 30,
	},
	{
		name: "项目详情",
		nameKey: "route.projectDetail",
		path: "/projects/:id",
		element: <ProjectDetail />,
		visible: false,
		navVisible: false,
		navParentPath: "/projects",
	},
	{
		name: "项目代码浏览",
		path: "/projects/:id/code-browser",
		element: <ProjectCodeBrowser />,
		visible: false,
		navVisible: false,
		navParentPath: "/projects",
	},
	{
		name: "扫描规则重定向",
		nameKey: "route.scanRules",
		path: "/opengrep-rules",
		element: <LegacyOpengrepRulesRedirect />,
		visible: false,
		navVisible: false,
	},
	{
		name: "任务管理重定向",
		path: "/tasks/overview",
		element: <Navigate to="/tasks/static" replace />,
		visible: false,
		navVisible: false,
	},
	{
		name: "静态审计",
		nameKey: "route.taskStatic",
		path: "/tasks/static",
		element: <TaskManagementStatic />,
		visible: true,
		navVisible: true,
		navGroup: "task",
		navOrder: 20,
	},
	{
		name: "智能审计",
		nameKey: "route.taskIntelligent",
		path: "/tasks/intelligent",
		element: <TaskManagementIntelligent />,
		visible: true,
		navVisible: true,
		navGroup: "task",
		navOrder: 30,
	},
	{
		name: "扫描配置重定向",
		path: "/scan-config",
		element: <Navigate to="/scan-config/engines" replace />,
		visible: false,
		navVisible: false,
	},
	{
		name: "扫描引擎",
		nameKey: "route.scanEngines",
		path: "/scan-config/engines",
		element: <ScanConfigEngines />,
		visible: true,
		navVisible: true,
		navGroup: "scanConfig",
		navOrder: 20,
	},
	{
		name: "智能引擎",
		nameKey: "route.smartEngine",
		path: "/scan-config/intelligent-engine",
		element: <ScanConfigIntelligentEngine />,
		visible: true,
		navVisible: true,
		navGroup: "scanConfig",
		navOrder: 25,
	},
	{
		name: "外部工具",
		nameKey: "route.scanExternalTools",
		path: "/scan-config/external-tools",
		element: <ScanConfigExternalTools />,
		visible: true,
		navVisible: true,
		navGroup: "scanConfig",
		navOrder: 30,
	},
	{
		name: "外部工具详情",
		path: "/scan-config/external-tools/:toolType/:toolId",
		element: <ScanConfigExternalToolDetail />,
		visible: false,
		navVisible: false,
		navParentPath: "/scan-config/external-tools",
	},
	{
		name: "静态分析结果",
		nameKey: "route.staticAnalysis",
		path: "/static-analysis/:taskId",
		element: <StaticAnalysis />,
		visible: false,
		navVisible: false,
	},
	{
		name: "AI研判分析结果",
		path: "/static-analysis/:taskId/ai-result",
		element: <AiAnalysisResult />,
		visible: false,
		navVisible: false,
		navParentPath: "/tasks/static",
	},
	{
		name: "统一漏洞详情",
		path: "/finding-detail/:source/:taskId/:findingId",
		element: <FindingDetail />,
		visible: false,
		navVisible: false,
	},
	{
		name: "静态漏洞详情",
		path: "/static-analysis/:taskId/findings/:findingId",
		element: <StaticFindingDetail />,
		visible: false,
		navVisible: false,
	},
	{
		name: "系统管理重定向",
		nameKey: "route.admin",
		path: "/admin",
		element: <Navigate to="/scan-config/intelligent-engine" replace />,
		visible: false,
		navVisible: false,
	},
	{
		name: "数据管理",
		nameKey: "route.dataManagement",
		path: "/data-management",
		element: <DataManagementPage />,
		visible: true,
		navVisible: true,
		navGroup: "devTest",
		navOrder: 35,
	},
];

export default routes;
