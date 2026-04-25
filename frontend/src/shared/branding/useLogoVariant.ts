import { useEffect, useState } from "react";

export const LOGO_VARIANTS = ["bp1", "bp2", "bp3", "bp4"] as const;
export type LogoVariant = (typeof LOGO_VARIANTS)[number];

const DEFAULT_LOGO_VARIANT: LogoVariant = "bp1";
const LOGO_STORAGE_KEY = "Argus_logo_variant";
const LOGO_CHANGE_EVENT = "Argus-logo-variant-change";

function isLogoVariant(value: string | null | undefined): value is LogoVariant {
    return Boolean(value && LOGO_VARIANTS.includes(value as LogoVariant));
}

function resolveStoredVariant(): LogoVariant {
    if (typeof window === "undefined") {
        return DEFAULT_LOGO_VARIANT;
    }
    const value = window.localStorage.getItem(LOGO_STORAGE_KEY);
    return isLogoVariant(value) ? value : DEFAULT_LOGO_VARIANT;
}

export function getLogoSrc(variant: LogoVariant): string {
    return `/logo_Argus_${variant}.png`;
}

export function setLogoVariant(variant: LogoVariant): LogoVariant {
    if (typeof window !== "undefined") {
        window.localStorage.setItem(LOGO_STORAGE_KEY, variant);
        window.dispatchEvent(
            new CustomEvent(LOGO_CHANGE_EVENT, {
                detail: { variant },
            }),
        );
    }
    return variant;
}

export function cycleLogoVariant(): LogoVariant {
    const current = resolveStoredVariant();
    const currentIndex = LOGO_VARIANTS.indexOf(current);
    const nextVariant =
        LOGO_VARIANTS[(currentIndex + 1) % LOGO_VARIANTS.length] ||
        DEFAULT_LOGO_VARIANT;
    return setLogoVariant(nextVariant);
}

export function useLogoVariant() {
    const [variant, setVariant] = useState<LogoVariant>(resolveStoredVariant);

    useEffect(() => {
        const handleCustomEvent = (event: Event) => {
            const customEvent = event as CustomEvent<{ variant?: string }>;
            const nextVariant = customEvent.detail?.variant;
            if (isLogoVariant(nextVariant)) {
                setVariant(nextVariant);
            } else {
                setVariant(resolveStoredVariant());
            }
        };

        const handleStorageEvent = (event: StorageEvent) => {
            if (event.key === LOGO_STORAGE_KEY) {
                setVariant(resolveStoredVariant());
            }
        };

        window.addEventListener(LOGO_CHANGE_EVENT, handleCustomEvent as EventListener);
        window.addEventListener("storage", handleStorageEvent);
        return () => {
            window.removeEventListener(
                LOGO_CHANGE_EVENT,
                handleCustomEvent as EventListener,
            );
            window.removeEventListener("storage", handleStorageEvent);
        };
    }, []);

    return {
        variant,
        logoSrc: getLogoSrc(variant),
        cycleLogoVariant,
        setLogoVariant,
    };
}