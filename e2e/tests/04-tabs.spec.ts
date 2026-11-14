import { expect, test } from '@playwright/test';
import { onboard, pick, shot, TID, trackErrors } from './helpers';

// README gallery: the other tabs. Soft: a missing tab is reported, not fatal.
test('tab bar: Insights, Goals, Learn render', async ({ page }, testInfo) => {
  const errors = trackErrors(page);
  await onboard(page, testInfo, { persona: 'aava' });

  const tabs = [
    { id: 'insights', name: /insights|oivallukset|näkymät|data/i, shot: '17-insights' },
    { id: 'goals', name: /goals|tavoitteet/i, shot: '18-goals' },
    { id: 'learn', name: /learn|money gym|opi|treeni/i, shot: '19-learn' },
  ] as const;

  for (const t of tabs) {
    await test.step(`tab ${t.id}`, async () => {
      const tab = pick(page, TID.tab(t.id), page.getByRole('tab', { name: t.name }), page.getByRole('link', { name: t.name }));
      if (!(await tab.isVisible().catch(() => false))) {
        await page.goto(`/${t.id}`);
      } else {
        await tab.click();
      }
      await expect.soft(page.getByTestId(`${t.id}-screen`), `${t.id}-screen testID`).toBeVisible();
      await page.waitForLoadState('networkidle').catch(() => {});
      await shot(page, testInfo, t.shot);
    });
  }

  await pick(page, TID.tab('home'), page.getByRole('tab', { name: /home|koti/i })).click().catch(() => page.goto('/'));
  await expect(pick(page, TID.home)).toBeVisible();
  expect(errors, errors.join('\n')).toEqual([]);
});
