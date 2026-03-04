/**
 * Sidebar Component
 * Premium Terminal Aesthetic with Enhanced Visual Design
 */

import { useCallback, useRef, useState } from "react";
import { Link, useLocation } from "react-router-dom";
import { Button } from "@/components/ui/button";
import LanguageToggle from "@/components/layout/LanguageToggle";
// import { ThemeToggle } from "@/components/ui/theme-toggle";
import {
    Menu,
    X,
    LayoutDashboard,
    FolderGit2,
    // Zap,
    // ListTodo,
    // Trash2,
    ChevronLeft,
    ChevronRight,
    // UserCircle,
    Shield,
    Code,
    // MessageSquare,
    Bot,
    ListChecks,
    Wrench,
    Zap,
} from "lucide-react";
import routes from "@/app/routes";
import { useI18n } from "@/shared/i18n";
import { useLogoVariant } from "@/shared/branding/useLogoVariant";

// Icon mapping for routes with consistent sizing
const routeIcons: Record<string, React.ReactNode> = {
    "/": <Bot className="w-[18px] h-[18px]" />,
    "/dashboard": <LayoutDashboard className="w-[18px] h-[18px]" />,
    "/projects": <FolderGit2 className="w-[18px] h-[18px]" />,
    // "/instant-analysis": <Zap className="w-[18px] h-[18px]" />,
    // "/audit-tasks": <ListTodo className="w-[18px] h-[18px]" />,
    "/audit-rules": <Shield className="w-[18px] h-[18px]" />,
    "/opengrep-rules": <Code className="w-[18px] h-[18px]" />,
    "/tasks/overview": <ListChecks className="w-[18px] h-[18px]" />,
    "/tasks/static": <Shield className="w-[18px] h-[18px]" />,
    "/tasks/intelligent": <Bot className="w-[18px] h-[18px]" />,
    "/tasks/hybrid": <ListChecks className="w-[18px] h-[18px]" />,
    "/scan-config": <Wrench className="w-[18px] h-[18px]" />,
    "/scan-config/engines": <Zap className="w-[18px] h-[18px]" />,
    "/scan-config/external-tools": <Wrench className="w-[18px] h-[18px]" />,
    // "/prompts": <MessageSquare className="w-[18px] h-[18px]" />,
    // "/recycle-bin": <Trash2 className="w-[18px] h-[18px]" />,
};

interface SidebarProps {
    collapsed: boolean;
    setCollapsed: (collapsed: boolean) => void;
}

