import {
  createContext,
  useCallback,
  useContext,
  useMemo,
  useState,
  type PropsWithChildren,
} from "react";

import { translateStaticText } from "./catalog";
import { MOBILE_STRINGS, type AppLocale, type MobileStrings } from "./resources";
import { setRuntimeLocale } from "./runtimeLocale";

interface I18nContextValue {
  locale: AppLocale;
  setLocale: (locale: AppLocale) => void;
  strings: MobileStrings;
  translate: (text: string) => string;
}

const I18nContext = createContext<I18nContextValue | null>(null);

export function I18nProvider({ children }: PropsWithChildren) {
  const [locale, setLocaleState] = useState<AppLocale>("en");
  const setLocale = useCallback((next: AppLocale) => {
    setRuntimeLocale(next);
    setLocaleState(next);
  }, []);
  const value = useMemo<I18nContextValue>(
    () => ({
      locale,
      setLocale,
      strings: MOBILE_STRINGS[locale],
      translate: (text: string) => translateStaticText(locale, text),
    }),
    [locale, setLocale],
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
