import { expect, test } from '@playwright/test';
import { byPrefix, DEMO_NAME, EURO, onboard, pick, shot, TID, trackErrors } from './helpers';

test.describe('Onboarding → home (Sisu)', () => {
  test('pick customer + Sisu, home shows money status and the character dock', async ({ page }, testInfo) => {
    const errors = trackErrors(page);

    await test.step('onboarding: choose demo customer and Sisu', async () => {
      await onboard(page, testInfo, { persona: 'sisu', shots: true });
    });

    await test.step('greeting names the customer', async () => {
      const greeting = pick(page, TID.greeting, page.getByText(new RegExp(`(Hei|Hi|Hello|Moi)\\s+${DEMO_NAME}`, 'i')));
      await expect(greeting).toBeVisible();
      await expect(greeting).toContainText(DEMO_NAME);
    });

    await test.step('balance card shows a euro balance', async () => {
      const card = pick(page, TID.balanceCard);
      await expect(card).toBeVisible();
      await expect(pick(page, TID.balanceAmount, card)).toHaveText(EURO);
    });

    await test.step('safe-to-spend card shows an amount', async () => {
      const card = pick(page, TID.safeCard, page.getByText(/safe to spend|turvallisesti/i));
      await expect(card).toBeVisible();
      await expect(pick(page, TID.safeAmount, card)).toHaveText(EURO);
    });
    await shot(page, testInfo, '04-home-top');

    await test.step('goal carousel has at least one goal (2 seeded per demo customer)', async () => {
      const carousel = pick(page, TID.goalCarousel);
      await carousel.scrollIntoViewIfNeeded();
      await expect(carousel).toBeVisible();
      await expect(byPrefix(carousel, TID.goalCardPrefix).first()).toBeVisible();
      expect.soft(await byPrefix(carousel, TID.goalCardPrefix).count(), 'seeded goals').toBeGreaterThanOrEqual(2);
    });

    await test.step('basket meter shows the three baskets', async () => {
      const meter = pick(page, TID.basketMeter);
      await meter.scrollIntoViewIfNeeded();
      await expect(meter).toBeVisible();
      for (const b of ['fixed', 'irregular', 'leak'] as const) {
        await expect.soft(page.getByTestId(TID.basketSegment(b)), `basket segment ${b}`).toHaveCount(1);
      }
      await shot(page, testInfo, '05-home-baskets');
    });

    await test.step('recent transactions list has rows', async () => {
      const list = pick(page, TID.recentTx);
      await list.scrollIntoViewIfNeeded();
      await expect(list).toBeVisible();
      const rows = byPrefix(list, TID.txRowPrefix);
      await expect(rows.first()).toBeVisible();
      expect.soft(await rows.count(), 'recent transactions (SPEC: 8)').toBe(8);
      await expect(rows.first()).toContainText(EURO);
      await shot(page, testInfo, '06-home-transactions');
    });

    await test.step('character dock: Sisu + nudge bubble + composer', async () => {
      const dock = pick(page, TID.dock);
      await expect(dock).toBeVisible();
      await expect(pick(dock, TID.character('sisu'), page.getByLabel(/sisu/i))).toBeVisible();
      await expect(pick(dock, TID.dockComposer, page.getByText(/ask sisu|kysy sisulta/i))).toBeVisible();
      await expect.soft(page.getByTestId(TID.nudgeBubble), 'nudge bubble').toBeVisible();
      await expect.soft(page.getByTestId(TID.micButton), 'mic button').toBeVisible();
      await expect.soft(page.getByTestId(TID.cameraButton), 'camera button').toBeVisible();
      await shot(page, testInfo, '07-home-dock', dock);
    });

    await test.step('layout fits a 390 px phone (no horizontal scroll)', async () => {
      const overflow = await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
      expect.soft(overflow, 'horizontal overflow in px').toBeLessThanOrEqual(1);
    });

    expect(errors, `uncaught page errors:\n${errors.join('\n')}`).toEqual([]);
  });
});
