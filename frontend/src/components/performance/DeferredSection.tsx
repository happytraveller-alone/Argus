import { useEffect, useRef, useState, type ReactNode } from "react";
import SilentLoadingState from "@/components/performance/SilentLoadingState";
import { cn } from "@/shared/utils/utils";

interface DeferredSectionProps {
	children: ReactNode;
	className?: string;
	delayMs?: number;
	rootMargin?: string;
	minHeight?: number;
	fallback?: ReactNode;
	priority?: boolean;
}

export default function DeferredSection({
	children,
	className,
	delayMs = 250,
	rootMargin = "240px 0px",
	minHeight = 320,
	fallback,
	priority = false,
}: DeferredSectionProps) {
	const containerRef = useRef<HTMLDivElement | null>(null);
	const [isNearViewport, setIsNearViewport] = useState(priority);
	const [isMounted, setIsMounted] = useState(priority);

	useEffect(() => {
		if (priority) {
			setIsNearViewport(true);
			return;
		}
		if (isNearViewport) return;
		const element = containerRef.current;
		if (!element) return;
		if (typeof window === "undefined") {
			setIsNearViewport(true);
			return;
		}
		if (!("IntersectionObserver" in window)) {
			setIsNearViewport(true);
			return;
		}

		const observer = new IntersectionObserver(
			(entries) => {
				for (const entry of entries) {
					if (entry.isIntersecting) {
						setIsNearViewport(true);
						observer.disconnect();
						break;
					}
				}
			},
			{
				rootMargin,
			},
		);

		observer.observe(element);
		return () => observer.disconnect();
	}, [isNearViewport, priority, rootMargin]);

	useEffect(() => {
		if (priority) {
			setIsMounted(true);
			return;
		}
		if (!isNearViewport || isMounted) return;
		if (typeof window === "undefined") {
			setIsMounted(true);
			return;
		}
		const idleWindow = window as Window & {
			requestIdleCallback?: (
				callback: IdleRequestCallback,
				options?: IdleRequestOptions,
			) => number;
			cancelIdleCallback?: (handle: number) => void;
		};

		let timeoutId: number | null = null;
		let idleId: number | null = null;

		const mountSection = () => {
			setIsMounted(true);
		};

		if (delayMs <= 0) {
			mountSection();
			return;
		}

		timeoutId = window.setTimeout(() => {
			if (typeof idleWindow.requestIdleCallback === "function") {
				idleId = idleWindow.requestIdleCallback(mountSection, {
					timeout: delayMs * 4,
				});
				return;
			}
			mountSection();
		}, delayMs);

		return () => {
			if (timeoutId !== null) {
				window.clearTimeout(timeoutId);
			}
			if (
				idleId !== null &&
				typeof idleWindow.cancelIdleCallback === "function"
			) {
				idleWindow.cancelIdleCallback(idleId);
			}
		};
	}, [delayMs, isMounted, isNearViewport, priority]);

	return (
		<div ref={containerRef} className={cn("relative", className)}>
			{isMounted
				? children
				: (fallback ?? (
					<SilentLoadingState minHeight={minHeight} />
				))}
		</div>
	);
}
