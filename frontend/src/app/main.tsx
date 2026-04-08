import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { ThemeProvider } from "next-themes";
import "@/assets/styles/globals.css";
import App from "./App.tsx";
import { AppWrapper } from "@/components/layout/PageMeta";
import { ErrorBoundary } from "@/components/common/ErrorBoundary";
import { LanguageProvider } from "@/shared/i18n";
import { installTranslatorDomCompatPatch } from "@/shared/utils/browserDomCompat";
import "@/shared/utils/fetchWrapper"; // 初始化fetch拦截器

localStorage.removeItem("theme");
installTranslatorDomCompatPatch();

createRoot(document.getElementById("root")!).render(
    <StrictMode>
        <LanguageProvider>
            <ErrorBoundary>
                <ThemeProvider
                    attribute="class"
                    defaultTheme="dark"
                    enableSystem={false}
                    disableTransitionOnChange={false}
                >
                    <AppWrapper>
                        <App />
                    </AppWrapper>
                </ThemeProvider>
            </ErrorBoundary>
        </LanguageProvider>
    </StrictMode>,
);
