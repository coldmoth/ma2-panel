import { test } from "node:test";
import assert from "node:assert/strict";
import {
  formatExecRange,
  formatFixtureRange,
  parseExecRange,
  parseFixtureRange,
} from "../src/allowlist.mjs";

test("parseFixtureRange handles empty, single IDs, ranges, Thru, dashes, and deduplication", () => {
  assert.deepEqual(parseFixtureRange(""), { ok: true, values: [] });
  assert.deepEqual(parseFixtureRange("   "), { ok: true, values: [] });
  assert.deepEqual(parseFixtureRange("1-5, 10, 3"), {
    ok: true,
    values: [1, 2, 3, 4, 5, 10],
  });
  assert.deepEqual(parseFixtureRange("25, 1 - 4; 2–3, 10 Thru 12"), {
    ok: true,
    values: [1, 2, 3, 4, 10, 11, 12, 25],
  });
  const twenty = parseFixtureRange("1-20, 25");
  assert.equal(twenty.ok, true);
  assert.equal(twenty.values.length, 21);
  assert.equal(twenty.values[0], 1);
  assert.equal(twenty.values[19], 20);
  assert.equal(twenty.values[20], 25);
});

test("parseFixtureRange rejects invalid tokens, reversed ranges, and oversized ranges", () => {
  const badToken = parseFixtureRange("1-5, abc");
  assert.equal(badToken.ok, false);
  assert.equal(badToken.invalid, "abc");
  assert.equal(badToken.reason, "invalid_token");

  const reversed = parseFixtureRange("10-5");
  assert.equal(reversed.ok, false);
  assert.equal(reversed.reason, "range_order");

  const zero = parseFixtureRange("0, 1");
  assert.equal(zero.ok, false);
  assert.equal(zero.reason, "out_of_bounds");

  const huge = parseFixtureRange("1-9000");
  assert.equal(huge.ok, false);
  assert.equal(huge.reason, "range_too_large");
});

test("formatFixtureRange compresses consecutive IDs and round-trips", () => {
  assert.equal(formatFixtureRange([]), "");
  assert.equal(formatFixtureRange([25, 1, 2, 3, 4, 5, 5, 8]), "1-5, 8, 25");
  const parsed = parseFixtureRange("1-20, 25, 30-32");
  assert.equal(formatFixtureRange(parsed.values), "1-20, 25, 30-32");
});

test("parseExecRange handles single executors, full ranges, shorthand ranges, and sorting", () => {
  assert.deepEqual(parseExecRange(""), { ok: true, values: [] });
  assert.deepEqual(parseExecRange("1.101-1.103, 2.1, 1.102"), {
    ok: true,
    values: ["1.101", "1.102", "1.103", "2.1"],
  });
  assert.deepEqual(parseExecRange("1.101-103; 2.10 Thru 2.11"), {
    ok: true,
    values: ["1.101", "1.102", "1.103", "2.10", "2.11"],
  });
  const ten = parseExecRange("1.101-1.110, 2.1");
  assert.equal(ten.ok, true);
  assert.equal(ten.values.length, 11);
  assert.equal(ten.values[0], "1.101");
  assert.equal(ten.values[9], "1.110");
  assert.equal(ten.values[10], "2.1");
});

test("parseExecRange rejects cross-page ranges, inverted ranges, and malformed tokens", () => {
  const crossPage = parseExecRange("1.101-2.105");
  assert.equal(crossPage.ok, false);
  assert.equal(crossPage.reason, "cross_page");

  const inverted = parseExecRange("1.110-1.101");
  assert.equal(inverted.ok, false);
  assert.equal(inverted.reason, "range_order");

  const malformed = parseExecRange("101");
  assert.equal(malformed.ok, false);
  assert.equal(malformed.reason, "invalid_token");

  const huge = parseExecRange("1.1-1.900");
  assert.equal(huge.ok, false);
  assert.equal(huge.reason, "range_too_large");
});

test("formatExecRange compresses consecutive executors per page and round-trips", () => {
  assert.equal(formatExecRange([]), "");
  assert.equal(
    formatExecRange(["2.1", "1.103", "1.101", "1.102", "1.102", "1.108"]),
    "1.101-1.103, 1.108, 2.1",
  );
  const parsed = parseExecRange("1.101-1.110, 2.1, 2.5-2.7");
  assert.equal(formatExecRange(parsed.values), "1.101-1.110, 2.1, 2.5-2.7");
});
