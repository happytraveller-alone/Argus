/**
 * Sidebar Component
 * Premium Terminal Aesthetic with Enhanced Visual Design
 */

import { useCallback, useRef, useState } from "react";
import { Link, matchPath, useLocation } from "react-router-dom";
import { Button } from "@/components/ui/button";
import { ThemeToggle } from "@/components/ui/theme-toggle";
import {
	Menu,
	X,
	LayoutDashboard,
	FolderGit2,
	DatabaseBackup,
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
	Wrench,
	Zap,
} from "lucide-react";
import routes from "@/app/routes";
import {
	SIDEBAR_NAV_GROUPS,
	type SidebarNavGroupId,
} from "@/app/sidebarNavGroups";
import { useI18n } from "@/shared/i18n";
import { useLogoVariant } from "@/shared/branding/useLogoVariant";

// Icon mapping for routes with consistent sizing
const routeIcons: Record<string, React.ReactNode> = {
	"/": <Bot className="w-[1.125rem] h-[1.125rem]" />,
	"/dashboard": <LayoutDashboard className="w-[1.125rem] h-[1.125rem]" />,
	"/projects": <FolderGit2 className="w-[1.125rem] h-[1.125rem]" />,
	// "/instant-analysis": <Zap className="w-[1.125rem] h-[1.125rem]" />,
	// "/audit-tasks": <ListTodo className="w-[1.125rem] h-[1.125rem]" />,
	"/audit-rules": <Shield className="w-[1.125rem] h-[1.125rem]" />,
	"/opengrep-rules": <Code className="w-[1.125rem] h-[1.125rem]" />,
	"/tasks/static": <Shield className="w-[1.125rem] h-[1.125rem]" />,
	"/tasks/intelligent": <Bot className="w-[1.125rem] h-[1.125rem]" />,
	"/scan-config/engines": <Zap className="w-[1.125rem] h-[1.125rem]" />,
	"/scan-config/intelligent-engine": <Bot className="w-[1.125rem] h-[1.125rem]" />,
	"/scan-config/external-tools": <Wrench className="w-[1.125rem] h-[1.125rem]" />,
	"/data-management": <DatabaseBackup className="w-[1.125rem] h-[1.125rem]" />,
	// "/prompts": <MessageSquare className="w-[1.125rem] h-[1.125rem]" />,
	// "/recycle-bin": <Trash2 className="w-[1.125rem] h-[1.125rem]" />,
};

interface SidebarProps {
	collapsed: boolean;
	setCollapsed: (collapsed: boolean) => void;
}

