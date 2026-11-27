import React from "react";
import { createRoot } from "react-dom/client";
import { Theme } from "@astryxdesign/core/theme";
import "@astryxdesign/core/reset.css";
import "@astryxdesign/core/astryx.css";
import "@astryxdesign/theme-neutral/theme.css";
import { lumaTheme } from "./theme/luma.js";
import "./theme/luma.css";
import "./styles.css";
import App from "./App.jsx";
import { initializeLanguage, LanguageProvider, useLanguage } from "./Language.jsx";
const designLab = !__LUMA_HALL_VERSION__ && location.pathname.replace(/\/$/, "") === "/design-lab";
const DesignLab = __LUMA_HALL_VERSION__ ? null : React.lazy(() => import("./DesignLab.jsx"));
const initialLanguage = initializeLanguage();

function Root() {
  const { t } = useLanguage();
  return (
    <Theme theme={lumaTheme} mode="dark">
      {designLab ? (
        <React.Suspense fallback={<p>{t("shell.loadingDesignLab")}</p>}>
          <DesignLab />
        </React.Suspense>
      ) : (
        <App />
      )}
    </Theme>
  );
}

createRoot(document.getElementById("root")).render(
  <LanguageProvider initialLanguage={initialLanguage}><Root /></LanguageProvider>,
);
