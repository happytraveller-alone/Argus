import { createContext, useContext } from "react";
import type { ReactNode } from "react";
import { I18N_MESSAGES, type I18nKey } from "./messages";

interface LanguageContextValue {
  language: "zh";
  isEnglish: false;
  t: (key: I18nKey, fallback?: string) => string;
}

interface LanguageProviderProps {
  children: ReactNode;
}

const LanguageContext = createContext<LanguageContextValue | null>(null);
const LANGUAGE_CONTEXT_VALUE: LanguageContextValue = {
  language: "zh",
  isEnglish: false,
  t: (key, fallback) => I18N_MESSAGES.zh[key] ?? fallback ?? key,
};

export function LanguageProvider({ children }: LanguageProviderProps) {
  return (
    <LanguageContext.Provider value={LANGUAGE_CONTEXT_VALUE}>
      {children}
    </LanguageContext.Provider>
  );
}

export function useI18n(): LanguageContextValue {
  const context = useContext(LanguageContext);
  if (!context) {
    throw new Error("useI18n must be used within LanguageProvider");
  }

  return context;
}
