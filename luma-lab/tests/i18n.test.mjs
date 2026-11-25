import { test } from "node:test";
import assert from "node:assert/strict";
import { LANGUAGE_KEY, createTranslator, loadLanguage, saveLanguage } from "../src/i18n.mjs";
import { BridgeError, errorDetails, errorMessage } from "../src/errors.mjs";
import { en, ru } from "../src/messages.mjs";

const english = createTranslator("en");
const russian = createTranslator("ru");

test("fresh profiles default to English, explicit choices restore and override older preferences", () => {
  const values = new Map();
  const storage = { getItem: key => values.get(key), setItem: (key, value) => values.set(key, value) };
  assert.equal(loadLanguage(storage), "en");
  values.set("luma.language", '"ru"');
  assert.equal(loadLanguage(storage), "ru");
  saveLanguage("en", storage);
  assert.equal(values.get(LANGUAGE_KEY), "en");
  assert.equal(loadLanguage(storage), "en");
  const blocked = { getItem() { throw new Error("storage blocked"); }, setItem() { throw new Error("storage blocked"); } };
  assert.equal(loadLanguage(blocked), "en");
  assert.doesNotThrow(() => saveLanguage("ru", blocked));
});

test("dictionaries match and format plurals and numbers with Intl", () => {
  assert.deepEqual(Object.keys(en).sort(), Object.keys(ru).sort());
  assert.equal(english("shell.fixtureCount", { count: 1 }), "1 fixture");
  assert.equal(english("shell.fixtureCount", { count: 1234 }), "1,234 fixtures");
  assert.equal(russian("shell.fixtureCount", { count: 2 }), "2 прибора");
  assert.equal(russian("shell.fixtureCount", { count: 5 }), "5 приборов");
  assert.equal(russian("shell.number", { value: 1234 }), new Intl.NumberFormat("ru").format(1234));
});

test("every translated variant accepts the same named parameters", () => {
  function fields(message) {
    return [...new Set(Array.from(message.matchAll(/\{(\w+)\}/g), match => match[1]))].sort();
  }
  for (const [key, source] of Object.entries(en)) {
    const target = ru[key];
    assert.equal(typeof source, typeof target, key);
    const expected = fields(typeof source === "string" ? source : source.other);
    for (const message of [source, target]) {
      const variants = typeof message === "string" ? [message] : Object.values(message);
      for (const variant of variants) assert.deepEqual(fields(variant), expected, key);
    }
  }
});

test("structured errors interpolate names as text and switch language without re-reading the response", () => {
  const name = '<img src=x onerror="alert(1)">';
  const error = new BridgeError({
    code: "show_mismatch", params: { deskShow: name, planShow: "План A", ignored: "hidden" }, err: "legacy",
  });
  assert.equal(errorMessage(error, english), `Console show: ${name}. Local plan: План A. Open the plan for the console show.`);
  assert.equal(errorMessage(error, russian), `Пульт: ${name}. Локальный план: План A. Откройте план шоу пульта.`);
  assert.equal(errorMessage({ code: "show_mismatch", params: {} }, english), en["error.show_mismatch"]);
  assert.deepEqual(Object.keys(error.params), ["deskShow", "planShow"]);
});

test("unknown and legacy errors fall back safely and keep redacted diagnostics", () => {
  for (const code of [undefined, "future_error", "constructor", { toString: "malformed" }]) {
    const error = new BridgeError({
      code, err: 'Ошибка: Login "panel" "ma2-pass"\nAuthorization: Bearer api-token\n"Password": "hidden"',
      outcome: "failed", command_evidence: ["not_sent", "hidden"],
    });
    assert.equal(errorMessage(error, english), "Could not complete the action.");
    assert.equal(errorMessage(error, russian), "Не удалось выполнить действие.");
    assert.deepEqual(errorDetails(error).command_evidence, ["not_sent"]);
    assert.match(errorDetails(error).err, /Ошибка: Login "panel" "\*\*\*"/);
    assert.doesNotMatch(errorDetails(error).err, /ma2-pass|api-token|hidden/);
  }
});
