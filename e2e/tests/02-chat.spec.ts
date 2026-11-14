import { expect, test } from '@playwright/test';
import { ask, byPrefix, MOCK, onboard, openChat, pick, shot, TID, trackErrors } from './helpers';

const QUESTION = 'How much did I spend on restaurants last month?';

test.describe('Chat with Sisu — streamed answer + generative UI widget', () => {
  test('restaurant spending question streams an answer and renders a widget', async ({ page }, testInfo) => {
    const errors = trackErrors(page);
    const sse: { status: number; contentType: string }[] = [];
    page.on('response', (r) => {
      if (r.url().includes('/api/chat') && r.request().method() === 'POST' && !r.url().includes('feedback')) {
        sse.push({ status: r.status(), contentType: r.headers()['content-type'] ?? '' });
      }
    });

    await onboard(page, testInfo, { persona: 'sisu' });
    await openChat(page);
    await expect(pick(page, TID.character('sisu'), page.getByLabel(/sisu/i))).toBeVisible();

    await pick(page, TID.chatInput, page.getByRole('textbox')).fill(QUESTION);
    await shot(page, testInfo, '08-chat-typed');

    const { text, partialLengths } = await ask(page, QUESTION, async () => {
      await shot(page, testInfo, '09-chat-streaming');
    });

    await test.step('answer is non-trivial and mentions euros', async () => {
      expect(text.length).toBeGreaterThan(20);
      expect.soft(text, 'answer should quote a € figure from tools').toMatch(/€|eur/i);
      expect(text).not.toMatch(/<think>|reasoning_content/);
    });

    await test.step('answer streamed in pieces (token events)', async () => {
      expect.soft(partialLengths, 'distinct partial lengths observed while streaming').toBeGreaterThan(1);
      if (!MOCK) {
        expect(sse.length, 'POST /api/chat was called').toBeGreaterThan(0);
        expect(sse[0].status).toBe(200);
        expect(sse[0].contentType).toContain('text/event-stream');
      }
    });

    await test.step('a generative-UI widget rendered inline', async () => {
      const widget = byPrefix(page, TID.widgetPrefix).first();
      await expect(widget).toBeVisible({ timeout: 30_000 });
      await widget.scrollIntoViewIfNeeded();
      const type = (await widget.getAttribute('data-testid'))?.slice(TID.widgetPrefix.length);
      testInfo.annotations.push({ type: 'widget', description: type ?? '?' });
      expect.soft(['bar_chart', 'kpi', 'line_chart', 'donut_chart', 'transaction_list', 'basket_breakdown']).toContain(type);
      await shot(page, testInfo, '10-chat-widget', widget);
    });

    await test.step('done event surfaced: suggestions + sources chip', async () => {
      await expect.soft(page.getByTestId(TID.suggestion).first(), 'suggestion chips').toBeVisible();
      expect.soft(await page.getByTestId(TID.suggestion).count(), 'SPEC: 3 suggestions').toBe(3);
      await expect.soft(page.getByTestId(TID.sources), 'sources chip').toContainText(/\d+/);
      await expect.soft(page.getByTestId(TID.feedbackUp), 'thumbs up').toBeVisible();
    });
    await shot(page, testInfo, '11-chat-answer');

    expect(errors, `uncaught page errors:\n${errors.join('\n')}`).toEqual([]);
  });
});
