import { createContext, useContext, useMemo, useState } from "react";
import { createTranslator, loadLanguage, saveLanguage } from "./i18n.mjs";

const Language = createContext(null);

export function LanguageProvider({ children, initialLanguage }) {
  const [language, setLanguage] = useState(initialLanguage);
  const t = useMemo(() => createTranslator(language), [language]);
  function changeLanguage(next) {
    saveLanguage(next);
    document.documentElement.lang = next;
    setLanguage(next);
  }
  return <Language.Provider value={{ language, changeLanguage, t }}>{children}</Language.Provider>;
}

export const useLanguage = () => useContext(Language);

export function initializeLanguage() {
  const language = loadLanguage();
  document.documentElement.lang = language;
  return language;
}
