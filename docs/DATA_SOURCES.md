# Data sources & reference content

This document explains where Rahakamu's reference data comes from, how each number was derived and how to rebuild it. Every figure the coach uses as a "national benchmark" traces back to an official open dataset. When a value is our own calculation rather than an official statistic, it is flagged `estimate: true` (or described as "derived") in the JSON and in this document.

| File | What it holds | Used by |
|---|---|---|
| `backend/app/data/benchmarks_fi.json` | Statistics Finland figures: household consumption by category and age (2022), median disposable income by age (2024), consumer price inflation (to Oct 2026), household saving rate (to 2026 Q2) | `app.analytics.benchmarks.benchmarks()` → the `stat_fi_monthly` field, the Insights tab, the agent's `benchmarks` tool |
| `backend/app/data/lessons.json` | 16 "Money Gym" micro-lessons (en + fi) with quizzes and unlock rules, plus a 26-term glossary | `GET /api/lessons`, the Learn tab, the agent's `explain_concept` tool, `lesson` widgets |
| `backend/app/data/mcc.json` | Brand-free labels, icons and the default three-basket assignment for every MCC in the dataset, null-MCC fallbacks per category, category and basket metadata | `app.analytics.baskets`, `merchant_label` / `mcc_label` / `icon` in the `Tx` shape, basket explanations |

All files were retrieved and checked on **2026-11-14**.

---

## 1. The hackathon dataset (private, never committed)

| File | Content |
|---|---|
| `data/transactions.parquet` | 3.6 M synthetic card and account transactions, 5 100 customers, 2024-10-01 … 2026-09-30 (converted from `tx_junction_transactions.csv`) |
| `data/tx_customers_junction.csv` | customer_id, postal code, age (18–90, median 44) |
| `data/mtg_*.csv` | 200 mortgage applications and their negotiation history |

The dataset is **synthetic** and was provided by S-Pankki for Junction 2026. Its spending levels are higher than the national averages (see the comparison table in §2.3). For that reason the app shows the dataset peer group (customers of the same age in the dataset) alongside the Statistics Finland figure. It never presents one as if it were the other.

---

## 2. Statistics Finland (Tilastokeskus): `benchmarks_fi.json`

**Licence:** CC BY 4.0. Attribution: *"Source: Statistics Finland"*. Data was pulled from the open **PxWeb API** at `https://pxdata.stat.fi/PxWeb/api/v1/en/StatFin/` (no key needed).

### 2.1 Tables used

| Topic | StatFin table | Latest period | Browser link |
|---|---|---|---|
| Household consumption expenditure by age of reference person (COICOP 2018) | `ktutk/14q4` | 2022 (latest survey round) | https://pxdata.stat.fi/PxWeb/pxweb/en/StatFin/StatFin__ktutk/14q4.px/ |
| Background information by age (household size, consumption units, disposable income) | `ktutk/14q9` | 2022 | https://pxdata.stat.fi/PxWeb/pxweb/en/StatFin/StatFin__ktutk/14q9.px/ |
| Income level of dwelling population by age (medians) | `tjt/14k5` | 2024 | https://pxdata.stat.fi/PxWeb/pxweb/en/StatFin/StatFin__tjt/14k5.px/ |
| Annual change of the consumer price index, yearly | `khi/122q` | 2025 | https://pxdata.stat.fi/PxWeb/pxweb/en/StatFin/StatFin__khi/122q.px/ |
| Annual change of the consumer price index, monthly | `khi/122p` | 2026M10 | https://pxdata.stat.fi/PxWeb/pxweb/en/StatFin/StatFin__khi/122p.px/ |
| Household saving rate and indebtedness (quarterly sector accounts, S14) | `ntp/15a8` | 2026Q2 | https://pxdata.stat.fi/PxWeb/pxweb/en/StatFin/StatFin__ntp/15a8.px/ |

