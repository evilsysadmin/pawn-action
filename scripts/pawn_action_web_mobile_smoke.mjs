import { createRequire } from 'node:module';
import { mkdir, writeFile } from 'node:fs/promises';

const requireFromE2e = createRequire(new URL('../e2e/package.json', import.meta.url));
const { chromium } = requireFromE2e('playwright');
const indexUrl = process.env.PAWN_ACTION_WEB_INDEX_URL ||
  'http://127.0.0.1:4179/index.html?stage=industrial_front_v1';
const outputDir = process.env.PAWN_SLUG_CAPTURE_DIR || '/tmp/pawn-action-mobile';
const viewport = { width: 915, height: 412 };

await mkdir(outputDir, { recursive: true });
const browser = await chromium.launch({ headless: true });
const context = await browser.newContext({
  viewport, isMobile: true, hasTouch: true, deviceScaleFactor: 1,
});
const page = await context.newPage();
const pageErrors = [];
page.on('pageerror', (error) => pageErrors.push(String(error)));
await page.addInitScript(() => {
  window.__pawnActionEvents = [];
  window.addEventListener('message', (event) => {
    if (event.data?.source === 'pawn-slug-godot') {
      window.__pawnActionEvents.push(String(event.data.type || ''));
    }
  });
});

async function boot({ reload = false } = {}) {
  if (reload) {
    await page.reload({ waitUntil: 'domcontentloaded', timeout: 45_000 });
  } else {
    await page.goto(indexUrl, { waitUntil: 'domcontentloaded', timeout: 45_000 });
  }
  await page.waitForSelector('canvas.is-ready', { state: 'visible', timeout: 60_000 });
  await page.waitForFunction(
    () => window.__pawnActionEvents?.includes('ready'),
    null, { timeout: 60_000 },
  );
  const status = await page.evaluate(() => ({
    touch: navigator.maxTouchPoints,
    width: innerWidth,
    height: innerHeight,
    events: window.__pawnActionEvents,
  }));
  if (status.touch < 1 || status.width <= status.height) {
    throw new Error('Invalid mobile landscape context: ' + JSON.stringify(status));
  }
  return status;
}

// Real Chrome compositor touch input, held through Godot physics ticks.
// Positions reflect the three supported Godot content-stretch projections.
// Never inject fake Godot actions: the 'player-fired' bridge event is required.
async function fireViaTouch() {
  const client = await context.newCDPSession(page);
  const w = viewport.width;
  const h = viewport.height;
  const scale = h / 720;
  const letterbox = (w - 1280 * scale) / 2;
  const targets = [
    { x: w - 90, y: h - 88, layout: 'viewport' },
    { x: letterbox + (1280 - 90) * scale, y: h - 88 * scale, layout: 'letterbox' },
    { x: w - 90 * scale, y: h - 88 * scale, layout: 'expanded' },
  ];
  try {
    for (const target of targets) {
      const before = await page.evaluate(() =>
        window.__pawnActionEvents.filter((type) => type === 'player-fired').length);
      await client.send('Input.dispatchTouchEvent', {
        type: 'touchStart',
        touchPoints: [{ id: 1, x: Math.round(target.x), y: Math.round(target.y) }],
      });
      try {
        await page.waitForTimeout(650);
      } finally {
        await client.send('Input.dispatchTouchEvent', {
          type: 'touchEnd', touchPoints: [],
        });
      }
      const after = await page.evaluate(() =>
        window.__pawnActionEvents.filter((type) => type === 'player-fired').length);
      if (after > before) return { target, shots: after - before };
    }
    throw new Error('Held touchscreen FIRE never emitted player-fired from Godot');
  } finally {
    await client.detach();
  }
}


/* Real Chromium touch beyond FIRE: the actual Godot grenade signal must fire.
 * Positions cover viewport, 16:9 letterbox and expanded canvas layouts. */
