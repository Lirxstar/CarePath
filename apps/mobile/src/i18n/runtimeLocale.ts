import type { AppLocale } from "./resources";

let runtimeLocale: AppLocale = "en";

export function getRuntimeLocale(): AppLocale {
  return runtimeLocale;
}

export function setRuntimeLocale(locale: AppLocale): void {
  runtimeLocale = locale;
}
