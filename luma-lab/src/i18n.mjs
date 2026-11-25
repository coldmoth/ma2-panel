import { en, ru } from "./messages.mjs";

const dictionaries = { en, ru };
export const LANGUAGE_KEY = "luma.language.v1";

function supported(value) {
  return typeof value === "string" && Object.hasOwn(dictionaries, value);
}

export function loadLanguage(storage) {
  try {
    storage ??= globalThis.localStorage;
    for (const key of [LANGUAGE_KEY, "luma.language", "luma.locale"]) {
      const saved = storage?.getItem(key);
      if (supported(saved)) return saved;
      if (saved) {
        try {
          const parsed = JSON.parse(saved);
          if (supported(parsed)) return parsed;
        } catch {}
      }
    }
  } catch {}
  return "en";
}

export function saveLanguage(language, storage) {
  if (!supported(language)) return;
  try {
    storage ??= globalThis.localStorage;
    storage?.setItem(LANGUAGE_KEY, language);
  } catch {}
}

export function createTranslator(language = "en") {
  const locale = supported(language) ? language : "en";
  const pluralRules = new Intl.PluralRules(locale);
  const numbers = new Intl.NumberFormat(locale);
  return function t(key, params = {}) {
    const entry = Object.hasOwn(en, key) ? dictionaries[locale][key] ?? en[key] : key;
    const template = typeof entry === "string" ? entry : entry[pluralRules.select(params.count)] ?? entry.other;
    return template.replace(/\{(\w+)\}/g, (placeholder, name) => {
      if (!Object.hasOwn(params, name)) return placeholder;
      const value = params[name];
      return typeof value === "number" ? numbers.format(value) : String(value);
    });
  };
}
