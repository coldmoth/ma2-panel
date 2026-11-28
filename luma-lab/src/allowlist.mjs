const MAX_FIXTURE_ID = 99999;
const MAX_FIXTURE_COUNT = 4096;
const MAX_EXEC_PAGE = 999;
const MAX_EXEC_NUM = 999;
const MAX_EXEC_RANGE = 500;
const MAX_EXEC_COUNT = 2048;

function normalizeInput(input) {
  if (Array.isArray(input)) {
    return input.map((v) => String(v ?? "").trim()).filter(Boolean).join(", ");
  }
  return String(input ?? "").trim();
}

function tokenizeRanges(text) {
  if (!text) return [];
  return text
    .replace(/[–—]/g, "-")
    .replace(/\bthru\b/gi, "-")
    .replace(/\s*-\s*/g, "-")
    .split(/[\s,;]+/)
    .map((token) => token.trim())
    .filter(Boolean);
}

/**
 * Parse fixture IDs and ranges such as "1-20, 25" into a sorted, deduplicated array of positive integers.
 * @returns {{ ok: true, values: number[] } | { ok: false, invalid: string, reason: string, values: number[] }}
 */
export function parseFixtureRange(input) {
  const text = normalizeInput(input);
  if (!text) return { ok: true, values: [] };
  const tokens = tokenizeRanges(text);
  const seen = new Set();

  for (const token of tokens) {
    const single = token.match(/^(\d+)$/);
    if (single) {
      const id = Number(single[1]);
      if (!Number.isSafeInteger(id) || id < 1 || id > MAX_FIXTURE_ID) {
        return { ok: false, invalid: token, reason: "out_of_bounds", values: [] };
      }
      seen.add(id);
      if (seen.size > MAX_FIXTURE_COUNT) {
        return { ok: false, invalid: token, reason: "range_too_large", values: [] };
      }
      continue;
    }

    const range = token.match(/^(\d+)-(\d+)$/);
    if (range) {
      const start = Number(range[1]);
      const end = Number(range[2]);
      if (
        !Number.isSafeInteger(start) ||
        !Number.isSafeInteger(end) ||
        start < 1 ||
        end < 1 ||
        start > MAX_FIXTURE_ID ||
        end > MAX_FIXTURE_ID
      ) {
        return { ok: false, invalid: token, reason: "out_of_bounds", values: [] };
      }
      if (start > end) {
        return { ok: false, invalid: token, reason: "range_order", values: [] };
      }
      if (end - start + 1 > MAX_FIXTURE_COUNT) {
        return { ok: false, invalid: token, reason: "range_too_large", values: [] };
      }
      for (let id = start; id <= end; id++) {
        seen.add(id);
        if (seen.size > MAX_FIXTURE_COUNT) {
          return { ok: false, invalid: token, reason: "range_too_large", values: [] };
        }
      }
      continue;
    }

    return { ok: false, invalid: token, reason: "invalid_token", values: [] };
  }

  return { ok: true, values: [...seen].sort((a, b) => a - b) };
}

/**
 * Format an array of positive fixture IDs into compact ranges such as "1-20, 25".
 */
export function formatFixtureRange(ids) {
  if (!Array.isArray(ids) || ids.length === 0) return "";
  const sorted = [
    ...new Set(
      ids
        .map((v) => Number(v))
        .filter((n) => Number.isInteger(n) && n >= 1 && n <= MAX_FIXTURE_ID),
    ),
  ].sort((a, b) => a - b);

  if (sorted.length === 0) return "";
  const parts = [];
  let start = sorted[0];
  let end = sorted[0];

  for (let i = 1; i < sorted.length; i++) {
    const id = sorted[i];
    if (id === end + 1) {
      end = id;
    } else {
      parts.push(start === end ? `${start}` : `${start}-${end}`);
      start = id;
      end = id;
    }
  }
  parts.push(start === end ? `${start}` : `${start}-${end}`);
  return parts.join(", ");
}

function compareExec(a, b) {
  if (a.page !== b.page) return a.page - b.page;
  return a.exec - b.exec;
}

/**
 * Parse executor IDs and ranges such as "1.101-1.110, 2.1" (also supports shorthand "1.101-110").
 * @returns {{ ok: true, values: string[] } | { ok: false, invalid: string, reason: string, values: string[] }}
 */
