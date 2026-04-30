import { matchPath } from "react-router-dom";
import type { RouteConfig } from "@/app/routes";
import type {
	SidebarNavGroupConfig,
	SidebarNavGroupId,
} from "@/app/sidebarNavGroups";

export interface NavigationRoute {
	route: RouteConfig;
	label: string;
	isActive: boolean;
	prefetch?: () => void;
}

export interface NavigationGroup {
	group: SidebarNavGroupConfig;
	label: string;
	routes: NavigationRoute[];
	isActive: boolean;
	prefetch?: () => void;
}

export interface NavigationModel {
	mainRoutes: NavigationRoute[];
	groups: NavigationGroup[];
	activeNavPath: string;
	isRouteActive: (route: RouteConfig) => boolean;
}

export interface BuildNavigationModelOptions {
	pathname: string;
	routes: RouteConfig[];
	groups: SidebarNavGroupConfig[];
	getRouteLabel: (route: RouteConfig) => string;
	getGroupLabel: (group: SidebarNavGroupConfig) => string;
	routePrefetchers?: Partial<Record<string, () => void>>;
	groupPrefetchers?: Partial<Record<SidebarNavGroupId, () => void>>;
}

const byNavOrder = (a: RouteConfig, b: RouteConfig) =>
	(a.navOrder ?? 999) - (b.navOrder ?? 999);

export function buildNavigationModel({
	pathname,
	routes,
	groups,
	getRouteLabel,
	getGroupLabel,
	routePrefetchers = {},
	groupPrefetchers = {},
}: BuildNavigationModelOptions): NavigationModel {
	const visibleRoutes = routes.filter(
		(route) => (route.navVisible ?? route.visible) !== false,
	);
	const matchesRoute = (path: string) =>
		Boolean(
			matchPath(
				{
					path,
					end: true,
				},
				pathname,
			),
		);
	const matchedRoute = routes.find((route) => matchesRoute(route.path));
	const activeNavPath = matchedRoute?.navParentPath || matchedRoute?.path || "";
	const isRouteActive = (route: RouteConfig) =>
		matchesRoute(route.path) || activeNavPath === route.path;
	const toNavigationRoute = (route: RouteConfig): NavigationRoute => ({
		route,
		label: getRouteLabel(route),
		isActive: isRouteActive(route),
		prefetch: routePrefetchers[route.path],
	});

	return {
		activeNavPath,
		isRouteActive,
		mainRoutes: visibleRoutes
			.filter((route) => (route.navGroup ?? "main") === "main")
			.sort(byNavOrder)
			.map(toNavigationRoute),
		groups: groups.map((group) => {
			const groupRoutes = visibleRoutes
				.filter((route) => route.navGroup === group.id)
				.sort(byNavOrder)
				.map(toNavigationRoute);

			return {
				group,
				label: getGroupLabel(group),
				routes: groupRoutes,
				isActive: groupRoutes.some((route) => route.isActive),
				prefetch: groupPrefetchers[group.id],
			};
		}),
	};
}
