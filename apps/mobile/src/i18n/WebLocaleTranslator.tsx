import { useEffect } from "react";
import { Platform } from "react-native";

import { useI18n } from "./I18nContext";
import { translateStaticText } from "./catalog";
import type { AppLocale } from "./resources";

const TRANSLATABLE_ATTRIBUTES = ["aria-label", "placeholder", "title"] as const;

function translateTextNode(node: Node, locale: AppLocale): void {
  const parent = node.parentElement;
  if (parent?.tagName === "SCRIPT" || parent?.tagName === "STYLE") {
    return;
  }
  const current = node.nodeValue;
  if (current === null) {
    return;
  }
  const next = translateStaticText(locale, current);
  if (next !== current) {
    node.nodeValue = next;
  }
}

function translateElementAttributes(element: Element, locale: AppLocale): void {
  for (const attribute of TRANSLATABLE_ATTRIBUTES) {
    const current = element.getAttribute(attribute);
    if (current === null) {
      continue;
    }
    const next = translateStaticText(locale, current);
    if (next !== current) {
      element.setAttribute(attribute, next);
    }
  }
}

function translateSubtree(root: Node, locale: AppLocale): void {
  if (root.nodeType === Node.TEXT_NODE) {
    translateTextNode(root, locale);
    return;
  }
  if (root.nodeType === Node.ELEMENT_NODE) {
    translateElementAttributes(root as Element, locale);
  }
  const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT);
  let current = walker.nextNode();
  while (current !== null) {
    translateTextNode(current, locale);
    current = walker.nextNode();
  }
  if (root.nodeType === Node.ELEMENT_NODE) {
    const elements = (root as Element).querySelectorAll<Element>(
      "[aria-label], [placeholder], [title]",
    );
    for (let index = 0; index < elements.length; index += 1) {
      translateElementAttributes(elements.item(index), locale);
    }
  }
}

export function WebLocaleTranslator() {
  const { locale } = useI18n();

  useEffect(() => {
    if (Platform.OS !== "web" || typeof document === "undefined") {
      return undefined;
    }
    const body = document.body;
    translateSubtree(body, locale);

    const observer = new MutationObserver((mutations) => {
      for (const mutation of mutations) {
        if (mutation.type === "characterData") {
          translateTextNode(mutation.target, locale);
          continue;
        }
        if (mutation.type === "attributes" && mutation.target.nodeType === Node.ELEMENT_NODE) {
          translateElementAttributes(mutation.target as Element, locale);
          continue;
        }
        for (let index = 0; index < mutation.addedNodes.length; index += 1) {
          translateSubtree(mutation.addedNodes.item(index), locale);
        }
      }
    });
    observer.observe(body, {
      subtree: true,
      childList: true,
      characterData: true,
      attributes: true,
      attributeFilter: [...TRANSLATABLE_ATTRIBUTES],
    });
    return () => {
      observer.disconnect();
    };
  }, [locale]);

  return null;
}