async function grenadeViaTouch() {
  const client = await context.newCDPSession(page);
  const w = viewport.width;
  const h = viewport.height;
  const scale = h / 720;
  const letterbox = (w - 1280 * scale) / 2;
  const targets = [
    { x: w - 84, y: h - 173, layout: 'viewport' },
    { x: letterbox + 1196 * scale, y: 547 * scale, layout: 'letterbox' },
    { x: w - 84 * scale, y: h - 173 * scale, layout: 'expanded' },
  ];
  try {
    for (const target of targets) {
      const before = await page.evaluate(() => ({
        grenades: window.__pawnActionEvents.filter((type) => type === 'grenade-thrown').length,
        shots: window.__pawnActionEvents.filter((type) => type === 'player-fired').length,
      }));
      await client.send('Input.dispatchTouchEvent', {
        type: 'touchStart',
        touchPoints: [{ id: 1, x: Math.round(target.x), y: Math.round(target.y) }],
      });
      try {
        await page.waitForTimeout(380);
      } finally {
        await client.send('Input.dispatchTouchEvent', {
          type: 'touchEnd', touchPoints: [],
        });
      }
      const after = await page.evaluate(() => ({
        grenades: window.__pawnActionEvents.filter((type) => type === 'grenade-thrown').length,
        shots: window.__pawnActionEvents.filter((type) => type === 'player-fired').length,
      }));
      if (after.grenades > before.grenades) {
        // Prior layout probes may hit an unrelated control; only a touch
        // that actually throws a grenade is evidence about GR isolation.
        if (after.shots !== before.shots) {
          throw new Error('Touch GR also fired an unintended bullet: ' +
            JSON.stringify({ before, after, target }));
        }
        return { target, throws: after.grenades - before.grenades,
          unwantedShots: 0 };
      }
    }
    throw new Error('Held touchscreen GR never emitted grenade-thrown from Godot');
  } finally {
    await client.detach();
  }
}

const results = { schema: 1, viewport, phases: [] };
try {
  results.phases.push({ phase: 'cold', ...await boot() });
  await page.screenshot({ path: outputDir + '/mobile-landscape-ready.png' });

  results.phases.push({ phase: 'touch-fire', ...await fireViaTouch() });
  await page.screenshot({ path: outputDir + '/mobile-landscape-fire.png' });

  results.phases.push({ phase: 'touch-grenade', ...await grenadeViaTouch() });
  await page.screenshot({ path: outputDir + '/mobile-landscape-grenade.png' });

  results.phases.push({ phase: 'reload', ...await boot({ reload: true }) });
  results.phases.push({ phase: 'touch-fire-after-reload', ...await fireViaTouch() });
  await page.screenshot({ path: outputDir + '/mobile-landscape-reload.png' });

  // Godot opens its mobile Web window fullscreen. Chromium rejects resizing
  // that window in place, so use a fresh real portrait mobile context.
  const portraitContext = await browser.newContext({
    viewport: { width: 390, height: 844 },
    isMobile: true, hasTouch: true, deviceScaleFactor: 1,
  });
  const portraitPage = await portraitContext.newPage();
  portraitPage.on('pageerror', (error) => pageErrors.push(String(error)));
  await portraitPage.goto(indexUrl, { waitUntil: 'domcontentloaded', timeout: 45_000 });
  await portraitPage.waitForSelector('canvas.is-ready', { state: 'visible', timeout: 60_000 });
  await portraitPage.screenshot({ path: outputDir + '/mobile-portrait-rotate.png' });
  const portrait = await portraitPage.evaluate(() => {
    const notice = document.getElementById('rotate-notice');
    return {
      width: innerWidth,
      height: innerHeight,
      orientationBlocked: document.documentElement.classList.contains('pawn-action-portrait'),
      noticeVisible: Boolean(notice && getComputedStyle(notice).display !== 'none'),
      noticeOnTop: Boolean(document.elementFromPoint(innerWidth / 2, innerHeight / 2)?.closest('#rotate-notice')),
      fullscreenElement: document.fullscreenElement?.id || null,
      noticeText: notice?.textContent?.replace(/\s+/g, ' ').trim() || '',
      canvasTouchDisabled: getComputedStyle(document.getElementById('canvas')).pointerEvents === 'none',
    };
  });
  await portraitContext.close();
  if (
    portrait.width >= portrait.height ||
    !portrait.orientationBlocked ||
    !portrait.noticeVisible ||
    !portrait.noticeOnTop ||
    portrait.fullscreenElement !== null ||
    !portrait.noticeText.includes('GIRA EL MÓVIL') ||
    !portrait.canvasTouchDisabled
  ) {
    throw new Error('Portrait touch guidance not active: ' + JSON.stringify(portrait));
  }
  results.phases.push({ phase: 'portrait', ...portrait });

  if (pageErrors.length > 0) {
    throw new Error('Mobile JS errors: ' + JSON.stringify(pageErrors));
  }
  console.log(JSON.stringify(results));
} catch (error) {
  results.error = String(error);
  console.error(results.error);
  await page.screenshot({ path: outputDir + '/mobile-failure.png' }).catch(() => {});
  process.exitCode = 1;
} finally {
  results.pageErrors = pageErrors;
  await writeFile(
    outputDir + '/mobile-web-smoke.json',
    JSON.stringify(results, null, 2) + '\n',
  );
  await browser.close();
}