export function parseExecRange(input) {
  const text = normalizeInput(input);
  if (!text) return { ok: true, values: [] };
  const tokens = tokenizeRanges(text);
  const seen = new Map();

  const addOne = (page, exec, token) => {
    if (
      !Number.isInteger(page) ||
      !Number.isInteger(exec) ||
      page < 1 ||
      page > MAX_EXEC_PAGE ||
      exec < 1 ||
      exec > MAX_EXEC_NUM
    ) {
      return { ok: false, invalid: token, reason: "out_of_bounds", values: [] };
    }
    const key = `${page}.${exec}`;
    seen.set(key, { page, exec, key });
    if (seen.size > MAX_EXEC_COUNT) {
      return { ok: false, invalid: token, reason: "range_too_large", values: [] };
    }
    return null;
  };

  for (const token of tokens) {
    const single = token.match(/^(\d+)\.(\d+)$/);
    if (single) {
      const err = addOne(Number(single[1]), Number(single[2]), token);
      if (err) return err;
      continue;
    }

    const fullRange = token.match(/^(\d+)\.(\d+)-(\d+)\.(\d+)$/);
    if (fullRange) {
      const p1 = Number(fullRange[1]);
      const e1 = Number(fullRange[2]);
      const p2 = Number(fullRange[3]);
      const e2 = Number(fullRange[4]);
      if (p1 !== p2) {
        return { ok: false, invalid: token, reason: "cross_page", values: [] };
      }
      if (e1 > e2) {
        return { ok: false, invalid: token, reason: "range_order", values: [] };
      }
      if (e2 - e1 + 1 > MAX_EXEC_RANGE) {
        return { ok: false, invalid: token, reason: "range_too_large", values: [] };
      }
      for (let e = e1; e <= e2; e++) {
        const err = addOne(p1, e, token);
        if (err) return err;
      }
      continue;
    }

    const shortRange = token.match(/^(\d+)\.(\d+)-(\d+)$/);
    if (shortRange) {
      const p1 = Number(shortRange[1]);
      const e1 = Number(shortRange[2]);
      const e2 = Number(shortRange[3]);
      if (e1 > e2) {
        return { ok: false, invalid: token, reason: "range_order", values: [] };
      }
      if (e2 - e1 + 1 > MAX_EXEC_RANGE) {
        return { ok: false, invalid: token, reason: "range_too_large", values: [] };
      }
      for (let e = e1; e <= e2; e++) {
        const err = addOne(p1, e, token);
        if (err) return err;
      }
      continue;
    }

    return { ok: false, invalid: token, reason: "invalid_token", values: [] };
  }

  const values = [...seen.values()].sort(compareExec).map((item) => item.key);
  return { ok: true, values };
}

/**
 * Format an array of executor strings (e.g. ["1.101", "1.102", "2.1"]) into compact ranges ("1.101-1.102, 2.1").
 */
export function formatExecRange(execs) {
  if (!Array.isArray(execs) || execs.length === 0) return "";
  const seen = new Map();
  for (const raw of execs) {
    const m = String(raw ?? "").trim().match(/^(\d+)\.(\d+)$/);
    if (!m) continue;
    const page = Number(m[1]);
    const exec = Number(m[2]);
    if (page < 1 || page > MAX_EXEC_PAGE || exec < 1 || exec > MAX_EXEC_NUM) continue;
    const key = `${page}.${exec}`;
    seen.set(key, { page, exec, key });
  }
  const sorted = [...seen.values()].sort(compareExec);
  if (sorted.length === 0) return "";

  const parts = [];
  let page = sorted[0].page;
  let start = sorted[0].exec;
  let end = sorted[0].exec;

  for (let i = 1; i < sorted.length; i++) {
    const item = sorted[i];
    if (item.page === page && item.exec === end + 1) {
      end = item.exec;
    } else {
      parts.push(start === end ? `${page}.${start}` : `${page}.${start}-${page}.${end}`);
      page = item.page;
      start = item.exec;
      end = item.exec;
    }
  }
  parts.push(start === end ? `${page}.${start}` : `${page}.${start}-${page}.${end}`);
  return parts.join(", ");
}
