import { createRequire } from 'node:module';
import { readFile, mkdir } from 'node:fs/promises';
import assert from 'node:assert/strict';

const requireFromE2e = createRequire(new URL('../e2e/package.json', import.meta.url));
const { chromium } = requireFromE2e('playwright');
const outputDir = process.env.PAWN_SLUG_CAPTURE_DIR || '/tmp/pawn-action-boot-failure';
await mkdir(outputDir, { recursive: true });

// Test the actual Web shell in Chromium, but replace Godot with an explicit
// rejected Engine. This does NOT impersonate a real gameplay or atlas smoke.
const template = await readFile(
  new URL('../games/pawn-slug-godot/web/pawn_slug_shell.html', import.meta.url), 'utf8',
);
assert.match(template, /id="boot-error" role="alert" hidden/);
const html = template
  .replaceAll('$GODOT_PROJECT_NAME', 'Pawn Action')
  .replace('$GODOT_HEAD_INCLUDE', '')
  .replace('<script src="$GODOT_URL"></script>', '')
  .replace('$GODOT_CONFIG', '{}');

const browser = await chromium.launch({ headless: true });
async function preparePage(context, path, fail = true) {
  const page = await context.newPage();
  await page.addInitScript((shouldFail) => {
    window.__pawnActionBootEvents = [];
    window.addEventListener('message', (event) => {
      if (event.data?.source === 'pawn-slug-godot') {
        window.__pawnActionBootEvents.push(event.data.type);
      }
    });
    window.Engine = class {
      startGame() {
        return shouldFail
          ? Promise.reject(new Error('simulated Web engine boot failure'))
          : Promise.resolve();
      }
    };
  }, fail);
  let visits = 0;
  await page.route('**' + path, async (route) => {
    visits += 1;
    await route.fulfill({ status: 200, contentType: 'text/html', body: html });
  });
  await page.goto('http://127.0.0.1:4179' + path, { waitUntil: 'load' });
  return { page, visits: () => visits };
}

try {
  const desktop = await browser.newContext({ viewport: { width: 1280, height: 720 } });
  const { page, visits } = await preparePage(desktop, '/pawn-action-boot-error-probe');
  await page.waitForSelector('#boot-error:not([hidden])');
  await page.waitForFunction(() => window.__pawnActionBootEvents.includes('load-error'));
  const failure = await page.evaluate(() => ({
    errorVisible: document.getElementById('boot-error')?.hidden === false,
    accessible: document.getElementById('boot-error')?.getAttribute('role') === 'alert'
      && !document.getElementById('boot')?.hasAttribute('aria-hidden'),
    canvasDisabled: getComputedStyle(document.getElementById('canvas')).pointerEvents === 'none',
    errorText: document.getElementById('boot-error')?.textContent || '',
    events: window.__pawnActionBootEvents,
  }));
  assert.equal(failure.errorVisible, true);
  assert.equal(failure.accessible, true);
  assert.equal(failure.canvasDisabled, true);
  assert.match(failure.errorText, /No se ha podido iniciar Pawn Action/);
  assert.deepEqual(failure.events, ['load-error']);
  assert.equal(visits(), 1);
  await page.screenshot({ path: outputDir + '/web-boot-error-desktop.png' });

  // Explicit keyboard activation reloads the *failed* shell; no automatic reload.
  await page.getByRole('button', { name: 'Reintentar' }).focus();
  await Promise.all([page.waitForEvent('load'), page.keyboard.press('Enter')]);
  assert.equal(visits(), 2);
  await desktop.close();

  const landscape = await browser.newContext({
    viewport: { width: 915, height: 412 }, isMobile: true, hasTouch: true,
  });
  const mobile = (await preparePage(landscape, '/pawn-action-boot-error-landscape')).page;
  await mobile.waitForSelector('#boot-error:not([hidden])');
  const bounds = await mobile.getByRole('button', { name: 'Reintentar' }).boundingBox();
  const mobileState = await mobile.evaluate(() => ({
    overflow: document.documentElement.scrollWidth > innerWidth,
    width: innerWidth, height: innerHeight,
  }));
  assert.equal(mobileState.overflow, false);
  assert.ok(bounds && bounds.x >= 0 && bounds.y >= 0);
  assert.ok(bounds.x + bounds.width <= mobileState.width);
  assert.ok(bounds.y + bounds.height <= mobileState.height);
  await mobile.screenshot({ path: outputDir + '/web-boot-error-landscape.png' });
  await landscape.close();

  const success = await browser.newContext({ viewport: { width: 1280, height: 720 } });
  const good = (await preparePage(success, '/pawn-action-boot-success-probe', false)).page;
  await good.evaluate(() => window.__pawnSlugGodotVisualReady());
  const status = await good.evaluate(() => ({
    ready: document.getElementById('canvas')?.classList.contains('is-ready') === true,
    errorHidden: document.getElementById('boot-error')?.hidden === true,
    bridgeErrors: window.__pawnActionBootEvents.filter((x) => x === 'load-error').length,
  }));
  assert.deepEqual(status, { ready: true, errorHidden: true, bridgeErrors: 0 });
  await success.close();
  console.log('OK Pawn Action Web boot failure UI: desktop, landscape, keyboard retry, successful startup');
} finally {
  await browser.close();
}
