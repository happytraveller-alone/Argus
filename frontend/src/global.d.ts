// global types

declare module "three";
declare module "vanta/dist/vanta.net.min";
declare module "vanta/dist/vanta.net.min.js";

interface Window {
	THREE?: unknown;
	VANTA?: {
		NET: (config: Record<string, unknown>) => {
			destroy: () => void;
		};
	};
}