export default function Sidebar({ collapsed, setCollapsed }: SidebarProps) {
	const location = useLocation();
	const [mobileOpen, setMobileOpen] = useState(false);
	const { t } = useI18n();
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
	const groupedRoutes = SIDEBAR_NAV_GROUPS.map((group) => ({
		...group,
		routes: sidebarRoutes
			.filter((route) => route.navGroup === group.id)
			.sort((a, b) => (a.navOrder ?? 999) - (b.navOrder ?? 999)),
	}));
	const matchesRoute = useCallback(
		(path: string) =>
			Boolean(
				matchPath(
					{
						path,
						end: true,
					},
					location.pathname,
				),
			),
		[location.pathname],
	);
	const matchedRoute = routes.find((route) => matchesRoute(route.path));
	const activeNavPath = matchedRoute?.navParentPath || matchedRoute?.path || "";
	const isRouteActive = useCallback(
		(route: (typeof routes)[number]) =>
			matchesRoute(route.path) || activeNavPath === route.path,
		[activeNavPath, matchesRoute],
	);

	const prefetchTaskGroupAssets = useCallback(() => {
		if (hasPrefetchedTaskGroupRef.current) return;
		hasPrefetchedTaskGroupRef.current = true;
		void import("@/features/tasks/services/taskActivitiesStore").then(
			({ prefetchTaskActivitiesSnapshot }) => {
				void prefetchTaskActivitiesSnapshot();
			},
		);
		void import("@/pages/TaskManagementStatic");
		void import("@/pages/TaskManagementIntelligent");
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
			void import("@/shared/api/database").then(({ api }) => {
				void api.getProjects();
			});
		void import("@/pages/Projects");
	}, []);

	const groupPrefetchers: Partial<Record<SidebarNavGroupId, () => void>> = {
		task: prefetchTaskGroupAssets,
	};

	const renderRouteLink = (
		route: (typeof routes)[number],
		options?: { compact?: boolean },
	) => {
		const isActive = isRouteActive(route);
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
					color: isActive ? "hsl(var(--primary))" : "var(--cyber-text-muted)",
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
						<LayoutDashboard className="w-[1.125rem] h-[1.125rem]" />
					)}
				</span>

				{!collapsed && (
					<span
						className={`tracking-wide transition-all duration-300 break-words leading-snug text-base ${isActive ? "font-semibold" : "font-medium"} ${compact ? "font-mono text-sm" : "font-mono"}`}
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
				{mobileOpen ? <X className="w-5 h-5" /> : <Menu className="w-5 h-5" />}
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
				}}
			>
				<div className="flex flex-col h-full relative">
					{/* Subtle gradient background */}
					<div className="absolute inset-0 bg-gradient-to-b from-primary/5 via-transparent to-transparent pointer-events-none" />

					{/* Logo Section */}
					<div
						className={`flex-shrink-0 relative flex items-center h-16 ${collapsed ? "px-3 justify-center" : "px-5 pr-6"}`}
						style={{
							background: "var(--cyber-bg-elevated)",
						}}
					>
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
										textShadow: "0 0 25px rgba(255,107,44,0.4)",
									}}
								>
									<span className="text-primary">Vul</span>
									<span style={{ color: "var(--cyber-text)" }}>Hunter</span>
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

							{groupedRoutes.map((group) => {
								if (group.routes.length === 0) {
									return null;
								}

								const isGroupActive = group.routes.some(isRouteActive);
								const isGroupExpanded = !collapsed;
								const groupLabel = t(group.titleKey, group.fallbackLabel);
								const GroupIcon = group.icon;
								const prefetchGroupAssets = groupPrefetchers[group.id];

								return (
									<div key={group.id} className="pt-1">
										<div
											data-sidebar-group-header={group.id}
											className={`flex items-center gap-3 px-3 py-2 rounded-lg border transition-all duration-300 cursor-default ${isGroupActive ? "bg-primary/10 border-primary/30 text-primary" : "bg-muted/20 border-border/40 text-muted-foreground"}`}
											title={collapsed ? groupLabel : undefined}
											onMouseEnter={() => {
												prefetchGroupAssets?.();
											}}
										>
											<span
												className={`p-1.5 rounded-md ${isGroupActive ? "bg-primary/20" : "bg-muted/50"}`}
											>
												<GroupIcon className="w-[1.125rem] h-[1.125rem]" />
											</span>
											{!collapsed && (
												<span
													className={`font-mono tracking-wide text-base ${isGroupActive ? "font-semibold" : "font-medium"}`}
												>
													{groupLabel}
												</span>
											)}
										</div>

										{isGroupExpanded && group.routes.length > 0 && (
											<div className="mt-1 pl-4 space-y-1">
												{group.routes.map((route) =>
													renderRouteLink(route, {
														compact: true,
													}),
												)}
											</div>
										)}
									</div>
								);
							})}
						</div>
					</nav>

					{/* Footer */}
					<div
						className="flex-shrink-0 p-3 space-y-1 relative"
						style={{
							background: "var(--cyber-bg-elevated)",
						}}
					>
						{/* Theme Toggle */}
						<ThemeToggle collapsed={collapsed} />
					</div>
				</div>
			</aside>
		</>
	);
}
