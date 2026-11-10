// Every text pair under ui/src/texts: both languages present, the right script on each side, the same {names},
// all plural forms, and no character that neither font draws (arrows, dingbats, emoji).
import { describe, expect, it } from "vitest";
import type { PluralPair, TextPair } from "./types";

const modules = import.meta.glob<Record<string, unknown>>(["./**/*.ts", "!./**/*.test.ts"], { eager: true });

const ARABIC = /[؀-ۿݐ-ݿࢠ-ࣿﭐ-﷿ﹰ-﻿]/;
const FORBIDDEN = /[←-⇿✀-➿]|\p{Extended_Pictographic}/u;
const names = (value: string) => [...value.matchAll(/\{(\w+)\}/g)].map((m) => m[1]).sort();

const isRecord = (v: unknown): v is Record<string, unknown> => typeof v === "object" && v !== null;
const isPair = (v: unknown): v is TextPair => isRecord(v) && typeof v.en === "string" && typeof v.ar === "string";
const isPlural = (v: unknown): v is PluralPair => isRecord(v) && isRecord(v.en) && isRecord(v.ar);

type Entry = { where: string; en: string[]; ar: string[]; plural: boolean };

function collect(): Entry[] {
  const entries: Entry[] = [];
  for (const [file, exports] of Object.entries(modules)) {
    for (const [name, value] of Object.entries(exports)) {
      if (!isRecord(value) || typeof value === "function") continue;
      for (const [key, pair] of Object.entries(value)) {
        const where = `${file} ${name}.${key}`;
        if (isPair(pair)) entries.push({ where, en: [pair.en], ar: [pair.ar], plural: false });
        else if (isPlural(pair))
          entries.push({ where, en: Object.values(pair.en).map(String), ar: Object.values(pair.ar).map(String), plural: true });
      }
    }
  }
  return entries;
}

const entries = collect();

describe("texts", () => {
  it("finds the shared words", () => {
    expect(entries.some((e) => e.where.includes("common.close"))).toBe(true);
  });

  it.each(entries.map((e) => [e.where, e] as const))("%s", (_where, entry) => {
    for (const value of [...entry.en, ...entry.ar]) {
      expect(value.trim()).not.toBe("");
      expect(value).not.toMatch(FORBIDDEN);
    }
    for (const value of entry.ar) expect(value).toMatch(ARABIC);
    for (const value of entry.en) expect(value).not.toMatch(ARABIC);
    if (entry.plural) {
      expect(entry.en).toHaveLength(2);
      expect(entry.ar).toHaveLength(6);
    } else {
      expect(names(entry.ar[0]!)).toEqual(names(entry.en[0]!));
    }
  });
});
