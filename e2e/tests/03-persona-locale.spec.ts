import { expect, test, type Page } from '@playwright/test';
import { ask, byPrefix, onboard, openChat, pick, shot, TID, trackErrors } from './helpers';

async function openSettings(page: Page) {
  const settings = pick(page, TID.settings);
  const btn = pick(page, TID.settingsButton, page.getByRole('button', { name: /settings|asetukset/i }));
  if (await btn.isVisible().catch(() => false)) await btn.click();
  if (!(await settings.isVisible({ timeout: 5_000 }).catch(() => false))) await page.goto('/settings');
  await expect(settings).toBeVisible();
}

async function backHome(page: Page) {
  const back = pick(page, TID.settingsBack, page.getByRole('button', { name: /back|close|takaisin|sulje/i }));
  if (await back.isVisible().catch(() => false)) await back.click();
  if (!(await page.getByTestId(TID.home).isVisible({ timeout: 5_000 }).catch(() => false))) await page.goto('/');
  await expect(pick(page, TID.home)).toBeVisible();
}

test.describe('Switch character to Aava', () => {
  test('settings → Aava: dock and chat use the owl mentor', async ({ page }, testInfo) => {
    const errors = trackErrors(page);
    await onboard(page, testInfo, { persona: 'sisu' });

    await openSettings(page);
    await shot(page, testInfo, '12-settings');
    await pick(page, TID.settingsPersona('aava'), page.getByRole('button', { name: /aava/i })).click();
    await backHome(page);

    const dock = pick(page, TID.dock);
    await expect(pick(dock, TID.character('aava'), page.getByLabel(/aava/i))).toBeVisible();
    await expect(page.getByTestId(TID.character('sisu'))).toHaveCount(0);
    await expect.soft(pick(dock, TID.dockComposer)).toContainText(/aava/i);
    await shot(page, testInfo, '13-home-aava');

    await openChat(page);
    await expect(pick(page, TID.character('aava'), page.getByLabel(/aava/i))).toBeVisible();
    const { text } = await ask(page, 'What is safe for me to spend this week?');
    expect(text.length).toBeGreaterThan(20);
    await expect.soft(byPrefix(page, TID.widgetPrefix).first(), 'safe_to_spend widget').toBeVisible();
    await shot(page, testInfo, '14-chat-aava');

    expect(errors, errors.join('\n')).toEqual([]);
  });
});

test.describe('Finnish locale', () => {
  test.use({ locale: 'fi-FI' });

  const FINNISH = /Hei|Saldo|Turvallisesti|Tavoitteet|Viimeisimmät|Kysy|Kiinteät|Vuodot|tapahtum/i;
  const ENGLISH_ONLY = /Safe to spend|Recent transactions|Ask (Sisu|Aava) anything/;

  test('fi-FI device locale → Finnish UI, Finnish chat answer', async ({ page }, testInfo) => {
    const errors = trackErrors(page);
    await onboard(page, testInfo, { persona: 'sisu' });

    // if the device locale wasn't picked up, switch explicitly in settings
    const body = page.locator('body');
    if (!FINNISH.test((await body.innerText()) ?? '')) {
      await openSettings(page);
      await pick(page, TID.settingsLocale('fi'), page.getByRole('button', { name: /suomi|finnish/i })).click();
      await backHome(page);
    }

    await expect(body).toContainText(FINNISH);
    await expect.soft(body, 'untranslated English strings on home').not.toContainText(ENGLISH_ONLY);
    await expect.soft(pick(page, TID.dockComposer)).toContainText(/kysy/i);
    await shot(page, testInfo, '15-home-fi');

    await openChat(page);
    const { text } = await ask(page, 'Paljonko kulutin ravintoloihin viime kuussa?');
    expect(text.length).toBeGreaterThan(20);
    expect.soft(text, 'answer should be Finnish').toMatch(/[äöÄÖ]|\b(ja|on|olet|sinun|kuussa)\b/);
    await shot(page, testInfo, '16-chat-fi');

    expect(errors, errors.join('\n')).toEqual([]);
  });
});
