import { Zap, Bot, Layers, ArrowRight, GitBranch, X } from "lucide-react";
import { useNavigate } from "react-router-dom";
import { useEffect, useRef, useState, useCallback } from "react";
import * as THREE from "three";
import { useLogoVariant } from "@/shared/branding/useLogoVariant";

type HomeScanCard = {
	key: "static" | "agent" | "hybrid";
	title: string;
	intro: string;
	icon: typeof Zap;
	targetRoute: string;
};

const homeScanCards: HomeScanCard[] = [
	{
		key: "static",
		title: "静态扫描",
		intro: "规则驱动漏洞检测",
		icon: Zap,
		targetRoute: "/tasks/static?openCreate=1&source=home-card",
	},
	{
		key: "agent",
		title: "智能扫描",
		intro: "AI Agent 代码推理",
		icon: Bot,
		targetRoute: "/tasks/intelligent?openCreate=1&source=home-card",
	},
	{
		key: "hybrid",
		title: "混合扫描",
		intro: "静态分析 + AI 推理",
		icon: Layers,
		targetRoute: "/tasks/hybrid?openCreate=1&source=home-card",
	},
];

// ═══════════════════════════════════════════════════════════════════
//  Resizable + Draggable Modal
// ═══════════════════════════════════════════════════════════════════

const MIN_W = 400;
const MIN_H = 300;
const DEFAULT_W = 860;
const DEFAULT_H = 580;

interface ModalRect {
	x: number;
	y: number;
	w: number;
	h: number;
}

