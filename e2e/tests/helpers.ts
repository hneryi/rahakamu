import { expect, type Locator, type Page, type TestInfo } from '@playwright/test';
import * as fs from 'node:fs';
import * as path from 'node:path';

/**
 * testID contract between the app and these tests. react-native-web renders `testID` as
 * `data-testid`, so `page.getByTestId()` works. Every lookup also has an accessibility/text
 * fallback so the suite degrades gracefully while the app is still being built.
 */
export const TID = {
  // onboarding
  onboarding: 'onboarding-screen',
  customerOption: (id: string) => `customer-option-${id}`,
  personaOption: (p: Persona) => `persona-option-${p}`,
  onboardingContinue: 'onboarding-continue',
  // home
  home: 'home-screen',
  greeting: 'home-greeting',
  settingsButton: 'settings-button',
  balanceCard: 'balance-card',
  balanceAmount: 'balance-amount',
  safeCard: 'safe-to-spend-card',
  safeAmount: 'safe-to-spend-amount',
  goalCarousel: 'goal-carousel',
  goalCardPrefix: 'goal-card-',
  basketMeter: 'basket-meter',
  basketSegment: (b: 'fixed' | 'irregular' | 'leak') => `basket-segment-${b}`,
  recentTx: 'recent-transactions',
  txRowPrefix: 'tx-row-',
  dock: 'character-dock',
  character: (p: Persona) => `character-${p}`,
  nudgeBubble: 'nudge-bubble',
  dockComposer: 'dock-composer',
  micButton: 'mic-button',
  cameraButton: 'camera-button',
  tab: (t: 'home' | 'insights' | 'goals' | 'learn') => `tab-${t}`,
  // chat
  chat: 'chat-screen',
  chatInput: 'chat-input',
  chatSend: 'chat-send',
  chatStatus: 'chat-status',
  msgUser: 'message-user',
  msgAssistant: 'message-assistant',
  widgetPrefix: 'widget-',
  suggestion: 'suggestion-chip',
  sources: 'sources-chip',
  feedbackUp: 'feedback-up',
  chatClose: 'chat-close',
  // settings
  settings: 'settings-screen',
  settingsPersona: (p: Persona) => `settings-persona-${p}`,
  settingsLocale: (l: 'en' | 'fi') => `settings-locale-${l}`,
  settingsBack: 'settings-back',
} as const;

export type Persona = 'sisu' | 'aava';

export const DEMO_CUSTOMER = process.env.E2E_CUSTOMER ?? 'CUST05020'; // "Emma, 21"
export const DEMO_NAME = process.env.E2E_CUSTOMER_NAME ?? 'Emma';
export const MOCK = !!process.env.E2E_MOCK;

const SHOT_DIR = path.resolve(__dirname, '..', 'screenshots');
fs.mkdirSync(SHOT_DIR, { recursive: true });

/** Euro amount as rendered by the app: "1 234,56 €", "€1,234.56", "23 €", "-12.50 €" … */
export const EURO = /(€\s?-?[\d\s.,  ]+\d|-?[\d\s.,  ]*\d\s?€)/;

/** testID first, then fallbacks (accessible role/name or text). Returns the first visible match. */
export function pick(page: Page | Locator, testId: string, ...fallbacks: Locator[]): Locator {
  let loc = page.getByTestId(testId);
  for (const f of fallbacks) loc = loc.or(f);
  return loc.first();
}

export function byPrefix(scope: Page | Locator, prefix: string): Locator {
  return scope.locator(`[data-testid^="${prefix}"]`);
}

/** Save a README-quality screenshot to e2e/screenshots/<name>.png and attach it to the report. */
export async function shot(page: Page, testInfo: TestInfo, name: string, target?: Locator) {
  await page.waitForTimeout(400); // let springs/animations settle
  const file = path.join(SHOT_DIR, `${name}.png`);
  const buf = target
    ? await target.screenshot({ path: file, animations: 'disabled' })
    : await page.screenshot({ path: file, animations: 'disabled' });
  await testInfo.attach(name, { body: buf, contentType: 'image/png' });
}

/** Collect uncaught page errors (React crashes etc.) so a test can assert there were none. */
export function trackErrors(page: Page): string[] {
  const errors: string[] = [];
  page.on('pageerror', (e) => errors.push(e.message));
  return errors;
}

