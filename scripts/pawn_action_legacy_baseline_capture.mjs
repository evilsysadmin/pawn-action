#!/usr/bin/env node
/** Read-only, provenance-bound visual reference from the Chess Studio Web release.
 *  NOT an approved baseline: live pointer identity must never silently become
 *  visual acceptance. No credentials, R2 writes, or Chess Studio mutation.
 */
import assert from 'node:assert/strict';
import { createRequire } from 'node:module';
import { createHash } from 'node:crypto';
import { mkdir, readFile, writeFile } from 'node:fs/promises';
import path from 'node:path';

const requireE2e = createRequire(new URL('../e2e/package.json', import.meta.url));
const ORIGIN = 'https://assets.chess-studio.shadowops.dpdns.org';
const PREFIX = 'pawn-slug-godot';
const POINTER_URL = ORIGIN + '/' + PREFIX + '/current.json';
const REQUIRED = ['index.html', 'index.js', 'index.wasm', 'index.pck'];
const OUT = path.resolve(process.env.PAWN_ACTION_LEGACY_CAPTURE_DIR || 'legacy-baseline-candidate');
const SHA40 = /^[0-9a-f]{40}$/;
const SHA64 = /^[0-9a-f]{64}$/;
const HEX16 = /^[0-9a-f]{16}$/;
const digest = data => createHash('sha256').update(data).digest('hex');

