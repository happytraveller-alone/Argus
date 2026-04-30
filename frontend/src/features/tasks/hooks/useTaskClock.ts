import { useEffect, useState } from "react";

interface UseTaskClockOptions {
	enabled: boolean;
	intervalMs?: number;
}

export function useTaskClock({
	enabled,
	intervalMs = 5000,
}: UseTaskClockOptions): number {
	const [nowMs, setNowMs] = useState(() => Date.now());

	useEffect(() => {
		if (!enabled) {
			setNowMs(Date.now());
			return;
		}

		setNowMs(Date.now());
		const timer = window.setInterval(() => {
			setNowMs(Date.now());
		}, intervalMs);

		return () => {
			window.clearInterval(timer);
		};
	}, [enabled, intervalMs]);

	return nowMs;
}
