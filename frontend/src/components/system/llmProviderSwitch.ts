export function resolveProviderSwitchFieldValue(options: {
	currentValue: string | null | undefined;
	wasTouched: boolean;
	nextDefaultValue: string | null | undefined;
}): string {
	const currentValue = String(options.currentValue ?? "");
	const nextDefaultValue = String(options.nextDefaultValue ?? "").trim();
	const hasCurrentValue = currentValue.trim().length > 0;

	if (options.wasTouched && hasCurrentValue) {
		return currentValue;
	}
	if (nextDefaultValue) {
		return nextDefaultValue;
	}
	return hasCurrentValue ? currentValue : "";
}
