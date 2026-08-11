import type { AppLocale } from "./resources";

// Non-React service objects read this value so API requests follow the selected interface locale.
let runtimeLocale: AppLocale = "en";

export function getRuntimeLocale(): AppLocale {
  return runtimeLocale;
}

export function setRuntimeLocale(locale: AppLocale): void {
  runtimeLocale = locale;
}
