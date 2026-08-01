import { createContext, useContext, useMemo, useState, type PropsWithChildren } from "react";

import { MOBILE_STRINGS, type AppLocale, type MobileStrings } from "./resources";

interface I18nContextValue {
  locale: AppLocale;
  setLocale: (locale: AppLocale) => void;
  strings: MobileStrings;
}

const I18nContext = createContext<I18nContextValue | null>(null);

export function I18nProvider({ children }: PropsWithChildren) {
  const [locale, setLocale] = useState<AppLocale>("en");
  const value = useMemo<I18nContextValue>(
    () => ({ locale, setLocale, strings: MOBILE_STRINGS[locale] }),
    [locale],
  );
  return <I18nContext.Provider value={value}>{children}</I18nContext.Provider>;
}

export function useI18n(): I18nContextValue {
  const value = useContext(I18nContext);
  if (value === null) {
    throw new Error("useI18n must be used inside I18nProvider");
  }
  return value;
}
