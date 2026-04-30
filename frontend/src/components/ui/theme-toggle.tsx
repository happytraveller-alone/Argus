
import { useTheme } from "next-themes";
import { useEffect, useState, useCallback } from "react";
import { Sun, Moon } from "lucide-react";
import { cn } from "@/shared/utils/utils";

interface ThemeToggleProps {
  collapsed?: boolean;
  className?: string;
}

const enableTransition = () => {
  const html = document.documentElement;
  html.classList.add("theme-transition");
  setTimeout(() => {
    html.classList.remove("theme-transition");
  }, 280);
};

export function ThemeToggle({ collapsed = false, className }: ThemeToggleProps) {
  const { theme, setTheme, resolvedTheme } = useTheme();
  const [mounted, setMounted] = useState(false);

  useEffect(() => {
    setMounted(true);
  }, []);

  const handleThemeChange = useCallback(
    (newTheme: string) => {
      enableTransition();
      setTheme(newTheme);
    },
    [setTheme]
  );

  if (!mounted) {
    return <div className={cn("h-9 w-full animate-pulse rounded-lg bg-muted", className)} />;
  }

  const isDark = (resolvedTheme ?? theme) === "dark";
  const nextTheme = isDark
    ? { value: "light", icon: Sun, label: "浅色" }
    : { value: "dark", icon: Moon, label: "深色" };
  const NextIcon = nextTheme.icon;
  const toggleTheme = () => {
    handleThemeChange(nextTheme.value);
  };

  if (collapsed) {
    return (
      <button
        onClick={toggleTheme}
        className={cn(
          "flex items-center justify-center w-9 h-9 rounded-lg",
          "bg-muted/50 hover:bg-muted/80 border border-transparent",
          "transition-colors duration-200",
          className
        )}
        title={`切换到${nextTheme.label}模式`}
      >
        <NextIcon
          className={cn(
            "w-4 h-4 transition-transform duration-200",
            nextTheme.value === "light" && "text-orange-500",
            nextTheme.value === "dark"  && "text-violet-400"
          )}
        />
      </button>
    );
  }

  return (
    <div className={cn("w-full", className)}>
      <button
        onClick={toggleTheme}
        className={cn(
          "flex w-full items-center justify-center gap-2 rounded-lg px-3 py-2.5",
          "bg-muted/50 text-sm font-medium text-muted-foreground",
          "transition-colors duration-200 hover:bg-muted/80 hover:text-foreground"
        )}
        title={`切换到${nextTheme.label}模式`}
      >
        <NextIcon
          className={cn(
            "h-4 w-4 transition-transform duration-200",
            nextTheme.value === "light" && "text-orange-500",
            nextTheme.value === "dark" && "text-violet-400"
          )}
        />
        <span className="font-mono tracking-wide">{nextTheme.label}</span>
      </button>
    </div>
  );
}

export function ThemeToggleCompact({ className }: { className?: string }) {
  const { setTheme, resolvedTheme } = useTheme();
  const [mounted, setMounted] = useState(false);

  useEffect(() => {
    setMounted(true);
  }, []);

  const handleToggle = useCallback(() => {
    enableTransition();
    setTheme(resolvedTheme === "dark" ? "light" : "dark");
  }, [setTheme, resolvedTheme]);

  if (!mounted) return null;

  const isDark = resolvedTheme === "dark";

  return (
    <button
      onClick={handleToggle}
      className={cn(
        "relative flex items-center justify-center w-9 h-9 rounded-lg",
        "bg-muted/60 hover:bg-muted border border-transparent hover:border-border",
        "transition-colors duration-200",
        className
      )}
      title={isDark ? "切换到浅色模式" : "切换到深色模式"}
    >
      <Moon
        className={cn(
          "absolute w-4 h-4 transition-all duration-200 text-violet-400",
          isDark ? "opacity-100 rotate-0 scale-100" : "opacity-0 -rotate-90 scale-0"
        )}
      />
      <Sun
        className={cn(
          "absolute w-4 h-4 transition-all duration-200 text-orange-500",
          isDark ? "opacity-0 rotate-90 scale-0" : "opacity-100 rotate-0 scale-100"
        )}
      />
    </button>
  );
}

export default ThemeToggle;
