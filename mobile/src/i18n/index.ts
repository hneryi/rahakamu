/**
 * Tiny i18n layer (no dependency): `useT()` returns a typed translator bound to
 * the session locale, plus locale-aware money/date formatters.
 *
 * Why not i18next: three languages, flat keys and compile-time key checking are
 * all we need; this keeps the bundle small for the S-mobiili WebView embed.
 * `fi.ts` and `sv.ts` are typed as `Record<TKey, string>`, so a missing key is a
 * compile error.
 *
 * Numbers for fi / sv are formatted by hand ("1 234,56 €" with non-breaking
 * spaces) instead of Intl: Hermes and browsers disagree on separators, and the
 * output must be identical on every platform and never wrap mid-amount.
 */
import { useCallback, useMemo } from 'react';

import type { Locale } from '@/api/types';
import { useSession } from '@/store/session';
import en, { type TKey } from './en';
import fi from './fi';
import sv from './sv';

export type { TKey };

const dictionaries: Record<Locale, Record<TKey, string>> = { en, fi, sv };

export const LOCALES: Locale[] = ['fi', 'en', 'sv'];
/** Native names for the language switch (never translated). */
export const LOCALE_NAMES: Record<Locale, string> = { fi: 'Suomi', en: 'English', sv: 'Svenska' };

export type Vars = Record<string, string | number>;

export function translate(locale: Locale, key: TKey, vars?: Vars): string {
  const raw = dictionaries[locale]?.[key] ?? en[key] ?? key;
  if (!vars) return raw;
  return raw.replace(/\{(\w+)\}/g, (_, k: string) => (vars[k] !== undefined ? String(vars[k]) : `{${k}}`));
}

const NBSP = '\u00A0';
const nordic = (l: Locale) => l === 'fi' || l === 'sv';

/** fi / sv number: NBSP thousands, comma decimals, true minus sign. */
function nordicNumber(v: number, minDigits: number, maxDigits: number): string {
  let s = Math.abs(v).toFixed(maxDigits);
  if (maxDigits > minDigits && s.includes('.')) s = s.replace(new RegExp(`0{1,${maxDigits - minDigits}}$`), '').replace(/\.$/, '');
  const [int, dec] = s.split('.');
  const body = int.replace(/\B(?=(\d{3})+(?!\d))/g, NBSP) + (dec ? `,${dec}` : '');
  return v < 0 && Number(s) !== 0 ? `−${body}` : body;
}

const enFormatters = new Map<string, Intl.NumberFormat>();
function enFmt(min: number, max: number, currency: boolean): Intl.NumberFormat {
  const key = `${min}-${max}-${currency}`;
  let f = enFormatters.get(key);
  if (!f) {
    f = new Intl.NumberFormat('en-IE', currency ? { style: 'currency', currency: 'EUR', minimumFractionDigits: min, maximumFractionDigits: max } : { minimumFractionDigits: min, maximumFractionDigits: max });
    enFormatters.set(key, f);
  }
  return f;
}

/** Money: 2 decimals under 100 €, whole euros above (mobile readability). fi/sv: "1 234 €", en: "€1,234". */
export function formatMoney(locale: Locale, value: number, opts: { decimals?: number; sign?: boolean } = {}): string {
  const v = Number.isFinite(value) ? value : 0;
  const decimals = opts.decimals ?? (Math.abs(v) >= 100 ? 0 : 2);
  const s = nordic(locale) ? `${nordicNumber(Math.abs(v), decimals, decimals)}${NBSP}€` : enFmt(decimals, decimals, true).format(Math.abs(v));
  if (v < 0) return `−${s}`;
  return opts.sign && v > 0 ? `+${s}` : s;
}

export function formatNumber(locale: Locale, v: number, digits = 0): string {
  return nordic(locale) ? nordicNumber(v, 0, digits) : enFmt(0, digits, false).format(v);
}

/** Compact money for chart labels: 1,2k / 1.2k. */
export function formatCompact(locale: Locale, value: number): string {
  const abs = Math.abs(value);
  if (abs >= 1000) return `${formatNumber(locale, value / 1000, abs >= 10000 ? 0 : 1)}k`;
  return formatNumber(locale, Math.round(value));
}

export function formatPct(locale: Locale, ratio: number, digits = 0): string {
  const n = formatNumber(locale, ratio * 100, digits);
  return nordic(locale) ? `${n}${NBSP}%` : `${n}%`;
}

const MONTHS: Record<Locale, { short: string[]; long: string[] }> = {
  en: {
    short: ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'],
    long: ['January', 'February', 'March', 'April', 'May', 'June', 'July', 'August', 'September', 'October', 'November', 'December'],
  },
  fi: {
    short: ['tammi', 'helmi', 'maalis', 'huhti', 'touko', 'kesä', 'heinä', 'elo', 'syys', 'loka', 'marras', 'joulu'],
    long: ['tammikuu', 'helmikuu', 'maaliskuu', 'huhtikuu', 'toukokuu', 'kesäkuu', 'heinäkuu', 'elokuu', 'syyskuu', 'lokakuu', 'marraskuu', 'joulukuu'],
  },
  sv: {
    short: ['jan', 'feb', 'mars', 'apr', 'maj', 'juni', 'juli', 'aug', 'sep', 'okt', 'nov', 'dec'],
    long: ['januari', 'februari', 'mars', 'april', 'maj', 'juni', 'juli', 'augusti', 'september', 'oktober', 'november', 'december'],
  },
};

/** "2026-09" → "Sep" / "syys" / "sep" (explicit tables: Hermes' Intl month names vary by platform). */
export function monthShort(locale: Locale, ym: string): string {
  const m = Number(ym.slice(5, 7)) - 1;
  return MONTHS[locale].short[m] ?? ym;
}

export function monthLong(locale: Locale, ym: string): string {
  const y = ym.slice(0, 4);
  const m = Number(ym.slice(5, 7)) - 1;
  const name = MONTHS[locale].long[m];
  return name ? `${name} ${y}` : ym;
}

/** "2026-09-17" → "17 Sep" (en) / "17.9." (fi, sv: Finland uses day.month. in both languages). */
export function formatDate(locale: Locale, isoDate: string | null | undefined, withYear = false): string {
  if (!isoDate) return '';
  const [y, m, d] = isoDate.slice(0, 10).split('-').map(Number);
  if (!y || !m || !d) return isoDate;
  if (nordic(locale)) return withYear ? `${d}.${m}.${y}` : `${d}.${m}.`;
  return withYear ? `${d} ${MONTHS.en.short[m - 1]} ${y}` : `${d} ${MONTHS.en.short[m - 1]}`;
}

export function useLocale(): Locale {
  return useSession((s) => s.locale);
}

export function useT() {
  const locale = useLocale();
  const t = useCallback((key: TKey, vars?: Vars) => translate(locale, key, vars), [locale]);
  return useMemo(
    () => ({
      t,
      locale,
      money: (v: number, opts?: { decimals?: number; sign?: boolean }) => formatMoney(locale, v, opts),
      compact: (v: number) => formatCompact(locale, v),
      pct: (ratio: number, digits?: number) => formatPct(locale, ratio, digits),
      num: (v: number, digits?: number) => formatNumber(locale, v, digits),
      date: (d: string | null | undefined, withYear?: boolean) => formatDate(locale, d, withYear),
      month: (ym: string) => monthShort(locale, ym),
      monthLong: (ym: string) => monthLong(locale, ym),
    }),
    [locale, t],
  );
}