function GitNexusModal({ onClose }: { onClose: () => void }) {
	const [rect, setRect] = useState<ModalRect>(() => ({
		x: Math.max(0, (window.innerWidth - DEFAULT_W) / 2),
		y: Math.max(0, (window.innerHeight - DEFAULT_H) / 2),
		w: DEFAULT_W,
		h: DEFAULT_H,
	}));
	const [minimized, setMinimized] = useState(false);

	// refs so mousemove handler always has fresh values without re-binding
	const dragRef = useRef<{
		sx: number;
		sy: number;
		ox: number;
		oy: number;
	} | null>(null);
	const resizeRef = useRef<{
		edge: string;
		sx: number;
		sy: number;
		ox: number;
		oy: number;
		ow: number;
		oh: number;
	} | null>(null);

	// global mouse tracking
	useEffect(() => {
		const onMove = (e: MouseEvent) => {
			if (dragRef.current) {
				const d = dragRef.current;
				setRect((r) => ({
					...r,
					x: Math.max(
						0,
						Math.min(window.innerWidth - r.w, d.ox + e.clientX - d.sx),
					),
					y: Math.max(
						0,
						Math.min(window.innerHeight - 40, d.oy + e.clientY - d.sy),
					),
				}));
			}
			if (resizeRef.current) {
				const r = resizeRef.current;
				const dx = e.clientX - r.sx;
				const dy = e.clientY - r.sy;
				setRect(() => {
					let { x, y, w, h } = { x: r.ox, y: r.oy, w: r.ow, h: r.oh };
					if (r.edge.includes("e")) w = Math.max(MIN_W, r.ow + dx);
					if (r.edge.includes("s")) h = Math.max(MIN_H, r.oh + dy);
					if (r.edge.includes("w")) {
						const nw = Math.max(MIN_W, r.ow - dx);
						x = r.ox + r.ow - nw;
						w = nw;
					}
					if (r.edge.includes("n")) {
						const nh = Math.max(MIN_H, r.oh - dy);
						y = r.oy + r.oh - nh;
						h = nh;
					}
					return { x, y, w, h };
				});
			}
		};
		const onUp = () => {
			dragRef.current = null;
			resizeRef.current = null;
		};
		window.addEventListener("mousemove", onMove);
		window.addEventListener("mouseup", onUp);
		return () => {
			window.removeEventListener("mousemove", onMove);
			window.removeEventListener("mouseup", onUp);
		};
	}, []);

	const startDrag = useCallback(
		(e: React.MouseEvent) => {
			if ((e.target as HTMLElement).closest("button")) return;
			e.preventDefault();
			dragRef.current = {
				sx: e.clientX,
				sy: e.clientY,
				ox: rect.x,
				oy: rect.y,
			};
		},
		[rect.x, rect.y],
	);

	const startResize = useCallback(
		(e: React.MouseEvent, edge: string) => {
			e.preventDefault();
			e.stopPropagation();
			resizeRef.current = {
				edge,
				sx: e.clientX,
				sy: e.clientY,
				ox: rect.x,
				oy: rect.y,
				ow: rect.w,
				oh: rect.h,
			};
		},
		[rect],
	);

	// 8 resize handles: n s e w ne nw se sw
	const handles: { edge: string; style: React.CSSProperties }[] = [
		{
			edge: "n",
			style: { top: -4, left: 12, right: 12, height: 8, cursor: "n-resize" },
		},
		{
			edge: "s",
			style: { bottom: -4, left: 12, right: 12, height: 8, cursor: "s-resize" },
		},
		{
			edge: "e",
			style: { right: -4, top: 12, bottom: 12, width: 8, cursor: "e-resize" },
		},
		{
			edge: "w",
			style: { left: -4, top: 12, bottom: 12, width: 8, cursor: "w-resize" },
		},
		{
			edge: "ne",
			style: { top: -4, right: -4, width: 14, height: 14, cursor: "ne-resize" },
		},
		{
			edge: "nw",
			style: { top: -4, left: -4, width: 14, height: 14, cursor: "nw-resize" },
		},
		{
			edge: "se",
			style: {
				bottom: -4,
				right: -4,
				width: 14,
				height: 14,
				cursor: "se-resize",
			},
		},
		{
			edge: "sw",
			style: {
				bottom: -4,
				left: -4,
				width: 14,
				height: 14,
				cursor: "sw-resize",
			},
		},
	];

	return (
		<div
			className="fixed z-50"
			style={{
				left: rect.x,
				top: rect.y,
				width: rect.w,
				height: minimized ? "auto" : rect.h,
			}}
		>
			{/* resize handles */}
			{!minimized &&
				handles.map((h) => (
					<div
						key={h.edge}
						className="absolute z-10"
						style={h.style}
						onMouseDown={(e) => startResize(e, h.edge)}
					/>
				))}

			{/* window */}
			<div
				className="flex flex-col rounded-xl overflow-hidden h-full"
				style={{
					height: minimized ? "auto" : "100%",
					background: "rgba(5, 8, 16, 0.94)",
					border: "1px solid rgba(255,255,255,0.07)",
					boxShadow:
						"0 32px 96px rgba(0,0,0,0.75), 0 0 0 1px rgba(59,130,246,0.10), inset 0 1px 0 rgba(255,255,255,0.05)",
					backdropFilter: "blur(20px)",
				}}
			>
				{/* ── title bar ── */}
				<div
					className="flex items-center gap-2 px-3.5 py-2.5 flex-shrink-0 select-none"
					style={{
						background: "rgba(255,255,255,0.025)",
						borderBottom: minimized
							? "none"
							: "1px solid rgba(255,255,255,0.055)",
						cursor: "grab",
					}}
					onMouseDown={startDrag}
				>
					{/* traffic lights */}
					<button
						onClick={onClose}
						className="w-3 h-3 rounded-full transition-opacity"
						style={{ background: "#ff5f56", flexShrink: 0 }}
						title="关闭"
					/>
					<button
						onClick={() => setMinimized((v) => !v)}
						className="w-3 h-3 rounded-full transition-opacity"
						style={{ background: "#febc2e", flexShrink: 0 }}
						title={minimized ? "展开" : "收起"}
					/>
					{/* green dot — noop, just for aesthetics */}
					<div
						className="w-3 h-3 rounded-full"
						style={{ background: "#28c840", flexShrink: 0 }}
					/>

					{/* title */}
					<div className="flex items-center gap-1.5 ml-2 flex-1 min-w-0">
						<GitBranch
							className="w-3 h-3 flex-shrink-0"
							style={{ color: "#4b5563" }}
						/>
						<span
							className="text-[11px] font-mono truncate"
							style={{ color: "#6b7280" }}
						>
							GitNexus — File Dependency Graph
						</span>
					</div>

					{/* size hint */}
					{!minimized && (
						<span
							className="text-[9px] font-mono mr-2 flex-shrink-0"
							style={{ color: "#374151" }}
						>
							{Math.round(rect.w)} × {Math.round(rect.h)}
						</span>
					)}

					<button
						onClick={onClose}
						className="p-1 rounded transition-colors flex-shrink-0"
						style={{ color: "#374151" }}
						onMouseEnter={(e) => (e.currentTarget.style.color = "#9ca3af")}
						onMouseLeave={(e) => (e.currentTarget.style.color = "#374151")}
					>
						<X className="w-3.5 h-3.5" />
					</button>
				</div>

				{/* ── iframe ── */}
				{!minimized && (
					<div className="flex-1 overflow-hidden">
						<iframe
							src="http://localhost:5174"
							className="w-full h-full border-0 block"
							title="GitNexus"
						/>
					</div>
				)}
			</div>
		</div>
	);
}

// ═══════════════════════════════════════════════════════════════════
//  Main Page
// ═══════════════════════════════════════════════════════════════════

