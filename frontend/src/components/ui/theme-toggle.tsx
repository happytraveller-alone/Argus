/**
 * Theme Toggle Component
 */

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

  const themes = [
    { value: "dark",  icon: Moon, label: "深色" },
    { value: "light", icon: Sun,  label: "浅色" },
    // { value: "system", icon: Monitor, label: "系统" },
  ];

  const cycleTheme = () => {
    const currentIndex = themes.findIndex((t) => t.value === theme);
    const nextIndex = (currentIndex + 1) % themes.length;
    handleThemeChange(themes[nextIndex].value);
  };

  const currentTheme = themes.find((t) => t.value === theme) ?? themes[0];
  const CurrentIcon = currentTheme.icon;

  if (collapsed) {
    return (
      <button
        onClick={cycleTheme}
        className={cn(
          "flex items-center justify-center w-9 h-9 rounded-lg",
          "bg-muted/60 hover:bg-muted border border-transparent hover:border-border",
          "transition-colors duration-200",
          className
        )}
        title={`当前：${currentTheme.label}模式`}
      >
        <CurrentIcon
          className={cn(
            "w-4 h-4 transition-transform duration-200",
            resolvedTheme === "light" && "text-orange-500",
            resolvedTheme === "dark"  && "text-violet-400"
          )}
        />
      </button>
    );
  }

  return (
    <div className={cn("w-full px-3 pb-2", className)}>
      <p className="text-xs text-muted-foreground mb-1.5 px-0.5">主题</p>
      <div className="flex items-center gap-1 p-1 rounded-lg bg-muted/60 border border-border/50">
        {themes.map(({ value, icon: Icon, label }) => {
          const isActive = theme === value;
          return (
            <button
              key={value}
              onClick={() => handleThemeChange(value)}
              className={cn(
                "flex-1 flex items-center justify-center gap-1.5 py-1.5 px-3 rounded-md",
                "text-xs font-medium transition-all duration-200",
                isActive
                  ? "bg-background text-foreground border border-border shadow-sm"
                  : "text-muted-foreground hover:text-foreground hover:bg-background/60"
              )}
            >
              <Icon
                className={cn(
                  "w-3.5 h-3.5",
                  isActive && value === "light" && "text-orange-500",
                  isActive && value === "dark"  && "text-violet-400"
                )}
              />
              {label}
            </button>
          );
        })}
      </div>
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