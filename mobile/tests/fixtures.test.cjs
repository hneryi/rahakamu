#!/usr/bin/env node
/**
 * Persistent offline regression test for the Joni demo customer (CUST05014).
 *
 * No test runner or new dependency: TypeScript is already installed, so the fixtures are
 * transpiled to CommonJS in a temp dir and exercised with node:assert. Run from mobile/:
 *   node tests/fixtures.test.cjs
 */
/* global __dirname */
const assert = require('node:assert/strict');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const ts = require('typescript');

const SRC = path.join(__dirname, '..', 'src');
const OUT = fs.mkdtempSync(path.join(os.tmpdir(), 'spankkibot-fixtures-'));

function transpile(from, to, rewrite) {
  const source = rewrite ? rewrite(fs.readFileSync(from, 'utf8')) : fs.readFileSync(from, 'utf8');
  const js = ts.transpileModule(source, {
    compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 },
    fileName: from,
  }).outputText;
  fs.mkdirSync(path.dirname(to), { recursive: true });
  fs.writeFileSync(to, js);
}

(async () => {
try {
  transpile(path.join(SRC, 'lib', 'speechLang.ts'), path.join(OUT, 'lib', 'speechLang.js'));
  transpile(
    path.join(SRC, 'api', 'fixtures.ts'),
    path.join(OUT, 'api', 'fixtures.js'),
    (s) => s.replace("from '@/lib/speechLang'", "from '../lib/speechLang'"),
  );
  const fx = require(path.join(OUT, 'api', 'fixtures.js'));

  // 1) Six selectable customers, in the same order as the backend, and Joni's real identity.
  const customers = fx.fixtureDemoCustomers('en');
  assert.deepEqual(
    customers.map((c) => c.customer_id),
    ['CUST05020', 'CUST00584', 'CUST00586', 'CUST00961', 'CUST00001', 'CUST05014'],
  );
  const joni = customers[5];
  assert.equal(joni.name, 'Joni');
  assert.equal(joni.age, 23);
  assert.equal(joni.postal_code, '00487');

  // 2) Description (tagline) localises for Joni in en / fi / sv; the older five stay English.
  assert.ok(fx.fixtureDemoCustomers('en')[5].tagline.startsWith('An unexpected repair'));
  assert.ok(fx.fixtureDemoCustomers('fi')[5].tagline.startsWith('Yllättävä remontti'));
  assert.ok(fx.fixtureDemoCustomers('sv')[5].tagline.startsWith('En oväntad reparation'));
  assert.ok(fx.fixtureDemoCustomers('fi')[0].tagline.startsWith('Student & part-time barista'));

  // 3) Balance, critical safe-to-spend and the single goal.
  const overview = fx.fixtureOverview('CUST05014', 'en');
  assert.equal(overview.balance, -784.58);
  assert.equal(overview.safe_to_spend.status, 'critical');
  assert.equal(overview.goals.length, 1);
  const goal = overview.goals[0];
  assert.equal(goal.kind, 'other');
  assert.equal(goal.target_amount, 784.58);
  assert.equal(goal.saved_amount, 0);
  assert.equal(goal.deadline, '2027-09-18');

  // 4) Goal name localises; user-typed names are not in the seed map and stay as typed.
  assert.equal(fx.fixtureGoals('CUST05014', 'en')[0].name, 'Back in the black');
  assert.equal(fx.fixtureGoals('CUST05014', 'fi')[0].name, 'Takaisin plussalle');
  assert.equal(fx.fixtureGoals('CUST05014', 'sv')[0].name, 'Tillbaka på plus');
  assert.equal(fx.fixtureGoals('CUST00584', 'sv')[0].name, 'Buffert till lönedagen');

  // 5) Planner keeps the negative surplus in the gap and promises no deadline-only success.
  for (const locale of ['en', 'fi', 'sv']) {
    const plan = fx.fixturePlanGoal('CUST05014', { target_amount: 784.58, deadline: '2027-09-18' }, locale);
    assert.ok(plan.current_monthly_surplus < 0, `${locale}: surplus ${plan.current_monthly_surplus}`);
    assert.ok(plan.gap > plan.needed_per_month, `${locale}: gap ${plan.gap} must include the deficit`);
    assert.equal(plan.feasibility, 'unrealistic');
    assert.equal(plan.suggested_deadline, null);
    assert.ok(plan.summary.length > 10);
    assert.ok(!/on track|aikataulussa|ligger i fas/.test(plan.summary), `${locale}: ${plan.summary}`);
  }
  assert.match(fx.fixturePlanGoal('CUST05014', { target_amount: 784.58, deadline: '2027-09-18' }, 'en').summary, /deficit/);

  // 6) Joni is in balance repair: the recovery nudges replace the generic goal nudge,
  //    and none of them promises the goal is on track while the surplus is negative.
  for (const locale of ['en', 'fi', 'sv']) {
    const ns = fx.fixtureNudges('CUST05014', locale);
    assert.deepEqual(ns.map((n) => n.id), ['recovery_balance', 'recovery_bills', 'recovery_deficit'], locale);
    assert.ok(ns.every((n) => !/on track|aikataulussa|ligger i fas/.test(n.text)), locale);
    assert.ok(ns.every((n) => n.action_prompt), locale);
  }
  assert.match(fx.fixtureNudges('CUST05014', 'en')[0].text, /€784\.58 below zero/);
  assert.match(fx.fixtureNudges('CUST05014', 'fi')[0].text, /784,58 € miinuksella/);
  assert.match(fx.fixtureNudges('CUST05014', 'sv')[0].text, /784,58 € under noll/);
  const joniDeficit = fx.fixtureOverview('CUST05014', 'en').recovery.deficit;
  assert.ok(fx.fixtureNudges('CUST05014', 'fi')[2].text.replace(/[^0-9]/g, '').includes(String(Math.round(joniDeficit))));

  // 7) Recovery classification follows the same rules on each demo customer's own numbers.
  const states = {
    CUST05020: 'ordinary', CUST00584: 'ordinary', CUST00586: 'ordinary',
    CUST00961: 'ordinary', CUST00001: 'ordinary', CUST05014: 'balance_repair',
  };
  for (const [id, state] of Object.entries(states)) {
    const r = fx.fixtureOverview(id, 'en').recovery;
    assert.equal(r.state, state, id);
    const expected = r.balance * 100 < 0 ? 'balance_repair' : r.monthly_surplus * 100 < 0 ? 'cashflow_stabilizing' : 'ordinary';
    assert.equal(r.state, expected, id);
    assert.equal(r.months, 6, id);
    assert.ok(r.tx_count > 0, id);
  }
  const joniRec = fx.fixtureOverview('CUST05014', 'en').recovery;
  assert.equal(joniRec.urgency, 'critical');
  assert.ok(joniRec.deficit > 0);
  assert.equal(joniRec.planned_monthly_change, Math.round((joniRec.deficit + joniRec.goal_monthly_need) * 100) / 100);
  assert.equal(joniRec.goal_reservations_present, joniRec.goal_contributions > 0);

  // 8) Goal progress does not move the balance or the recovery state.
  const beforeGoal = fx.fixtureOverview('CUST05014', 'en');
  fx.fixtureUpdateGoal('CUST05014', 'g-joni-1', { saved_amount: 200 });
  const afterGoal = fx.fixtureOverview('CUST05014', 'en');
  assert.equal(afterGoal.balance, beforeGoal.balance);
  for (const key of ['state', 'balance', 'monthly_income', 'monthly_spending', 'monthly_surplus', 'deficit', 'urgency'])
    assert.equal(afterGoal.recovery[key], beforeGoal.recovery[key], key);
  fx.fixtureUpdateGoal('CUST05014', 'g-joni-1', { saved_amount: 0 });

  // 9) Recovery action prompts stream a grounded answer, in both personas and all locales.
  const realSetTimeout = global.setTimeout;
  global.setTimeout = (cb) => realSetTimeout(cb, 0);
  const stream = async (text, persona = 'sisu', locale = 'en', customer_id = 'CUST05014') => {
    const events = [];
    for await (const e of fx.fixtureChatStream({ customer_id, persona, locale, messages: [{ role: 'user', content: text }], image_base64: null }))
      events.push(e);
    return {
      tool: events.find((e) => e.event === 'tool')?.data.name,
      args: events.find((e) => e.event === 'tool')?.data.args,
      text: events.filter((e) => e.event === 'token').map((e) => e.data.text).join(''),
      widgets: events.filter((e) => e.event === 'widget').map((e) => e.data),
      last: events[events.length - 1],
    };
  };
  try {
    for (const locale of ['en', 'fi', 'sv']) {
      for (const persona of ['sisu', 'aava']) {
        const prompts = fx.fixtureNudges('CUST05014', locale).map((n) => n.action_prompt);
        const want = ['get_overview', 'survival_plan', 'query_spending'];
        for (const [i, prompt] of prompts.entries()) {
          const out = await stream(prompt, persona, locale);
          assert.equal(out.tool, want[i], `${locale}/${persona}: ${prompt}`);
          assert.equal(out.last.event, 'done');
          assert.ok(out.text.length > 20);
          if (i === 0) assert.match(out.text, locale === 'en' ? /784\.58/ : /784,58/);
          if (i === 2) assert.ok(out.text.replace(/[^0-9]/g, '').includes(String(Math.round(joniDeficit))), out.text);
          assert.ok(!/€12,000|12000 €/.test(out.text), out.text);
        }
      }
    }
    const questions = {
      en: ['Show my goals', 'What is safe to spend this week?', 'How much would I save if I reduced dining out by 20%?'],
      fi: ['Näytä tavoitteet', 'Paljonko voin käyttää tällä viikolla?', 'Paljonko säästäisin, jos vähentäisin ulkona syömistä 20%?'],
      sv: ['Visa mina mål', 'Hur mycket kan jag tryggt använda den här veckan?', 'Hur mycket skulle jag spara om jag åt ute 20% mindre?'],
    };
    for (const locale of ['en', 'fi', 'sv']) for (const persona of ['sisu', 'aava']) {
      for (const [i, question] of questions[locale].entries()) {
        const out = await stream(question, persona, locale);
        assert.equal(out.tool, ['list_goals', 'safe_to_spend', 'simulate_what_if'][i]);
        if (i === 0) {
          assert.deepEqual(out.widgets.map((w) => w.type), ['kpi', 'action_buttons']);
          assert.equal(out.widgets[0].data.items[0].value, 0);
          assert.equal(out.widgets[1].data.buttons[0].payload.tab, 'goals');
        }
        const all = (out.text + JSON.stringify(out.last.data.suggestions)).replace(/\s/g, ' ');
        assert.ok(!/Ohjaa säästö|Put the savings|Lägg besparingen|Lyödäänkö lukkoon|Shall we lock|Ska vi slå fast|stay disciplined|pidetään kuri|håll disciplinen/.test(all), all);
      }
      const gap = await stream(fx.fixtureNudges('CUST05014', locale)[2].action_prompt, persona, locale);
      assert.equal(gap.args.start, '2026-03-01');
      assert.equal(gap.args.end, '2026-08-31');
      assert.equal(gap.widgets[0].type, 'bar_chart');
      assert.equal(gap.widgets[0].data.bars.reduce((n, b) => n + b.value, 0).toFixed(2), fx.fixtureSpending('CUST05014', gap.args).total.toFixed(2));
      const ordinary = await stream('How do I get back to a positive balance?', persona, locale, 'CUST05020');
      assert.ok(!/negative balance|miinussaldo|negativa saldot|no ongoing deficit/.test(ordinary.text), ordinary.text);
    }
    // The goal nudge action keeps the existing goal, not a generic €12,000 new plan.
    for (const locale of ['en', 'fi', 'sv']) {
      const goalName = fx.fixtureGoals('CUST05014', locale)[0].name;
      const out = await stream(`How can I reach my ${goalName} goal faster?`, 'sisu', locale);
      assert.equal(out.tool, 'plan_goal');
      assert.equal(out.args.target_amount, 784.58);
      assert.match(out.text, /€785/);
      assert.ok(!/€12,000/.test(out.text), out.text);
    }
    // The six-month deficit action routes to spending, not a goal plan.
    assert.equal((await stream('Mistä kuuden kuukauden menoero muodostuu?', 'sisu', 'fi')).tool, 'query_spending');
    // Emergency-buffer support is a lesson, not an invented credit product.
    assert.equal((await stream('What is an emergency buffer and how do I start one?', 'aava', 'en')).tool, 'explain_concept');
  } finally {
    global.setTimeout = realSetTimeout;
  }

  // 10) The five old customers keep their balances and goal counts.
  const expected = { CUST05020: 1138.42, CUST00584: 63.4, CUST00586: 8432.19, CUST00961: 2918.55, CUST00001: 14205.8 };
  for (const [id, balance] of Object.entries(expected)) {
    assert.equal(fx.fixtureOverview(id, 'en').balance, balance, id);
    assert.equal(fx.fixtureGoals(id, 'en').length, 2, id);
  }

  console.log('fixtures.test.cjs: OK');
} finally {
  fs.rmSync(OUT, { recursive: true, force: true });
}
})().catch((err) => {
  console.error(err);
  process.exit(1);
});
