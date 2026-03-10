import { lazy } from "react";
import type { ReactNode } from "react";
import { Navigate, useLocation } from "react-router-dom";
import type { I18nKey } from "@/shared/i18n";
import { buildOpengrepRulesRedirectPath } from "@/shared/utils/legacyRouteRedirect";

const Dashboard = lazy(() => import("@/pages/Dashboard"));
const Projects = lazy(() => import("@/pages/Projects"));
const AgentAudit = lazy(() => import("@/pages/AgentAudit"));
const AdminDashboard = lazy(() => import("@/pages/AdminDashboard"));
const ProjectDetail = lazy(() => import("@/pages/ProjectDetail"));
const StaticAnalysis = lazy(() => import("@/pages/StaticAnalysis"));
const StaticFindingDetail = lazy(() => import("@/pages/StaticFindingDetail"));
const FindingDetail = lazy(() => import("@/pages/FindingDetail"));
const ScanConfigEngines = lazy(() => import("@/pages/ScanConfigEngines"));
const ScanConfigIntelligentEngine = lazy(
	() => import("@/pages/ScanConfigIntelligentEngine"),
);
const ScanConfigExternalTools = lazy(
	() => import("@/pages/ScanConfigExternalTools"),
);
const TaskManagementStatic = lazy(() => import("@/pages/TaskManagementStatic"));
const TaskManagementIntelligent = lazy(() => import("@/pages/TaskManagementIntelligent"));
const TaskManagementHybrid = lazy(() => import("@/pages/TaskManagementHybrid"));

function LegacyOpengrepRulesRedirect() {
	const location = useLocation();
	return (
		<Navigate
			to={buildOpengrepRulesRedirectPath(location.search)}
			replace
		/>
	);
}

export interface RouteConfig {
    name: string;
    nameKey?: I18nKey;
    path: string;
    element: ReactNode;
    visible?: boolean;
    navVisible?: boolean;
    navGroup?: "main" | "task" | "scanConfig";
    navOrder?: number;
    navParentPath?: string;
}

const routes: RouteConfig[] = [
    {
        name: "首页",
        nameKey: "route.home",
        path: "/",
        element: <AgentAudit />,
        visible: true,
        navVisible: true,
        navGroup: "main",
        navOrder: 10,
    },
	{
		name: "Agent扫描任务",
		nameKey: "route.agentTask",
		path: "/agent-audit/:taskId",
		element: <AgentAudit />,
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
        name: "静态扫描",
        nameKey: "route.taskStatic",
        path: "/tasks/static",
        element: <TaskManagementStatic />,
        visible: true,
        navVisible: true,
        navGroup: "task",
        navOrder: 20,
    },
    {
        name: "智能扫描",
        nameKey: "route.taskIntelligent",
        path: "/tasks/intelligent",
        element: <TaskManagementIntelligent />,
        visible: true,
        navVisible: true,
        navGroup: "task",
        navOrder: 30,
    },
    {
        name: "混合扫描",
        nameKey: "route.taskHybrid",
        path: "/tasks/hybrid",
        element: <TaskManagementHybrid />,
        visible: true,
        navVisible: true,
        navGroup: "task",
        navOrder: 40,
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
        name: "静态分析结果",
        nameKey: "route.staticAnalysis",
        path: "/static-analysis/:taskId",
        element: <StaticAnalysis />,
        visible: false,
        navVisible: false,
    },
    {
        name: "统一缺陷详情",
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
        name: "系统管理",
        nameKey: "route.admin",
        path: "/admin",
        element: <AdminDashboard />,
        visible: true,
        navVisible: false,
        navGroup: "main",
        navOrder: 60,
    },
];

export default routes;
