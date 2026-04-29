/**
 * Header Component
 * Minimalist mechanical terminal header
 * Features: Enhanced glow effects, refined controls, premium feel
 */

import {
	ArrowLeft,
	Square,
	Download,
	Loader2,
} from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import type { HeaderProps } from "../types";

export function Header({
	title,
	task,
	isRunning,
	isCancelling,
	onBack,
	onCancel,
	onExport,
	metricTags = [],
}: HeaderProps) {
	return (
		<header className="relative flex-shrink-0 overflow-hidden border-b border-border/50 bg-card/80 px-6 py-4 backdrop-blur-md">
			<div className="absolute left-0 right-0 top-0 h-px bg-gradient-to-r from-transparent via-primary/50 to-transparent" />
			<div className="absolute inset-0 bg-gradient-to-r from-primary/5 via-transparent to-primary/5 pointer-events-none" />

			<div className="relative z-10 flex items-start justify-between gap-3 flex-wrap">
				<div className="min-w-0 flex-1 basis-[320px]">
					<div
						className="flex min-w-0 flex-wrap items-center gap-x-3 gap-y-2"
						data-agent-audit-title-row="true"
					>
						<h1 className="shrink-0 text-2xl font-bold tracking-wider text-foreground">
							{title}
						</h1>
						{metricTags.length > 0 ? (
							<div
								className="flex min-w-0 flex-wrap items-center gap-2"
								aria-label="智能审计概要标签"
							>
								{metricTags.map((tag, index) => (
									<Badge
										key={`${index}-${tag}`}
										variant="outline"
										className="h-9 max-w-[260px] truncate rounded-full border-border/70 bg-muted/30 px-3 text-sm font-semibold text-foreground/85"
										title={tag}
									>
										{tag}
									</Badge>
								))}
							</div>
						) : null}
					</div>
				</div>

				<div className="flex items-center gap-2 flex-wrap">
					{isRunning && (
						<Button
							variant="outline"
							className="cyber-btn-outline h-8 border-rose-500/40 text-rose-400 hover:bg-rose-500/10 hover:text-rose-300"
							onClick={onCancel}
							disabled={isCancelling}
						>
							{isCancelling ? (
								<>
									<Loader2 className="mr-1.5 h-3.5 w-3.5 animate-spin" />
									中止中
								</>
							) : (
								<>
									<Square className="mr-1.5 h-3.5 w-3.5" />
									中止
								</>
							)}
						</Button>
					)}

					<Button
						variant="outline"
						className="cyber-btn-outline h-8"
						onClick={onExport}
						disabled={!task}
					>
						<Download className="mr-1.5 h-3.5 w-3.5" />
						导出报告
					</Button>

					<Button
						variant="outline"
						className="cyber-btn-outline h-8"
						onClick={onBack}
					>
						<ArrowLeft className="mr-1.5 h-3.5 w-3.5" />
						返回
					</Button>
				</div>
			</div>

			<div className="absolute bottom-0 left-0 right-0 h-px bg-gradient-to-r from-transparent via-border/50 to-transparent" />
			{isRunning && (
				<>
					<div className="absolute bottom-0 left-1/2 -translate-x-1/2 w-1/2 h-px bg-gradient-to-r from-transparent via-emerald-500/60 to-transparent" />
					<div className="absolute bottom-0 left-1/2 -translate-x-1/2 w-1/3 h-4 bg-gradient-to-t from-emerald-500/10 to-transparent pointer-events-none" />
				</>
			)}
		</header>
	);
}

export default Header;
