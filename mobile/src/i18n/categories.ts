/**
 * Display names for the raw category keys of the dataset.
 *
 * Most API payloads already carry a localized `label`. A few (benchmark rows,
 * recurring payments) only carry the raw key, so the app localizes those here
 * with the same wording the backend uses elsewhere.
 */
import type { Locale } from '@/api/types';

const CATEGORY: Record<Locale, Record<string, string>> = {
  en: {
    Housing: 'Rent & housing',
    Groceries: 'Groceries',
    Restaurants: 'Restaurants & cafés',
    Entertainment: 'Entertainment',
    Transportation: 'Transport',
    Lifestyle: 'Shopping & lifestyle',
    'Home & Tech': 'Home & tech',
    Health: 'Health',
    Travel: 'Travel',
    Utilities: 'Utilities & bills',
    Salary: 'Salary',
    'Other Income': 'Other income',
    'Salary Sweep': 'Savings transfer',
    'Invest Deposit': 'Investment deposit',
    'Invest Withdraw': 'Investment withdrawal',
  },
  fi: {
    Housing: 'Vuokra ja asuminen',
    Groceries: 'Ruokaostokset',
    Restaurants: 'Ravintolat ja kahvilat',
    Entertainment: 'Viihde',
    Transportation: 'Liikkuminen',
    Lifestyle: 'Ostokset ja vapaa-aika',
    'Home & Tech': 'Koti ja tekniikka',
    Health: 'Terveys',
    Travel: 'Matkailu',
    Utilities: 'Asumisen laskut',
    Salary: 'Palkka',
    'Other Income': 'Muut tulot',
    'Salary Sweep': 'Säästösiirto',
    'Invest Deposit': 'Sijoitustalletus',
    'Invest Withdraw': 'Sijoitusnosto',
  },
  sv: {
    Housing: 'Hyra och boende',
    Groceries: 'Matinköp',
    Restaurants: 'Restauranger och kaféer',
    Entertainment: 'Nöjen',
    Transportation: 'Transport',
    Lifestyle: 'Shopping och fritid',
    'Home & Tech': 'Hem och teknik',
    Health: 'Hälsa',
    Travel: 'Resor',
    Utilities: 'Boenderäkningar',
    Salary: 'Lön',
    'Other Income': 'Övriga inkomster',
    'Salary Sweep': 'Sparöverföring',
    'Invest Deposit': 'Investeringsinsättning',
    'Invest Withdraw': 'Investeringsuttag',
  },
};

const CADENCE: Record<Locale, Record<string, string>> = {
  en: { weekly: 'weekly', biweekly: 'every 2 weeks', monthly: 'monthly', quarterly: 'quarterly', yearly: 'yearly', annual: 'yearly' },
  fi: { weekly: 'viikoittain', biweekly: 'joka toinen viikko', monthly: 'kuukausittain', quarterly: 'neljännesvuosittain', yearly: 'vuosittain', annual: 'vuosittain' },
  sv: { weekly: 'varje vecka', biweekly: 'varannan vecka', monthly: 'varje månad', quarterly: 'varje kvartal', yearly: 'varje år', annual: 'varje år' },
};

/** Localized name for a raw category key; unknown keys are shown as they are. */
export function categoryLabel(locale: Locale, key: string | null | undefined): string {
  if (!key) return '';
  return CATEGORY[locale]?.[key] ?? key;
}

/** Localized name for a recurring-payment cadence; unknown values are shown as they are. */
export function cadenceLabel(locale: Locale, cadence: string | null | undefined): string {
  if (!cadence) return '';
  return CADENCE[locale]?.[cadence.toLowerCase()] ?? cadence;
}