export default function Sidebar({ collapsed, setCollapsed }: SidebarProps) {
    const location = useLocation();
    const [mobileOpen, setMobileOpen] = useState(false);
    const [expandedGroup, setExpandedGroup] = useState<"task" | "scanConfig" | null>(null);
    const { t, isEnglish } = useI18n();
    const { logoSrc } = useLogoVariant();
    const hasPrefetchedTaskGroupRef = useRef(false);
    const hasPrefetchedDashboardRef = useRef(false);
    const hasPrefetchedProjectsRef = useRef(false);

    const sidebarRoutes = routes.filter(
        (route) => (route.navVisible ?? route.visible) !== false,
    );
    const mainRoutes = sidebarRoutes
        .filter((route) => (route.navGroup ?? "main") === "main")
        .sort((a, b) => (a.navOrder ?? 999) - (b.navOrder ?? 999));
    const taskRoutes = sidebarRoutes
        .filter((route) => route.navGroup === "task")
        .sort((a, b) => (a.navOrder ?? 999) - (b.navOrder ?? 999));
    const scanConfigRoutes = sidebarRoutes
        .filter((route) => route.navGroup === "scanConfig")
        .sort((a, b) => (a.navOrder ?? 999) - (b.navOrder ?? 999));
    const taskOverviewRoute =
        taskRoutes.find((route) => route.path === "/tasks/overview") ||
        taskRoutes[0];
    const taskChildRoutes = taskRoutes.filter(
        (route) => route.path !== taskOverviewRoute?.path,
    );
    const scanConfigOverviewRoute =
        scanConfigRoutes.find((route) => route.path === "/scan-config") ||
        scanConfigRoutes[0];
    const scanConfigChildRoutes = scanConfigRoutes.filter(
        (route) => route.path !== scanConfigOverviewRoute?.path,
    );
    const isTaskGroupActive = taskRoutes.some(
        (route) => location.pathname === route.path,
    );
    const isScanConfigGroupActive = scanConfigRoutes.some(
        (route) => location.pathname === route.path,
    );
    const isTaskGroupExpanded =
        !collapsed && (isTaskGroupActive || expandedGroup === "task");
    const isScanConfigGroupExpanded =
        !collapsed &&
        (isScanConfigGroupActive || expandedGroup === "scanConfig");

    const toggleGroupExpanded = (group: "task" | "scanConfig") => {
        setExpandedGroup((prev) => (prev === group ? null : group));
    };

    const prefetchTaskGroupAssets = useCallback(() => {
        if (hasPrefetchedTaskGroupRef.current) return;
        hasPrefetchedTaskGroupRef.current = true;
        void import("@/features/tasks/services/taskActivitiesStore").then(
            ({ prefetchTaskActivitiesSnapshot }) => {
                void prefetchTaskActivitiesSnapshot();
            },
        );
        void import("@/pages/TaskManagementOverview");
        void import("@/pages/TaskManagementStatic");
        void import("@/pages/TaskManagementIntelligent");
        void import("@/pages/TaskManagementHybrid");
    }, []);

    const prefetchDashboardAssets = useCallback(() => {
        if (hasPrefetchedDashboardRef.current) return;
        hasPrefetchedDashboardRef.current = true;
        void import("@/features/dashboard/services/dashboardSnapshotStore").then(
            ({ prefetchDashboardSnapshot }) => {
                void prefetchDashboardSnapshot(10);
            },
        );
        void import("@/pages/Dashboard");
    }, []);

    const prefetchProjectsAssets = useCallback(() => {
        if (hasPrefetchedProjectsRef.current) return;
        hasPrefetchedProjectsRef.current = true;
        void import("@/shared/config/database").then(({ api }) => {
            void api.getProjects();
        });
        void import("@/pages/Projects");
    }, []);

    const renderRouteLink = (
        route: (typeof routes)[number],
        options?: { compact?: boolean },
    ) => {
        const isActive = location.pathname === route.path;
        const routeLabel = route.nameKey
            ? t(route.nameKey, route.name)
            : route.name;
        const compact = options?.compact ?? false;
        return (
            <Link
                key={route.path}
                to={route.path}
                className={`
                    flex items-center gap-3 transition-all duration-300 group relative rounded-lg
                    ${compact ? "px-2 py-2" : "px-3 py-2"}
                    ${
                        isActive
                            ? "bg-primary/15 border border-primary/40 shadow-[0_0_15px_rgba(255,107,44,0.1)]"
                            : "border border-transparent hover:bg-card/60 hover:border-border/50"
                    }
                `}
                style={{
                    color: isActive
                        ? "hsl(var(--primary))"
                        : "var(--cyber-text-muted)",
                }}
                onClick={() => setMobileOpen(false)}
                title={collapsed ? routeLabel : undefined}
                onMouseEnter={(e) => {
                    if (!isActive) {
                        e.currentTarget.style.color = "var(--cyber-text)";
                    }
                    if (route.path === "/dashboard") {
                        prefetchDashboardAssets();
                    } else if (route.path === "/projects") {
                        prefetchProjectsAssets();
                    }
                }}
                onMouseLeave={(e) => {
                    if (!isActive) {
                        e.currentTarget.style.color = "var(--cyber-text-muted)";
                    }
                }}
                onFocus={() => {
                    if (route.path === "/dashboard") {
                        prefetchDashboardAssets();
                    } else if (route.path === "/projects") {
                        prefetchProjectsAssets();
                    }
                }}
            >
                {isActive && (
                    <div
                        className={`absolute top-1/2 -translate-y-1/2 w-1 h-6 bg-primary rounded-r shadow-[0_0_8px_rgba(255,107,44,0.5)] ${compact ? "left-0" : "left-0"}`}
                    />
                )}

                <span
                    className={`
                        flex-shrink-0 transition-all duration-300 p-1.5 rounded-md
                        ${isActive ? "bg-primary/20" : "group-hover:bg-muted/50"}
                    `}
                >
                    {routeIcons[route.path] || (
                        <LayoutDashboard className="w-[18px] h-[18px]" />
                    )}
                </span>

                {!collapsed && (
                    <span
                        className={`tracking-wide transition-all duration-300 break-words leading-snug ${isEnglish ? "text-sm" : "text-base"} ${isActive ? "font-semibold" : "font-medium"} ${compact ? "font-mono text-sm" : "font-mono"}`}
                    >
                        {routeLabel}
                    </span>
                )}

                {!isActive && !collapsed && (
                    <span className="absolute right-3 opacity-0 group-hover:opacity-100 transition-all duration-300 group-hover:translate-x-1">
                        <ChevronRight className="w-4 h-4 text-primary" />
                    </span>
                )}
            </Link>
        );
    };

    return (
        <>
            {/* Mobile Menu Button */}
            <Button
                variant="ghost"
                size="sm"
                className="fixed top-4 left-4 z-50 md:hidden"
                style={{
                    background: "var(--cyber-bg)",
                    border: "1px solid var(--cyber-border)",
                    color: "var(--cyber-text-muted)",
                }}
                onClick={() => setMobileOpen(!mobileOpen)}
            >
                {mobileOpen ? (
                    <X className="w-5 h-5" />
                ) : (
                    <Menu className="w-5 h-5" />
                )}
            </Button>

            {/* Overlay for mobile */}
            {mobileOpen && (
                <button
                    type="button"
                    aria-label="Close sidebar overlay"
                    className="fixed inset-0 bg-black/70 backdrop-blur-sm z-40 md:hidden"
                    onClick={() => setMobileOpen(false)}
                />
            )}

            {/* Sidebar */}
            <aside
                className={`
                    fixed top-0 left-0 h-screen z-40 transition-all duration-300 ease-in-out
                    ${collapsed ? "w-20" : "w-64"}
                    ${mobileOpen ? "translate-x-0" : "-translate-x-full md:translate-x-0"}
                `}
                style={{
                    background: "var(--cyber-bg)",
                    borderRight: "1px solid var(--cyber-border)",
                }}
            >
                <div className="flex flex-col h-full relative">
                    {/* Subtle gradient background */}
                    <div className="absolute inset-0 bg-gradient-to-b from-primary/5 via-transparent to-transparent pointer-events-none" />

                    {/* Subtle grid background */}
                    <div
                        className="absolute inset-0 opacity-20 pointer-events-none"
                        style={{
                            backgroundImage: `
                                linear-gradient(var(--cyber-border-accent) 1px, transparent 1px),
                                linear-gradient(90deg, var(--cyber-border-accent) 1px, transparent 1px)
                            `,
                            backgroundSize: "32px 32px",
                        }}
                    />

                    {/* Right edge glow */}
                    <div className="absolute top-0 right-0 bottom-0 w-px bg-gradient-to-b from-primary/30 via-primary/10 to-primary/30 pointer-events-none" />

                    {/* Logo Section */}
                    <div
                        className={`flex-shrink-0 relative flex items-center h-16 ${collapsed ? "px-3 justify-center" : "px-5 pr-6"}`}
                        style={{
                            background: "var(--cyber-bg-elevated)",
                            borderBottom: "1px solid var(--cyber-border)",
                        }}
                    >
                        {/* Bottom accent line */}
                        <div className="absolute bottom-0 left-0 right-0 h-px bg-gradient-to-r from-primary/40 via-primary/20 to-transparent" />

                        <Link
                            to="/"
                            className={`flex items-center gap-3 group transition-all duration-300 ${collapsed ? "justify-center" : "flex-1 min-w-0"}`}
                            onClick={() => setMobileOpen(false)}
                        >
                            {/* Logo Icon */}
                            <div className="relative flex-shrink-0">
                                <div
                                    className="w-10 h-10 rounded-xl flex items-center justify-center overflow-hidden transition-all duration-300 group-hover:shadow-[0_0_20px_rgba(255,107,44,0.3)]"
                                    style={{
                                        background:
                                            "linear-gradient(135deg, hsl(var(--primary) / 0.15), hsl(var(--primary) / 0.05))",
                                        border: "1px solid hsl(var(--primary) / 0.4)",
                                    }}
                                >
                                    <img
                                        src={logoSrc}
                                        alt="VulHunter"
                                        className="w-6 h-6 object-contain transition-transform duration-300 group-hover:scale-110"
                                    />
                                </div>
                                {/* Glow effect */}
                                <div className="absolute inset-0 bg-primary/30 rounded-xl blur-xl opacity-0 group-hover:opacity-100 transition-opacity duration-500" />
                            </div>

                            {/* Logo Text */}
                            <div
                                className={`transition-all duration-300 ${collapsed ? "w-0 opacity-0 overflow-hidden" : "flex-1 min-w-0 opacity-100"}`}
                            >
                                <div
                                    className="text-xl font-bold tracking-wider font-mono leading-tight"
                                    style={{
                                        textShadow:
                                            "0 0 25px rgba(255,107,44,0.4)",
                                    }}
                                >
                                    <span className="text-primary">
                                        Vul
                                    </span>
                                    <span style={{ color: "var(--cyber-text)" }}>
                                        Hunter
                                    </span>
                                </div>
                            </div>
                        </Link>

                        {/* Collapse button */}
                        <button
                            type="button"
                            className="hidden md:flex absolute -right-3 top-1/2 -translate-y-1/2 w-6 h-6 rounded-md items-center justify-center hover:bg-primary hover:border-primary hover:text-white transition-all duration-300 shadow-sm"
                            style={{
                                background: "var(--cyber-bg)",
                                border: "1px solid var(--cyber-border)",
                                color: "var(--cyber-text-muted)",
                                zIndex: 100,
                            }}
                            onClick={() => setCollapsed(!collapsed)}
                        >
                            {collapsed ? (
                                <ChevronRight className="w-3.5 h-3.5" />
                            ) : (
                                <ChevronLeft className="w-3.5 h-3.5" />
                            )}
                        </button>
                    </div>

                    {/* Navigation */}
                    <nav className="flex-1 min-h-0 py-3 px-3 relative">
                        <div className="space-y-1">
                            {mainRoutes.map((route) => renderRouteLink(route))}

                            {taskRoutes.length > 0 && (
                                <div className="pt-1">
                                    <Link
                                        to={taskOverviewRoute?.path || "/tasks/overview"}
                                        className={`flex items-center gap-3 px-3 py-2 rounded-lg border transition-all duration-300 ${isTaskGroupActive ? "bg-primary/10 border-primary/30 text-primary" : "bg-muted/20 border-border/40 text-muted-foreground"}`}
                                        onClick={() => {
                                            prefetchTaskGroupAssets();
                                            toggleGroupExpanded("task");
                                            setMobileOpen(false);
                                        }}
                                        title={collapsed ? t("route.taskManagement", "任务管理") : undefined}
                                        onMouseEnter={() => {
                                            prefetchTaskGroupAssets();
                                        }}
                                        onFocus={() => {
                                            prefetchTaskGroupAssets();
                                        }}
                                    >
                                        <span className={`p-1.5 rounded-md ${isTaskGroupActive ? "bg-primary/20" : "bg-muted/50"}`}>
                                            <ListChecks className="w-[18px] h-[18px]" />
                                        </span>
                                        {!collapsed && (
                                            <span className={`font-mono tracking-wide ${isEnglish ? "text-sm" : "text-base"} ${isTaskGroupActive ? "font-semibold" : "font-medium"}`}>
                                                {t("route.taskManagement", "任务管理")}
                                            </span>
                                        )}
                                    </Link>

                                    {isTaskGroupExpanded && taskChildRoutes.length > 0 && (
                                        <div className="mt-1 pl-4 space-y-1">
                                            {taskChildRoutes.map((route) =>
                                                renderRouteLink(route, {
                                                    compact: true,
                                                }),
                                            )}
                                        </div>
                                    )}
                                </div>
                            )}

                            {scanConfigRoutes.length > 0 && (
                                <div className="pt-1">
                                    <Link
                                        to={scanConfigOverviewRoute?.path || "/scan-config"}
                                        className={`flex items-center gap-3 px-3 py-2 rounded-lg border transition-all duration-300 ${isScanConfigGroupActive ? "bg-primary/10 border-primary/30 text-primary" : "bg-muted/20 border-border/40 text-muted-foreground"}`}
                                        onClick={() => {
                                            toggleGroupExpanded("scanConfig");
                                            setMobileOpen(false);
                                        }}
                                        title={collapsed ? t("route.scanConfig", "扫描配置") : undefined}
                                    >
                                        <span className={`p-1.5 rounded-md ${isScanConfigGroupActive ? "bg-primary/20" : "bg-muted/50"}`}>
                                            <Wrench className="w-[18px] h-[18px]" />
                                        </span>
                                        {!collapsed && (
                                            <span className={`font-mono tracking-wide ${isEnglish ? "text-sm" : "text-base"} ${isScanConfigGroupActive ? "font-semibold" : "font-medium"}`}>
                                                {t("route.scanConfig", "扫描配置")}
                                            </span>
                                        )}
                                    </Link>

                                    {isScanConfigGroupExpanded && scanConfigChildRoutes.length > 0 && (
                                        <div className="mt-1 pl-4 space-y-1">
                                            {scanConfigChildRoutes.map((route) =>
                                                renderRouteLink(route, {
                                                    compact: true,
                                                }),
                                            )}
                                        </div>
                                    )}
                                </div>
                            )}
                        </div>
                    </nav>

                    {/* Footer */}
                    <div
                        className="flex-shrink-0 p-3 space-y-1 relative"
                        style={{
                            background: "var(--cyber-bg-elevated)",
                            borderTop: "1px solid var(--cyber-border)",
                        }}
                    >
                        {/* Top accent line */}
                        <div className="absolute top-0 left-0 right-0 h-px bg-gradient-to-r from-transparent via-primary/20 to-transparent" />

                        {/* Theme Toggle */}
                        {/*<ThemeToggle collapsed={collapsed} />*/}

                        {/* Account Link */}
                        {/*<Link
                            to="/account"
                            className={`
                                flex items-center gap-3 px-3 py-2 rounded-lg transition-all duration-300 group
                                ${location.pathname === '/account'
                                    ? 'bg-primary/15 border border-primary/40'
                                    : 'border border-transparent hover:bg-card/60 hover:border-border/50'
                                }
                            `}
                            style={{
                                color: location.pathname === '/account' ? 'hsl(var(--primary))' : 'var(--cyber-text-muted)'
                            }}
                            onClick={() => setMobileOpen(false)}
                            title={collapsed ? "账号管理" : undefined}
                        >
                            <span className={`p-1.5 rounded-md transition-all duration-300 ${location.pathname === '/account' ? 'bg-primary/20' : 'group-hover:bg-muted/50'}`}>
                                <UserCircle className="w-[18px] h-[18px] flex-shrink-0" />
                            </span>
                            {!collapsed && (
                                <span className="font-mono text-sm">账号管理</span>
                            )}
                        </Link>*/}

                        <LanguageToggle
                            compact={collapsed}
                            className={collapsed ? "px-0" : "px-1"}
                        />
                    </div>
                </div>
            </aside>
        </>
    );
}
