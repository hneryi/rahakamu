#!/usr/bin/env node
/* global __dirname */
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const root = path.resolve(__dirname, '../..');
const read = (file) => fs.readFileSync(path.join(root, file), 'utf8');
const config = JSON.parse(read('mobile/app.json')).expo;
const manifest = JSON.parse(read('mobile/public/manifest.json'));
for (const name of [config.name, config.web.name, config.web.shortName, manifest.name, manifest.short_name]) {
  assert.equal(name, 'Rahakamu');
}
assert.equal(config.slug, 'spankkibot');
assert.equal(config.scheme, 'spankkibot');
assert.equal(config.ios.bundleIdentifier, 'fi.junction.spankkibot');
assert.equal(config.android.package, 'fi.junction.spankkibot');
assert.equal(JSON.parse(read('mobile/package.json')).name, 'spankkibot-mobile');
for (const file of ['mobile/app.json', 'mobile/public/index.html', 'mobile/public/manifest.json',
  'mobile/src/app/onboarding.tsx', 'mobile/src/components/AppFrame.tsx',
  'backend/app/data/lessons.json', 'backend/app/analytics/benchmarks.py', 'deploy/coming-soon/index.html']) {
  assert.ok(read(file).includes('Rahakamu'), file);
  assert.ok(!read(file).includes('SPankkiBot'), file);
}
JSON.parse(read('backend/app/data/lessons.json'));
assert.match(read('mobile/public/index.html'), /<title>Rahakamu<\/title>/);
assert.match(read('backend/app/main.py'), /title="Rahakamu API"/);
assert.match(read('backend/app/main.py'), /"name": "Rahakamu API"/);
assert.match(read('backend/app/main.py'), /getLogger\("spankkibot"\)/);
assert.match(read('mobile/src/store/session.ts'), /spankkibot\.session\.v1/);
assert.match(read('mobile/src/store/chat.ts'), /spankkibot\.chat\.v1/);
assert.match(read('mobile/src/store/learn.ts'), /spankkibot\.learn\.v1/);
assert.match(read('docs/S-MOBIILI_INTEGRATION.md'), /SPankkiBotHost\.getAccessToken/);
console.log('Branding and compatibility identifiers: OK');
