import { forwardRef, useCallback, useEffect, useRef, useState } from "react";
import type { AnchorHTMLAttributes, ReactNode } from "react";
import { Link, useLocation } from "react-router-dom";
import {
	Bot,
	ChevronDown,
	Code,
	DatabaseBackup,
	FolderGit2,
	LayoutDashboard,
	Menu,
	Shield,
	Wrench,
	Zap,
} from "lucide-react";
import routes from "@/app/routes";
import {
	SIDEBAR_NAV_GROUPS,
	type SidebarNavGroupId,
} from "@/app/sidebarNavGroups";
import { Button } from "@/components/ui/button";
import {
	DropdownMenu,
	DropdownMenuContent,
	DropdownMenuItem,
	DropdownMenuLabel,
	DropdownMenuSeparator,
	DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { ThemeToggleCompact } from "@/components/ui/theme-toggle";
import { cn } from "@/shared/utils/utils";
import { useLogoVariant } from "@/shared/branding/useLogoVariant";
import { useI18n } from "@/shared/i18n";
import {
	buildNavigationModel,
	type NavigationRoute,
} from "@/components/layout/navigationModel";

const routeIcons: Record<string, ReactNode> = {
	"/": <Bot className="h-[1.125rem] w-[1.125rem]" />,
	"/dashboard": <LayoutDashboard className="h-[1.125rem] w-[1.125rem]" />,
	"/projects": <FolderGit2 className="h-[1.125rem] w-[1.125rem]" />,
	"/audit-rules": <Shield className="h-[1.125rem] w-[1.125rem]" />,
	"/opengrep-rules": <Code className="h-[1.125rem] w-[1.125rem]" />,
	"/tasks/static": <Shield className="h-[1.125rem] w-[1.125rem]" />,
	"/tasks/intelligent": <Bot className="h-[1.125rem] w-[1.125rem]" />,
	"/scan-config/engines": <Zap className="h-[1.125rem] w-[1.125rem]" />,
	"/scan-config/intelligent-engine": (
		<Bot className="h-[1.125rem] w-[1.125rem]" />
	),
	"/scan-config/external-tools": (
		<Wrench className="h-[1.125rem] w-[1.125rem]" />
	),
	"/data-management": (
		<DatabaseBackup className="h-[1.125rem] w-[1.125rem]" />
	),
};

const DESKTOP_GROUP_CLOSE_DELAY_MS = 240;

function RouteIcon({ path }: { path: string }) {
	return routeIcons[path] || <LayoutDashboard className="h-[1.125rem] w-[1.125rem]" />;
}

function TopNavigationLink({
	item,
	className,
	onNavigate,
}: {
	item: NavigationRoute;
	className?: string;
	onNavigate?: () => void;
}) {
	const handlePrefetch = () => item.prefetch?.();

	return (
		<Link
			to={item.route.path}
			data-top-nav-active={item.isActive ? "true" : undefined}
			className={cn(
				"relative inline-flex min-h-10 items-center gap-2 rounded-sm border px-3 py-2 font-mono text-sm font-medium leading-snug transition-colors",
				item.isActive
					? "border-primary/40 bg-primary/15 text-primary"
					: "border-transparent text-muted-foreground hover:border-border hover:bg-muted/60 hover:text-foreground",
				className,
			)}
			onClick={onNavigate}
			onMouseEnter={handlePrefetch}
			onFocus={handlePrefetch}
		>
			<span
				className={cn(
					"inline-flex h-7 w-7 items-center justify-center rounded-sm",
					item.isActive ? "bg-primary/20" : "bg-muted/50",
				)}
			>
				<RouteIcon path={item.route.path} />
			</span>
			<span>{item.label}</span>
		</Link>
	);
}

const DropdownRouteLink = forwardRef<
	HTMLAnchorElement,
	{
		item: NavigationRoute;
	} & AnchorHTMLAttributes<HTMLAnchorElement>
>(({ item, className, onFocus, onMouseEnter, ...props }, ref) => {
	const handlePrefetch = () => item.prefetch?.();

	return (
		<Link
			ref={ref}
			to={item.route.path}
			data-top-nav-active={item.isActive ? "true" : undefined}
			className={cn(
				"flex w-full items-center justify-start gap-2 rounded-sm border border-transparent px-2 py-2 font-mono text-sm font-medium leading-snug transition-colors",
				item.isActive
					? "bg-primary/15 text-primary"
					: "text-muted-foreground hover:bg-muted hover:text-foreground",
				className,
			)}
			onMouseEnter={(event) => {
				handlePrefetch();
				onMouseEnter?.(event);
			}}
			onFocus={(event) => {
				handlePrefetch();
				onFocus?.(event);
			}}
			{...props}
		>
			<span
				className={cn(
					"inline-flex h-7 w-7 items-center justify-center rounded-sm",
					item.isActive ? "bg-primary/20" : "bg-muted/50",
				)}
			>
				<RouteIcon path={item.route.path} />
			</span>
			<span>{item.label}</span>
		</Link>
	);
});
DropdownRouteLink.displayName = "DropdownRouteLink";

export default function TopNavigation() {
	const location = useLocation();
	const { t } = useI18n();
	const { logoSrc } = useLogoVariant();
	const [openGroupId, setOpenGroupId] = useState<SidebarNavGroupId | null>(null);
	const closeTimerRef = useRef<number | null>(null);
	const hasPrefetchedTaskGroupRef = useRef(false);
	const hasPrefetchedDashboardRef = useRef(false);
	const hasPrefetchedProjectsRef = useRef(false);

	const clearCloseTimer = useCallback(() => {
		if (closeTimerRef.current !== null && typeof window !== "undefined") {
			window.clearTimeout(closeTimerRef.current);
			closeTimerRef.current = null;
		}
	}, []);

	const openGroupMenu = useCallback(
		(groupId: SidebarNavGroupId) => {
			clearCloseTimer();
			setOpenGroupId(groupId);
		},
		[clearCloseTimer],
	);

	const scheduleGroupClose = useCallback(
		(groupId: SidebarNavGroupId) => {
			if (typeof window === "undefined") return;
			clearCloseTimer();
			closeTimerRef.current = window.setTimeout(() => {
				setOpenGroupId((currentGroupId) =>
					currentGroupId === groupId ? null : currentGroupId,
				);
				closeTimerRef.current = null;
			}, DESKTOP_GROUP_CLOSE_DELAY_MS);
		},
		[clearCloseTimer],
	);

	useEffect(() => clearCloseTimer, [clearCloseTimer]);

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

	const model = buildNavigationModel({
		pathname: location.pathname,
		routes,
		groups: SIDEBAR_NAV_GROUPS,
		getRouteLabel: (route) =>
			route.nameKey ? t(route.nameKey, route.name) : route.name,
		getGroupLabel: (group) => t(group.titleKey, group.fallbackLabel),
		routePrefetchers: {
			"/dashboard": prefetchDashboardAssets,
			"/projects": prefetchProjectsAssets,
		},
		groupPrefetchers: {
			task: prefetchTaskGroupAssets,
		},
	});

	return (
		<header
			className="relative z-30 border-b border-border/60"
			data-top-navigation-shell
			style={{ background: "var(--cyber-bg)" }}
		>
			<div className="flex min-h-16 w-full items-center gap-3 px-4 lg:px-6">
				<Link
					to="/"
					className="group flex flex-shrink-0 items-center"
					aria-label="Argus"
				>
					<img
						src={logoSrc}
						alt="Argus"
						className="h-10 w-10 object-contain transition-transform duration-300 group-hover:scale-105"
					/>
				</Link>

				<nav className="hidden min-w-0 flex-1 items-center gap-1 md:flex">
					{model.mainRoutes.map((item) => (
						<TopNavigationLink key={item.route.path} item={item} />
					))}

					{model.groups.map((group) => {
						if (group.routes.length === 0) return null;

						const GroupIcon = group.group.icon;

						return (
							<DropdownMenu
								key={group.group.id}
								modal={false}
								open={openGroupId === group.group.id}
								onOpenChange={(open) => {
									if (open) {
										openGroupMenu(group.group.id);
										return;
									}
									scheduleGroupClose(group.group.id);
								}}
							>
								<div
									onMouseEnter={() => {
										openGroupMenu(group.group.id);
										group.prefetch?.();
									}}
									onMouseLeave={() => scheduleGroupClose(group.group.id)}
								>
									<DropdownMenuTrigger asChild>
										<button
											type="button"
											data-top-nav-group-trigger={group.group.id}
											data-top-nav-active={group.isActive ? "true" : undefined}
											className={cn(
												"inline-flex min-h-10 items-center gap-2 rounded-sm border px-3 py-2 font-mono text-sm font-medium leading-snug transition-colors",
												group.isActive
													? "border-primary/40 bg-primary/15 text-primary"
													: "border-transparent text-muted-foreground hover:border-border hover:bg-muted/60 hover:text-foreground",
											)}
											onFocus={() => {
												openGroupMenu(group.group.id);
												group.prefetch?.();
											}}
										>
											<span
												className={cn(
													"inline-flex h-7 w-7 items-center justify-center rounded-sm",
													group.isActive ? "bg-primary/20" : "bg-muted/50",
												)}
											>
												<GroupIcon className="h-[1.125rem] w-[1.125rem]" />
											</span>
											<span>{group.label}</span>
											<ChevronDown className="h-4 w-4" />
										</button>
									</DropdownMenuTrigger>
								</div>
								<DropdownMenuContent
									align="start"
									className="w-[var(--radix-dropdown-menu-trigger-width)]"
									onMouseEnter={() => openGroupMenu(group.group.id)}
									onMouseLeave={() => scheduleGroupClose(group.group.id)}
								>
									{group.routes.map((item) => (
										<DropdownMenuItem key={item.route.path} asChild>
											<DropdownRouteLink item={item} />
										</DropdownMenuItem>
									))}
								</DropdownMenuContent>
							</DropdownMenu>
						);
					})}
				</nav>

				<div className="ml-auto flex items-center gap-2">
					<ThemeToggleCompact />
					<DropdownMenu>
						<DropdownMenuTrigger asChild>
							<Button
								type="button"
								variant="ghost"
								size="icon"
								className="md:hidden"
								aria-label="打开导航菜单"
							>
								<Menu className="h-5 w-5" />
							</Button>
						</DropdownMenuTrigger>
						<DropdownMenuContent align="end" className="max-h-[75vh] min-w-64">
							{model.mainRoutes.map((item) => (
								<DropdownMenuItem key={item.route.path} asChild>
									<DropdownRouteLink item={item} />
								</DropdownMenuItem>
							))}

							{model.groups.map((group) => {
								if (group.routes.length === 0) return null;
								const GroupIcon = group.group.icon;

								return (
									<div key={group.group.id}>
										<DropdownMenuSeparator />
										<DropdownMenuLabel className="flex items-center gap-2">
											<GroupIcon className="h-4 w-4" />
											{group.label}
										</DropdownMenuLabel>
										{group.routes.map((item) => (
											<DropdownMenuItem key={item.route.path} asChild>
												<DropdownRouteLink item={item} />
											</DropdownMenuItem>
										))}
									</div>
								);
							})}
						</DropdownMenuContent>
					</DropdownMenu>
				</div>
			</div>
		</header>
	);
}
