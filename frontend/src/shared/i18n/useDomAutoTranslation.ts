import { useEffect, useRef } from "react";
import {
  containsChinese,
  getCachedEnglish,
  translateToEnglish,
} from "./translationService";
import type { AppLanguage } from "./LanguageProvider";

const TRANSFORMABLE_ATTRIBUTES = [
  "title",
  "placeholder",
  "aria-label",
  "alt",
] as const;
const SKIP_TAGS = new Set([
  "SCRIPT",
  "STYLE",
  "NOSCRIPT",
  "CODE",
  "PRE",
]);

type TransformableAttribute = (typeof TRANSFORMABLE_ATTRIBUTES)[number];
type ElementAttributeStore = Partial<Record<TransformableAttribute, string>>;

function shouldSkipElement(element: Element): boolean {
  if (SKIP_TAGS.has(element.tagName)) {
    return true;
  }

  if (element.getAttribute("contenteditable") === "true") {
    return true;
  }

  if (
    element.closest("[data-no-i18n='true']") ||
    element.closest(".monaco-editor")
  ) {
    return true;
  }

  return false;
}

function shouldTranslateText(text: string): boolean {
  const trimmed = text.trim();
  if (!trimmed) {
    return false;
  }

  if (!containsChinese(trimmed)) {
    return false;
  }

  if (trimmed.length > 260) {
    return false;
  }

  const lineBreakCount = (trimmed.match(/\n/g) ?? []).length;
  return lineBreakCount <= 3;
}

export function useDomAutoTranslation(language: AppLanguage): void {
  const languageRef = useRef(language);
  const textOriginalRef = useRef<WeakMap<Text, string>>(new WeakMap());
  const attrOriginalRef = useRef<WeakMap<Element, ElementAttributeStore>>(
    new WeakMap(),
  );

  useEffect(() => {
    languageRef.current = language;
    document.documentElement.lang = language === "zh" ? "zh-CN" : "en-US";
    document.documentElement.dataset.lang = language;
  }, [language]);

  useEffect(() => {
    const root = document.body;
    if (!root) {
      return;
    }

    const syncSourceText = (node: Text): string => {
      const current = node.nodeValue ?? "";
      const map = textOriginalRef.current;
      const stored = map.get(node);

      if (stored === undefined) {
        map.set(node, current);
        return current;
      }

      if (languageRef.current === "zh") {
        if (
          stored !== current &&
          (containsChinese(current) || !containsChinese(stored))
        ) {
          map.set(node, current);
          return current;
        }
        return stored;
      }

      if (containsChinese(current) && current !== stored) {
        map.set(node, current);
        return current;
      }

      return stored;
    };

    const applyTextNode = (node: Text): void => {
      const parent = node.parentElement;
      if (!parent || shouldSkipElement(parent)) {
        return;
      }

      const sourceText = syncSourceText(node);

      if (languageRef.current === "zh") {
        if (node.nodeValue !== sourceText) {
          node.nodeValue = sourceText;
        }
        return;
      }

      if (!shouldTranslateText(sourceText)) {
        return;
      }

      const translated =
        getCachedEnglish(sourceText) ?? translateToEnglish(sourceText);
      if (translated && node.nodeValue !== translated) {
        node.nodeValue = translated;
      }
    };

    const syncSourceAttribute = (
      element: Element,
      attrName: TransformableAttribute,
    ): string | null => {
      const current = element.getAttribute(attrName);
      if (current === null) {
        return null;
      }

      let store = attrOriginalRef.current.get(element);
      if (!store) {
        store = {};
        attrOriginalRef.current.set(element, store);
      }

      const stored = store[attrName];
      if (stored === undefined) {
        store[attrName] = current;
        return current;
      }

      if (languageRef.current === "zh") {
        if (
          stored !== current &&
          (containsChinese(current) || !containsChinese(stored))
        ) {
          store[attrName] = current;
          return current;
        }
        return stored;
      }

      if (containsChinese(current) && current !== stored) {
        store[attrName] = current;
        return current;
      }

      return stored;
    };

    const applyAttribute = (
      element: Element,
      attrName: TransformableAttribute,
    ): void => {
      const sourceValue = syncSourceAttribute(element, attrName);
      if (sourceValue === null) {
        return;
      }

      if (languageRef.current === "zh") {
        if (element.getAttribute(attrName) !== sourceValue) {
          element.setAttribute(attrName, sourceValue);
        }
        return;
      }

      if (!shouldTranslateText(sourceValue)) {
        return;
      }

      const translated =
        getCachedEnglish(sourceValue) ?? translateToEnglish(sourceValue);
      if (translated && element.getAttribute(attrName) !== translated) {
        element.setAttribute(attrName, translated);
      }
    };

    const applyElementAttributes = (element: Element): void => {
      if (shouldSkipElement(element)) {
        return;
      }

      for (const attrName of TRANSFORMABLE_ATTRIBUTES) {
        if (element.hasAttribute(attrName)) {
          applyAttribute(element, attrName);
        }
      }
    };

    const traverseNode = (node: Node): void => {
      if (node.nodeType === Node.TEXT_NODE) {
        applyTextNode(node as Text);
        return;
      }

      if (node.nodeType !== Node.ELEMENT_NODE) {
        return;
      }

      const element = node as Element;
      if (shouldSkipElement(element)) {
        return;
      }

      applyElementAttributes(element);

      for (const child of Array.from(element.childNodes)) {
        traverseNode(child);
      }
    };

    const observer = new MutationObserver((mutations) => {
      for (const mutation of mutations) {
        if (mutation.type === "characterData") {
          const textNode = mutation.target;
          if (textNode.nodeType === Node.TEXT_NODE) {
            applyTextNode(textNode as Text);
          }
          continue;
        }

        if (mutation.type === "attributes") {
          if (mutation.target.nodeType === Node.ELEMENT_NODE) {
            applyElementAttributes(mutation.target as Element);
          }
          continue;
        }

        for (const addedNode of Array.from(mutation.addedNodes)) {
          traverseNode(addedNode);
        }
      }
    });

    observer.observe(root, {
      childList: true,
      subtree: true,
      characterData: true,
      attributes: true,
      attributeFilter: [...TRANSFORMABLE_ATTRIBUTES],
    });

    traverseNode(root);

    return () => {
      observer.disconnect();
    };
  }, [language]);
}