Statistics overview pages: [Households' consumption](https://stat.fi/en/statistics/ktutk) · [Income distribution statistics](https://stat.fi/en/statistics/tjt) · [Consumer price index](https://stat.fi/en/statistics/khi) · [Quarterly sector accounts](https://stat.fi/en/statistics/sekn).

### 2.2 Method: "monthly per person"

The dataset has one account per customer, so we need a **per-person** benchmark. Statistics Finland publishes the series *"Consumption expenditure per consumption unit at current prices per month, EUR"* (`kulukk_kt_hk_2_1`). A **consumption unit** follows the modified OECD scale: the first adult counts as 1, every other person aged 14 or over as 0.5, and each child under 14 as 0.3. A one-person household therefore has exactly 1 consumption unit, and **the figure equals spending per person for someone living alone**. This is the official equivalisation, so we did not have to divide by an assumed household size ourselves.

* The values are **2022 euros**. Consumer prices then rose 6.2 % (2023), 1.6 % (2024) and 0.3 % (2025). Chaining these gives a factor of **1.0822**, stored as `inflation.cumulative_factor_2022_to_2025`. Use it only for an approximate 2025-price view; it is our derivation (`estimate: true`).
* Per-household monthly values (`kulukk_kt_hk_1_1`) are kept too, for transparency.
* Some cells are suppressed by Statistics Finland because the sample is too small. These are counted as 0 and listed in `suppressed_cells_counted_as_zero`. All of them are tiny sub-items, such as refuse collection for under-25s.
* **The 17–24 band rests on only 92 sampled households**, and the 85+ band on 78. Both carry `low_sample_warning: true` and should be called "indicative" in the UI.
* Age bands refer to the household's *reference person*. The lookup rule in the JSON (`age_band_rule`) maps a customer age to a band: under 25 → `17-24`, and so on.

### 2.3 Mapping dataset categories to COICOP 2018

The mapping below is **our interpretation**. Statistics Finland does not publish it. We aimed for each dataset category to cover the same kind of cash spending as the COICOP aggregate. The values are EUR per consumption unit per month, 2022.

| Dataset category | COICOP 2018 codes summed | Finland, all ages | Age 17-24 | Age 25-34 | Dataset median* |
|---|---|---:|---:|---:|---:|
| Groceries | 01 | 329 | 210 | 292 | 478 |
| Restaurants | 11.1 | 79 | 67 | 112 | 205 |
| Transportation | 07.2, 07.3.1, 07.3.2, 07.3.4, 07.3.5 | 165 | 89 | 152 | 211 |
| Utilities | 04.4.1, 04.4.2, 04.4.3, 04.5, 08.3 | 168 | 77 | 117 | 157 |
| Housing | 04.1, 04.4.4, 04.6.3 | 292 | 458 | 429 | 1000 |
| Entertainment | 09.4, 09.6 | 48 | 30 | 42 | 130 |
| Health | 06 | 86 | 45 | 46 | 97 |
| Home & Tech | 05, 08.1, 08.2 | 130 | 94 | 152 | 167 |
| Lifestyle | 03, 09.2, 09.7, 13.1, 13.2 | 187 | 159 | 228 | 170 |
| Travel | 07.3.3, 11.2, 09.8 | 43 | 29 | 37 | 79 |

\*Dataset median = for each customer with spending in the category, total outflow over the 24 months divided by 24, then the median across those customers. We computed it with DuckDB on `transactions.parquet` to put the national figures in context. It is not stored in the JSON, because the live peer statistics are computed by `benchmarks()`.

Notes on the mapping:

* **Transportation** leaves out 07.1 *purchase of vehicles* (the dataset has no car purchases) and 07.3.3 *air travel*, which goes to Travel.
* **Housing** = actual rent (04.1) + *other services related to the dwelling* (04.4.4) + *interest on housing loans* (04.6.3). We read 04.4.4 as covering items such as housing-company maintenance charges (*hoitovastike*). That reading is plausible but we have not confirmed it in the classification notes. **Imputed rent of owner-occupiers (04.2, 360 €/CU) is excluded**, because nobody actually pays it. Mortgage *principal* repayments are not consumption in national statistics, so they are not included either. This is why the dataset's housing payments, which include principal, look much higher.
* **Utilities** = water, refuse and sewage + electricity, gas and heating fuels (04.5) + phone and internet services (08.3).
* **Entertainment** 09.4 also contains games of chance and pet services. We kept it whole so the figure stays an official aggregate.
* Alcohol and tobacco (02), education (10), insurance and financial services (12) and social protection (13.3) have no dataset counterpart and are not mapped. Whole-economy totals are kept in `coicop_divisions_monthly_per_person_eur`.

### 2.4 Other key figures

**Total consumption expenditure (2022):** 2 363 € per consumption unit per month for all households (includes imputed rent), and 1 535 € when the reference person is 17–24. Sample size is 3 138 households, representing 2.92 M households.

**Median disposable income (2024, tjt/14k5)**, monthly = annual / 12:

| Age | Median disposable cash income per consumption unit €/mo | Median personal disposable income €/mo |
|---|---:|---:|
| all | 2 544 | 1 894 |
| 18+ | 2 573 | 2 217 |
| 18–24 | 1 960 | 1 098 |
| 25–34 | 2 531 | 2 266 |
| 35–49 | 2 756 | 2 768 |
| 50–64 | 3 095 | 2 641 |
| 65–74 | 2 435 | 1 871 |
| 75–84 | 2 255 | 1 829 |
| 85+ | 1 984 | 1 745 |

The income age bands (tjt) differ from the consumption age bands (ktutk). Both are stored as published, without re-banding.

**Inflation (CPI annual change):** 2021 2.2 % · 2022 7.1 % · 2023 6.2 % · 2024 1.6 % · 2025 0.3 %. Monthly: Oct 2025 −0.2 % … Sep 2026 2.5 %, **Oct 2026 3.1 %** (latest, published 2026-11-13).

**Household saving rate** (seasonally adjusted, % of disposable income): 2025 Q1 4.6 · Q2 7.1 · Q3 5.8 · Q4 6.1 · 2026 Q1 6.2 · **2026 Q2 4.3**. `average_2025_pct` = 5.9 is our simple mean of the four quarters (`estimate: true`). Household indebtedness rate, 2026 Q2: 117.9 % of disposable income. This is a macro, national-accounts figure, so it is not directly comparable with an individual's savings rate from bank data. The coach uses it only as context.

### 2.5 Reproducing the numbers

Every table is queried with a `POST` to `https://pxdata.stat.fi/PxWeb/api/v1/en/StatFin/<table>` and the response format `json-stat2`. The selections we used:

```jsonc
// ktutk/14q4.px: consumption by age
{"query":[
  {"code":"timeperiod_y","selection":{"filter":"item","values":["2022"]}},
  {"code":"coicop_46_20231201","selection":{"filter":"item","values":["0","01","03","041","0441","0442","0443","0444","045","0463","05","06","072","0731","0732","0733","0734","0735","081","082","083","092","094","096","097","098","111","112","131","132"]}},
  {"code":"ikaryhma_10_20180101","selection":{"filter":"item","values":["SSS","17-24","25-34","35-44","45-54","55-64","65-74","75-84","85-"]}},
  {"code":"contentscode","selection":{"filter":"item","values":["kulukk_kt_hk_2_1","kulukk_kt_hk_1_1"]}}],
 "response":{"format":"json-stat2"}}
// ktutk/14q9.px: contentscode pklkm_sum, oklkm_sum, jlkm_mean, oecdmod_mean, Kaytetmk_1_mean (same year/age)
// tjt/14k5.px: timeperiod_y 2024, tuloluokka SSS, sukupuoli SSS, koulutusaste SSS, contentscode tjt-ekvikturaha_med, hkturaha_med, tjt-henkiloita
// khi/122q.px: timeperiod_y 2021..2025  ·  khi/122p.px: timeperiod_m 2025M10..2026M10  (contentscode Vuosimuutos)
// ntp/15a8.px: sektoriluokitus S14, contentscode ntp-kausit_b8n (saving rate), ntp-kausit_f4 (indebtedness)
```

Quick check from the shell:

```bash
curl -s https://pxdata.stat.fi/PxWeb/api/v1/en/StatFin/ktutk/14q4.px | jq '.variables[].code'
```

---

## 3. Money Gym content: `lessons.json`

The lessons are original text written for Rahakamu, in plain English and Finnish (120–200 words in English, with Finnish of equivalent length). Each lesson has `unlock_rule`, a rule the app can read that ties it to the user's own data (for example `leak_share > 0.30` unlocks *50/30/20 — the three-basket way*), plus a human-readable `unlock_hint`. Investing content is **general education, not advice**, and points to S-Bank's advisors.

Finnish rules and figures in the lessons were checked on 2026-11-14:

| Fact used | Source |
|---|---|
| CPI: 7.1 % (2022), 6.2 % (2023), 1.6 % (2024), 0.3 % (2025), 3.1 % (Oct 2026) | Statistics Finland `khi/122q`, `khi/122p` (above) |
| Household spending 2022: groceries 329 €, restaurants 79 €; age 17–24 groceries 210 €, restaurants 67 €, rent 442 € per CU/month | Statistics Finland `ktutk/14q4` (above) |
| ASP reform in force **1 June 2026**: monthly deposits 50–1 500 €, at least 20 deposits, upper age limit 44 removed (saving can start at 15), own savings ≥ 10 % of the price, interest ≥ 1 % tax-free, state bonus interest 2–4 %, ASP-loan regional limits 230 000 € / 160 000 € (one borrower) | [Finnish Government press release 13 May 2026](https://valtioneuvosto.fi/-/1410903/asp-korkotukilainan-enimmaismaarat-nousevat-ja-alueelliset-rajat-selkeytyvat) · [Taloustaito 20 Oct 2025](https://www.taloustaito.fi/koti/2025/ensiasuntoa-saastavan-uusi-asp-on-aiempaa-joustavampi/). A cut of the own-savings share to 5 % has been proposed for 2027 but is not law, so the lesson notes that terms can change. |
| Loan cap: first-home buyers can borrow up to 95 % (FIN-FSA also raised the cap for other buyers to 95 % in June 2026) | [FIN-FSA release](https://www.sttinfo.fi/announcement/72171635?publisherId=69817444) · [Taloustaito 2026](https://www.taloustaito.fi/koti/2026/asuntolainaa-pienemmilla-saastoilla--lainakatto-nousee-95-prosenttiin/) |
| Transfer tax 1.5 % on housing-company shares (3 % on real estate); first-home exemption abolished from 1 Jan 2024 | [vero.fi: first-home transfer tax exemption](https://www.vero.fi/syventavat-vero-ohjeet/ohje-hakusivu/79875/ensiasunnon-varainsiirtoverovapaus4/) |
| Consumer-credit interest cap: 15 % + reference rate (max 20 %), other credit costs ≤ 150 €/year | [Finnish Competition and Consumer Authority (KKV)](https://www.kkv.fi/en/consumer-affairs/credit-and-payments/credit/price-of-credit/) |
| Positive credit register in use since 2024 (consumer credit from 1 Feb 2024) | [vero.fi: positive credit register](https://www.vero.fi/positiivinenluottotietorekisteri/) |
| Deposit guarantee 100 000 € per depositor per bank | [Finance Finland](https://www.finanssiala.fi/en/topics/deposit-guarantee-in-finland/) · [Financial Stability Authority](https://rvv.fi/en/deposit-guarantee) |
| Equity savings account (osakesäästötili): deposit cap 100 000 € since 2024; tax only on withdrawn gains | [vero.fi](https://vero.fi/henkiloasiakkaat/omaisuus/sijoitukset/osakes%C3%A4%C3%A4st%C3%B6tili/) · [Veronmaksajat](https://www.veronmaksajat.fi/neuvot/henkiloverotus/sijoittaminen/osakesaastotili/osakesaastotili-ja-verot/) |
| 60 % withholding when no tax card is given | Finnish Tax Administration, tax card guidance ([vero.fi](https://www.vero.fi/henkiloasiakkaat/verokortti-ja-veroilmoitus/)) |

**Illustrative calculations** (our arithmetic, clearly marked as assumptions in the text):

* 100 €/month at 5 %/yr compounded monthly gives ≈ 15 528 € (10 y), 41 103 € (20 y) and 83 226 € (30 y).
* A 4.50 € coffee × 5 days × 52 weeks ≈ 1 170 €/yr.
* 600 € over 12 months at 15 % APR ≈ 54.15 €/month.
* 50/30/20, the 24-hour rule and the 1–3 month emergency fund are presented as **rules of thumb**, not as regulations.

---

## 4. Merchant categories: `mcc.json`

* Codes are ISO 18245 Merchant Category Codes as found in the dataset. There are 36 distinct codes, every one is covered, and each sits under the dataset category it appears with. Labels are **simplified and brand-free**, written by us. `merchant_label` = `short_label_en` + merchant number, for example `MRC-RES-0042` + 5812 → "Restaurant #42". Real brand names are never used.
* `default_basket` follows SPEC §2 exactly. Two amount rules are encoded as `irregular_over_eur`: fuel and parking over **80 €** (MCC 5541, 5542, 7523, and null-MCC Transportation), and electronics, software and furniture over **150 €** (5732, 5734, 5712, and null-MCC Home & Tech) become *irregular*. Health is always irregular; Home & Tech 5200 and 5251 are irregular. Recurring-payment detection in `app.analytics.baskets` / `recurring.py` can still promote a payment to *fixed*.
* `null_mcc` gives the fallback for every category with null MCC rows, including Housing, Utilities and the income and saving flows.
* `baskets` holds the five flow types with their colours (SPEC §5.4) and a short `why` text in English and Finnish, used for the tap-to-explain on the basket meter.

---

## 5. Keeping it fresh

* The **household budget survey** runs every few years. When a new round is published, add its year to the `timeperiod_y` selection. The table codes and the COICOP 2018 mapping should stay stable.
* **CPI** updates monthly (mid-month), **income statistics** yearly (December) and **sector accounts** quarterly. Rerun the queries in §2.5 and bump `meta.retrieved`.
* **ASP and loan-cap rules** have changes planned for 2027. Re-check the sources in §3 before each release.
