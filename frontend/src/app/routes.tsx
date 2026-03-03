import Dashboard from "@/pages/Dashboard";
import Projects from "@/pages/Projects";
import AgentAudit from "@/pages/AgentAudit";
import AdminDashboard from "@/pages/AdminDashboard";
import ProjectDetail from "@/pages/ProjectDetail";
import OpengrepRules from "@/pages/OpengrepRules";
import StaticAnalysis from "@/pages/StaticAnalysis";
import TaskManagementOverview from "@/pages/TaskManagementOverview";
import TaskManagementStatic from "@/pages/TaskManagementStatic";
import TaskManagementIntelligent from "@/pages/TaskManagementIntelligent";
import TaskManagementHybrid from "@/pages/TaskManagementHybrid";
import ScanConfigOverview from "@/pages/ScanConfigOverview";
import ScanConfigEngines from "@/pages/ScanConfigEngines";
import ScanConfigExternalTools from "@/pages/ScanConfigExternalTools";
import type { ReactNode } from "react";
import type { I18nKey } from "@/shared/i18n";

export interface RouteConfig {
    name: string;
    nameKey?: I18nKey;
    path: string;
    element: ReactNode;
    visible?: boolean;
    navVisible?: boolean;
    navGroup?: "main" | "task" | "scanConfig";
    navOrder?: number;
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
    },
    {
        name: "审计规则",
        nameKey: "route.auditRules",
        path: "/opengrep-rules",
        element: <OpengrepRules />,
        visible: true,
        navVisible: false,
        navGroup: "main",
        navOrder: 40,
    },
    {
        name: "任务概览",
        nameKey: "route.taskOverview",
        path: "/tasks/overview",
        element: <TaskManagementOverview />,
        visible: true,
        navVisible: true,
        navGroup: "task",
        navOrder: 10,
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
        name: "扫描配置总览",
        nameKey: "route.scanConfigOverview",
        path: "/scan-config",
        element: <ScanConfigOverview />,
        visible: true,
        navVisible: true,
        navGroup: "scanConfig",
        navOrder: 10,
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