function assertPointer(pointer) {
  assert.equal(pointer?.version, 1, 'legacy release pointer version');
  assert.match(pointer.release, HEX16, 'legacy release id');
  assert.match(pointer.sha256, SHA64, 'legacy bundle digest');
  assert.match(pointer.sourceSha, SHA40, 'legacy source HEAD SHA is required');
  const releaseRoot = ORIGIN + '/' + PREFIX + '/releases/' + pointer.release + '/';
  assert.equal(pointer.index, releaseRoot + 'index.html', 'legacy index must use trusted immutable origin');
  assert.ok(pointer.files && typeof pointer.files === 'object' && !Array.isArray(pointer.files));
  const keys = Object.keys(pointer.files);
  assert.ok(keys.length >= 4 && keys.length <= 80, 'bounded release manifest');
  for (const name of keys) {
    assert.ok(/^[A-Za-z0-9_./-]+$/.test(name) && !name.startsWith('/')
      && !name.split('/').includes('..'), 'no unsafe paths: ' + name);
    const entry = pointer.files[name];
    assert.equal(entry.key, PREFIX + '/releases/' + pointer.release + '/' + name);
    assert.equal(entry.url, releaseRoot + name, 'no alternate CDN or URL');
    assert.match(entry.sha256, SHA64, 'immutable file sha256');
    assert.ok(Number.isSafeInteger(entry.bytes) && entry.bytes > 0 && entry.bytes < 150e6,
      'bounded immutable asset bytes');
  }
  for (const name of REQUIRED) assert.ok(pointer.files[name], 'missing required asset ' + name);
  return releaseRoot;
}
function selfTest() {
  const p = {
    version: 1, release: 'f'.repeat(16), sha256: 'e'.repeat(64), sourceSha: 'd'.repeat(40),
    index: ORIGIN + '/' + PREFIX + '/releases/' + 'f'.repeat(16) + '/index.html',
    files: {},
  };
  for (const name of REQUIRED) {
    p.files[name] = {
      key: PREFIX + '/releases/' + p.release + '/' + name,
      url: ORIGIN + '/' + PREFIX + '/releases/' + p.release + '/' + name,
      sha256: 'a'.repeat(64), bytes: 512,
    };
  }
  assertPointer(p);
  const invalid = (edit) => {
    const copy = structuredClone(p);
    edit(copy);
    assert.throws(() => assertPointer(copy));
  };
  invalid(p => { p.sourceSha = ''; });
  invalid(p => { p.index = 'https://evil.example.test/index.html'; });
  invalid(p => { p.files['index.wasm'].url = ORIGIN + '/pawn-action/current.json'; });
  invalid(p => { delete p.files['index.pck']; });
  invalid(p => { p.files['../out.js'] = p.files['index.js']; });
  invalid(p => { p.files['index.wasm'].sha256 = 'xxx'; });
  invalid(p => { p.files['index.html'].bytes = 0; });
  console.log('OK read-only Chess Studio baseline pointer contract');
}
async function fetchBytes(url, maxBytes) {
  const response = await fetch(url, {
    redirect: 'error', signal: AbortSignal.timeout(30000), cache: 'no-store',
  });
  if (!response.ok) throw new Error('Trusted legacy CDN HTTP ' + response.status);
  const length = Number(response.headers.get('content-length') || 0);
  if (length > maxBytes) throw new Error('Legacy CDN payload too large');
  const data = Buffer.from(await response.arrayBuffer());
  if (data.length > maxBytes) throw new Error('Legacy CDN body too large');
  return data;
}
async function capture(page, url, filename, outputs) {
  await page.goto(url, { waitUntil: 'domcontentloaded', timeout: 45000 });
  await page.locator('canvas').waitFor({ state: 'visible', timeout: 45000 });
  await page.waitForFunction(() => window.__legacyReady === true, null, { timeout: 45000 });
  await page.waitForTimeout(700);
  const image = await page.screenshot({ fullPage: false });
  await writeFile(path.join(OUT, filename), image);
  outputs[filename] = {
    sha256: digest(image), bytes: image.length,
    viewport: page.viewportSize(), stage: 'industrial_front_v1',
  };
}
async function installProbe(page) {
  await page.addInitScript(() => {
    window.__legacyReady = false;
    window.__legacyEvents = [];
    window.addEventListener('message', event => {
      if (event.data?.source !== 'pawn-slug-godot') return;
      const type = String(event.data?.type || '');
      window.__legacyEvents.push(type);
      if (type === 'ready') window.__legacyReady = true;
    });
  });
}
async function main() {
  await mkdir(OUT, { recursive: true });
  try {
    const raw = await fetchBytes(POINTER_URL, 1024 * 1024);
    const pointer = JSON.parse(raw.toString('utf8'));
    const releaseRoot = assertPointer(pointer);
    const verifiedAssets = {};
    for (const name of REQUIRED) {
      const bytes = await fetchBytes(pointer.files[name].url, 150e6);
      assert.equal(bytes.length, pointer.files[name].bytes, 'legacy bytes ' + name);
      assert.equal(digest(bytes), pointer.files[name].sha256, 'legacy immutable SHA ' + name);
      verifiedAssets[name] = { sha256: digest(bytes), bytes: bytes.length };
    }
    const { chromium } = requireE2e('playwright');
    const browser = await chromium.launch({ headless: true });
    const captures = {};
    try {
      const desktop = await browser.newPage({ viewport: { width: 1280, height: 720 } });
      await installProbe(desktop);
      const index = releaseRoot + 'index.html?stage=industrial_front_v1';
      await capture(desktop, index, '00-idle.png', captures);
      const canvas = desktop.locator('canvas');
      await canvas.click({ position: { x: 640, y: 360 } });
      await desktop.keyboard.down('ArrowRight');
      try {
        await desktop.waitForTimeout(350);
        const image = await desktop.screenshot({ fullPage: false });
        await writeFile(path.join(OUT, '10-run.png'), image);
        captures['10-run.png'] = { sha256: digest(image), bytes: image.length,
          viewport: { width: 1280, height: 720 }, stage: 'industrial_front_v1' };
        const firesBefore = await desktop.evaluate(() =>
          window.__legacyEvents.filter(x => x === 'player-fired').length);
        await desktop.keyboard.down('z');
        try {
          await desktop.waitForFunction(before =>
            window.__legacyEvents.filter(x => x === 'player-fired').length > before,
            firesBefore, { timeout: 4000 });
          const fired = await desktop.screenshot({ fullPage: false });
          await writeFile(path.join(OUT, '20-run-fire.png'), fired);
          captures['20-run-fire.png'] = { sha256: digest(fired), bytes: fired.length,
            viewport: { width: 1280, height: 720 }, stage: 'industrial_front_v1' };
        } finally { await desktop.keyboard.up('z'); }
      } finally { await desktop.keyboard.up('ArrowRight'); }

      const mobile = await browser.newPage({ viewport: { width: 915, height: 412 },
        isMobile: true, hasTouch: true, deviceScaleFactor: 1 });
      await installProbe(mobile);
      await capture(mobile, index, 'mobile-landscape-ready.png', captures);

      // A different route is not falsely labeled as a verified SMG pickup.
      const smg = await browser.newPage({ viewport: { width: 1280, height: 720 } });
      await installProbe(smg);
      await smg.goto(index + '&weaponProbe=machinegun', { waitUntil: 'domcontentloaded' });
      await smg.locator('canvas').waitFor({ state: 'visible', timeout: 45000 });
      await smg.waitForFunction(() => window.__legacyReady === true, null, { timeout: 45000 });
      await smg.waitForTimeout(900);
      const weaponChange = await smg.evaluate(() => window.__legacyEvents.includes('weapon-changed'));
      if (weaponChange) {
        const image = await smg.screenshot({ fullPage: false });
        await writeFile(path.join(OUT, '51-smg-selected.png'), image);
        captures['51-smg-selected.png'] = { sha256: digest(image), bytes: image.length,
          viewport: { width: 1280, height: 720 }, stage: 'industrial_front_v1',
          verified: 'weapon-changed bridge event' };
      }
      const evidence = {
        schema: 1, status: 'candidate_not_approved', owner: 'chess-studio',
        pointerUrl: POINTER_URL, pointerSha256: digest(raw), sourceSha: pointer.sourceSha,
        release: pointer.release, bundleSha256: pointer.sha256,
        verifiedAssets, captures,
        smg: weaponChange ? 'captured' : 'not_proven',
      };
      await writeFile(path.join(OUT, 'baseline-candidate.json'),
        JSON.stringify(evidence, null, 2) + '\n');
      console.log('Legacy visual candidate: ' + pointer.sourceSha + ', captures=' +
        Object.keys(captures).length + ', SMG=' + evidence.smg);
    } finally { await browser.close(); }
  } catch (error) {
    await writeFile(path.join(OUT, 'baseline-error.json'),
      JSON.stringify({ schema: 1, status: 'unavailable_not_approved',
        pointerUrl: POINTER_URL, reason: String(error.message || error) }, null, 2) + '\n');
    throw error;
  }
}
if (process.argv.includes('--self-test')) selfTest();
else await main();