async function visible(loc: Locator, timeout = 1_500): Promise<boolean> {
  try {
    await loc.waitFor({ state: 'visible', timeout });
    return true;
  } catch {
    return false;
  }
}

/** Fresh context → app should land on onboarding. Picks customer + persona and lands on home. */
export async function onboard(page: Page, testInfo: TestInfo | null, opts: { persona: Persona; customer?: string; shots?: boolean }) {
  const customer = opts.customer ?? DEMO_CUSTOMER;
  const snap = async (n: string) => {
    if (opts.shots && testInfo) await shot(page, testInfo, n);
  };

  await page.goto('/');
  const onboarding = pick(page, TID.onboarding);
  const home = pick(page, TID.home);
  await expect(onboarding.or(home).first()).toBeVisible({ timeout: 120_000 });
  if (!(await visible(onboarding, 500))) {
    // already onboarded (persisted state) or app doesn't auto-redirect → go explicitly
    await page.goto('/onboarding');
    await expect(onboarding).toBeVisible();
  }
  await snap('01-onboarding');

  // step 1: customer
  const custOpt = pick(page, TID.customerOption(customer), page.getByRole('button', { name: new RegExp(DEMO_NAME, 'i') }));
  await custOpt.click();
  await snap('02-onboarding-customer');

  // optional "continue" between steps
  const persona = pick(page, TID.personaOption(opts.persona), page.getByRole('button', { name: new RegExp(opts.persona, 'i') }));
  const cont = pick(page, TID.onboardingContinue, page.getByRole('button', { name: /continue|next|jatka|seuraava/i }));
  if (!(await visible(persona, 1_500)) && (await visible(cont, 1_000))) await cont.click();

  // step 2: character
  await persona.click();
  await snap(`03-onboarding-${opts.persona}`);
  if (!(await visible(home, 1_500))) {
    await cont.click(); // "Start training" / "Let's go" / "Aloitetaan"
  }
  await expect(home).toBeVisible({ timeout: 60_000 });
}

/** Navigate to the full-screen chat from the home dock (falls back to /chat). */
export async function openChat(page: Page) {
  const chat = pick(page, TID.chat);
  const dock = pick(page, TID.dockComposer, page.getByPlaceholder(/ask|kysy/i), page.getByRole('button', { name: /ask|kysy/i }));
  if (await visible(dock, 3_000)) await dock.click();
  if (!(await visible(chat, 5_000))) await page.goto('/chat');
  await expect(chat).toBeVisible();
}

export function chatInput(page: Page) {
  return pick(page, TID.chatInput, page.getByRole('textbox'));
}

/**
 * Types a question, sends it and waits for the streamed answer to finish.
 * Returns the assistant text plus how many distinct partial lengths we observed while streaming.
 */
export async function ask(page: Page, question: string, onStreaming?: () => Promise<void>) {
  const input = chatInput(page);
  await input.fill(question);
  const assistantBefore = await page.getByTestId(TID.msgAssistant).count();
  const send = pick(page, TID.chatSend, page.getByRole('button', { name: /send|lähetä/i }));
  if (await visible(send, 1_000)) await send.click();
  else await input.press('Enter');

  await expect(page.getByTestId(TID.msgUser).or(page.getByText(question, { exact: true })).last()).toBeVisible();

  const answer = page.getByTestId(TID.msgAssistant).nth(assistantBefore);
  await expect(answer).toBeVisible({ timeout: 120_000 });

  // sample the growing text to prove token streaming
  const lengths = new Set<number>();
  let shotTaken = false;
  const doneMarker = pick(page, TID.suggestion).or(page.getByTestId(TID.sources)).first();
  const deadline = Date.now() + 150_000;
  while (Date.now() < deadline) {
    const t = ((await answer.textContent().catch(() => '')) ?? '').trim();
    if (t.length) lengths.add(t.length);
    if (!shotTaken && t.length > 0 && onStreaming) {
      shotTaken = true;
      await onStreaming();
    }
    if (await doneMarker.isVisible().catch(() => false)) break;
    await page.waitForTimeout(120);
  }
  const text = ((await answer.textContent()) ?? '').trim();
  return { text, partialLengths: lengths.size, answer };
}
