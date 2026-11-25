import { createTranslator } from "./i18n.mjs";

const defaultT = createTranslator();
const evidenceStates = ["sent", "not_sent", "error", "unknown"];
const namedParams = {
  show_mismatch: ["deskShow", "planShow"],
  plan_missing: ["deskShow"],
  plan_conflict: ["deskShow"],
};

function cleanText(value) {
  if (typeof value !== "string") return undefined;
  return value
    .replace(/(\blogin\s+"[^"\r\n]*"\s+)"[^"\r\n]*"/gi, '$1"***"')
    .replace(/\b(Bearer|Basic)\s+[\w.+/=-]+/gi, "$1 ***")
    .replace(/(\b[\w-]*(?:password|passwd|token|secret|api[_-]?key|authorization|cookie)\b["']?\s*[:=]\s*)(?:"[^"\r\n]*"|'[^'\r\n]*'|[^\r\n,;}]+)/gi, "$1***")
    .replace(/\bsk-[A-Za-z0-9_-]+/g, "***")
    .slice(0, 1500);
}

function errorCode(source) {
  const code = source.code ?? source.reason?.code;
  return typeof code === "string" && /^[a-z][a-z0-9_.]{0,63}$/.test(code) ? code : undefined;
}

export function errorDetails(source) {
  if (!source) return null;
  const code = errorCode(source);
  const err = cleanText(source.err ?? source.reason?.message ??
    (source instanceof BridgeError ? undefined : source.message ?? source));
  const evidence = Array.isArray(source.command_evidence)
    ? source.command_evidence.filter((entry) => evidenceStates.includes(entry))
    : [];
  const outcome = ["failed", "partial", "unknown", "completed"].includes(source.outcome)
    ? source.outcome : undefined;
  if (code || err || outcome || evidence.length) {
    return { code, err, outcome, command_evidence: evidence.length ? evidence : undefined };
  }
  return null;
}

export function errorMessage(source, t) {
  if (!source) return undefined;
  const code = errorCode(source);
  const key = `error.${code}`;
  const fields = Object.hasOwn(namedParams, code) ? namedParams[code] : [];
  const params = source.params ?? source.reason?.params;
  if (fields.length && fields.every((name) => typeof params?.[name] === "string" && params[name])) {
    return t(`${key}.named`, Object.fromEntries(fields.map((name) => [name, cleanText(params[name])])));
  }
  const message = t(key);
  return message === key ? t("error.action_failed") : message;
}

export class BridgeError extends Error {
  constructor(source) {
    super(errorMessage(source, defaultT));
    Object.assign(this, errorDetails(source));
    const params = source.params ?? source.reason?.params;
    if (Object.hasOwn(namedParams, this.code)) {
      this.params = Object.fromEntries(namedParams[this.code].map((name) => [name, cleanText(params?.[name])]));
    }
  }
}
