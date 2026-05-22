import { Link } from "react-router-dom";
import { Brain, Code2, Search, ArrowRight } from "lucide-react";

const SCAN_ENGINES = [
	{
		name: "Opengrep 扫描",
		icon: Search,
		path: "/tasks/static",
		iconBg: "bg-emerald-500/10 border-emerald-500/20",
		iconColor: "text-emerald-400",
		cardBorder: "border-emerald-500/20 hover:border-emerald-400/50",
		cardBg: "hover:bg-emerald-500/5",
		glow: "hover:shadow-emerald-500/10",
	},
	{
		name: "CodeQL 扫描",
		icon: Code2,
		path: "/tasks/static",
		iconBg: "bg-sky-500/10 border-sky-500/20",
		iconColor: "text-sky-400",
		cardBorder: "border-sky-500/20 hover:border-sky-400/50",
		cardBg: "hover:bg-sky-500/5",
		glow: "hover:shadow-sky-500/10",
	},
	{
		name: "智能扫描",
		icon: Brain,
		path: "/tasks/intelligent",
		iconBg: "bg-violet-500/10 border-violet-500/20",
		iconColor: "text-violet-400",
		cardBorder: "border-violet-500/20 hover:border-violet-400/50",
		cardBg: "hover:bg-violet-500/5",
		glow: "hover:shadow-violet-500/10",
	},
];

export default function Home() {
	return (
		<div className="min-h-screen bg-background text-foreground relative overflow-hidden">
			{/* Mesh gradient background */}
			<div className="absolute inset-0 pointer-events-none">
				<div className="absolute inset-0 bg-[radial-gradient(ellipse_80%_50%_at_20%_-10%,hsl(var(--primary)/0.12),transparent)]" />
				<div className="absolute inset-0 bg-[radial-gradient(ellipse_60%_40%_at_80%_110%,hsl(var(--primary)/0.08),transparent)]" />
				<div className="absolute inset-0 bg-[linear-gradient(to_bottom,transparent_60%,hsl(var(--background)/0.8))]" />
			</div>

			{/* Subtle grid overlay */}
			<div
				className="absolute inset-0 pointer-events-none opacity-[0.03]"
				style={{
					backgroundImage:
						"linear-gradient(hsl(var(--foreground)) 1px, transparent 1px), linear-gradient(90deg, hsl(var(--foreground)) 1px, transparent 1px)",
					backgroundSize: "48px 48px",
				}}
			/>

			<div className="relative z-10 flex items-center justify-center min-h-screen px-12 py-16">
				<div className="grid w-full gap-12 lg:grid-cols-[1fr_1fr] items-center">

					{/* Left: Logo only */}
					<div className="flex items-center justify-center">
						<div className="relative w-full flex items-center justify-center">
							<div className="absolute -inset-8 rounded-full bg-primary/8 blur-3xl" />
							<img
								src="/argus.png"
								alt="Argus"
								className="relative w-full max-w-full h-auto object-contain drop-shadow-2xl"
							/>
						</div>
					</div>

					{/* Right: Engine Cards */}
					<div className="flex flex-col gap-4">
						{SCAN_ENGINES.map((engine) => {
							const Icon = engine.icon;
							return (
								<Link
									key={engine.name}
									to={engine.path}
									className={`group relative flex items-center gap-5 rounded-xl border bg-background/40 backdrop-blur-sm p-8 transition-all duration-300 ${engine.cardBorder} ${engine.cardBg} hover:shadow-lg ${engine.glow}`}
								>
									<div className={`flex h-16 w-16 shrink-0 items-center justify-center rounded-xl border ${engine.iconBg} transition-transform duration-300 group-hover:scale-110`}>
										<Icon className={`h-8 w-8 ${engine.iconColor}`} />
									</div>
									<span className={`font-bold text-2xl ${engine.iconColor}`}>
										{engine.name}
									</span>
									<ArrowRight className={`ml-auto h-6 w-6 shrink-0 ${engine.iconColor} opacity-0 -translate-x-2 transition-all duration-300 group-hover:opacity-100 group-hover:translate-x-0`} />
								</Link>
							);
						})}
					</div>
				</div>
			</div>
		</div>
	);
}
