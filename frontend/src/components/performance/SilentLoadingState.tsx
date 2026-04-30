import { cn } from "@/shared/utils/utils";

interface SilentLoadingStateProps {
	className?: string;
	label?: string;
	minHeight?: number | string;
}

export default function SilentLoadingState({
	className,
	label = "加载中...",
	minHeight,
}: SilentLoadingStateProps) {
	return (
		<div
			aria-live="polite"
			role="status"
			className={cn("w-full bg-transparent", className)}
			style={minHeight === undefined ? undefined : { minHeight }}
		>
			<span className="sr-only">{label}</span>
		</div>
	);
}