export function HomeScanCards() {
	const navigate = useNavigate();
	const { logoSrc, cycleLogoVariant } = useLogoVariant();

	const vantaRef = useRef<HTMLDivElement>(null);
	const vantaEffect = useRef<{ destroy: () => void } | null>(null);
	const [showGraph, setShowGraph] = useState(false);

	useEffect(() => {
		let cancelled = false;
		const reduceMotion = window.matchMedia("(prefers-reduced-motion: reduce)");

		if (reduceMotion.matches) {
			return;
		}

		async function initVanta() {
			try {
				const module = await import("vanta/dist/vanta.net.min");
				const createNetEffect = (module.default ?? module) as (
					config: Record<string, unknown>,
				) => { destroy: () => void };
				if (
					cancelled ||
					!vantaRef.current ||
					typeof createNetEffect !== "function"
				)
					return;
				vantaEffect.current = createNetEffect({
					el: vantaRef.current,
					THREE,
					mouseControls: true,
					touchControls: true,
					gyroControls: false,
					minHeight: 200,
					minWidth: 200,
					scale: 1,
					scaleMobile: 1,
					color: 0x275c99,
					backgroundColor: 0x02050d,
					points: 10,
					maxDistance: 17,
					spacing: 20,
				});
			} catch (err) {
				console.warn("Vanta load failed:", err);
			}
		}
		initVanta();
		return () => {
			cancelled = true;
			vantaEffect.current?.destroy();
			vantaEffect.current = null;
		};
	}, []);

	return (
		<>
			{showGraph && <GitNexusModal onClose={() => setShowGraph(false)} />}

			<div
				ref={vantaRef}
				className="home-hero-shell relative flex min-h-[100dvh] items-center justify-center overflow-hidden"
			>
				<div className="home-hero-grid pointer-events-none absolute inset-0 z-0" />
				<div className="home-hero-veil pointer-events-none absolute inset-0 z-0" />
				<div className="home-hero-spotlight pointer-events-none absolute inset-0 z-0" />
				<div className="home-hero-scanlines pointer-events-none absolute inset-0 z-0" />
				<div className="vignette pointer-events-none absolute inset-0 z-0" />

				<div className="relative z-10 mx-auto flex w-full max-w-[1240px] flex-col px-6 py-12 text-center sm:py-16 lg:py-20">
					<div className="home-hero-frame mx-auto w-full max-w-5xl px-6 py-8 sm:px-10 sm:py-10 lg:px-14 lg:py-14">
						<div className="mb-8 flex flex-col items-center justify-center gap-5 sm:mb-10 sm:flex-row">
							<button
								onClick={cycleLogoVariant}
								className="home-logo-button flex h-20 w-20 flex-shrink-0 items-center justify-center rounded-3xl"
							>
								<img
									src={logoSrc}
									alt="VulHunter"
									className="h-16 w-16 object-contain"
								/>
							</button>
							<div className="space-y-3">
								<h1 className="font-mono text-5xl font-bold tracking-[0.2em] text-white sm:text-6xl lg:text-7xl">
									VulHunter
								</h1>
								<div className="mx-auto h-px w-28 bg-gradient-to-r from-transparent via-primary/60 to-transparent" />
							</div>
						</div>

						<div className="mx-auto mb-6 max-w-3xl">
							<span className="home-status-chip inline-flex items-center rounded-full px-4 py-2 text-sm text-foreground/75">
								1000+ 漏洞规则 · AI Agent 推理
							</span>
						</div>

						<div className="mb-4">
							<button
								onClick={() =>
									navigate("/tasks/hybrid?openCreate=1&source=home-primary")
								}
								className="home-primary-cta group inline-flex items-center justify-center rounded-2xl px-10 py-4 text-lg font-bold text-white sm:px-14 sm:py-5 sm:text-xl"
							>
								<span className="flex items-center gap-3 justify-center">
									一键开始安全审计
									<ArrowRight className="h-6 w-6 transition-transform duration-200 ease-out group-hover:translate-x-1" />
								</span>
							</button>
						</div>
					</div>

					<div className="mx-auto mt-8 grid w-full max-w-5xl gap-5 md:grid-cols-3">
						{homeScanCards.map((card) => {
							const Icon = card.icon;
							return (
								<button
									key={card.key}
									onClick={() => navigate(card.targetRoute)}
									className="home-scan-card group relative rounded-[22px] p-6 text-left transition"
								>
									<ArrowRight className="absolute right-5 top-5 h-4 w-4 text-primary/85 opacity-0 transition-all duration-200 ease-out group-hover:translate-x-1 group-hover:opacity-100" />
									<div className="mb-4 flex items-center gap-3">
										<div className="home-scan-card-icon rounded-xl p-2.5 text-primary">
											<Icon className="h-5 w-5" />
										</div>
										<h3 className="text-lg font-semibold text-white">
											{card.title}
										</h3>
									</div>
									<p className="max-w-[18rem] text-sm leading-7 text-foreground/72">
										{card.intro}
									</p>
								</button>
							);
						})}
					</div>
				</div>
			</div>
		</>
	);
}

export default HomeScanCards;
