import { createRequire } from 'node:module';
import { mkdir, writeFile } from 'node:fs/promises';
import { execFileSync } from 'node:child_process';

const requireFromE2e = createRequire(new URL('../e2e/package.json', import.meta.url));
const { chromium } = requireFromE2e('playwright');

const indexUrl = String(
  process.env.PAWN_SLUG_GODOT_INDEX_URL ||
  'http://127.0.0.1:4179/index.html?stage=industrial_front_v1'
).trim();
const outputDir = String(process.env.PAWN_SLUG_CAPTURE_DIR || '/tmp/pawn-slug-visual').trim();
const stageIds = String(
  process.env.PAWN_SLUG_CAPTURE_STAGES ||
  'industrial_front_v1,harbor_raid_v1,alpine_fortress_v1,jungle_relay_v1'
)
  .split(',')
  .map((value) => value.trim())
  .filter(Boolean);

if (stageIds.length === 0) {
  throw new Error('Pawn Slug visual capture needs at least one stage id');
}

await mkdir(outputDir, { recursive: true });
const browser = await chromium.launch({ headless: true });
const page = await browser.newPage({ viewport: { width: 1280, height: 720 } });

await page.addInitScript(() => {
  window.__pawnSlugCaptureReady = false;
  window.__pawnSlugCaptureEvents = [];
  const params = new URLSearchParams(window.location.search);
  const stage = params.get('stage') || '';
  const traversalProbes = {
    industrial_front_v1: 1900,
    harbor_raid_v1: 3860,
    alpine_fortress_v1: 4200,
    jungle_relay_v1: 3820,
  };
  const jumpProbe = params.get('jumpProbe') === '1';
  const pickupProbe = params.get('pickupProbe') === 'machinegun';
  // The authored MG pickup in industrial_front_v1 is at x=1240; both repos
  // spawn 70px beforehand. Godot still owns actual pickup, weapon and firing.
  window.__pawnSlugVisualProbeX = pickupProbe ? 1170 : jumpProbe ? 110 :
    params.get('visualProbe') === '1' ? traversalProbes[stage] ?? null : null;
  window.__pawnSlugVisualProbeCalmRadius = pickupProbe ? 1000 : jumpProbe ? 950 : null;
  window.__pawnSlugVisualProbeWeapon = params.get('weaponProbe') || '';
  window.addEventListener('message', (event) => {
    const data = event.data;
    if (data?.source !== 'pawn-slug-godot') return;
    window.__pawnSlugCaptureEvents.push(String(data?.type || ''));
    if (data?.type === 'ready') {
      window.__pawnSlugCaptureReady = true;
    }
  });
});

function urlForStage(stageId, { visualProbe = false, weaponProbe = '', jumpProbe = false, pickupProbe = false } = {}) {
  const url = new URL(indexUrl);
  url.searchParams.set('stage', stageId);
  if (visualProbe) url.searchParams.set('visualProbe', '1');
  else url.searchParams.delete('visualProbe');
  if (weaponProbe) url.searchParams.set('weaponProbe', weaponProbe);
  else url.searchParams.delete('weaponProbe');
  if (jumpProbe) url.searchParams.set('jumpProbe', '1');
  else url.searchParams.delete('jumpProbe');
  if (pickupProbe) url.searchParams.set('pickupProbe', 'machinegun');
  else url.searchParams.delete('pickupProbe');
  return url.toString();
}

async function loadStage(stageId, options = {}) {
  const url = urlForStage(stageId, options);
  await page.goto(url, { waitUntil: 'domcontentloaded', timeout: 45_000 });
  await page.waitForSelector('canvas', { state: 'visible', timeout: 45_000 });
  await page.waitForFunction(() => window.__pawnSlugCaptureReady === true, null, { timeout: 45_000 });
  await page.waitForTimeout(1600);

  const canvasLocator = page.locator('canvas');
  const canvas = await canvasLocator.boundingBox();
  if (!canvas || canvas.width < 640 || canvas.height < 360) {
    throw new Error(`Pawn Slug canvas is unexpectedly small for ${stageId}: ${JSON.stringify(canvas)}`);
  }
  return { stageId, url, canvas, canvasLocator };
}

const stageOverviews = [];
const captures = [];
async function capture(label) {
  const path = `${outputDir}/${label}.png`;
  await page.screenshot({ path, fullPage: false });
  captures.push({ label, path, kind: 'overview' });
}

async function captureDetailedCloseup(label, canvas, { followPlayer = false } = {}) {
  const path = `${outputDir}/${label}-closeup.png`;
  // The camera centers Matthias once he leaves the starting area. A fixed
  // left-edge crop would show only enemies during later jump frames.
  const clip = {
    x: Math.max(0, canvas.x + (followPlayer ? Math.min(canvas.width * 0.25, 360) : 0)),
    y: Math.max(0, canvas.y + canvas.height * 0.38),
    width: Math.min(canvas.width * 0.52, 560),
    height: Math.min(canvas.height * 0.58, 420),
  };
  await page.screenshot({ path, clip });
  captures.push({ label: `${label}-closeup`, path, kind: 'player-closeup' });
}

const detailedStage = stageIds[0];
const detailed = await loadStage(detailedStage);
const overviewPath = `${outputDir}/stage-${detailedStage}.png`;
await page.screenshot({ path: overviewPath, fullPage: false });
stageOverviews.push({ stageId: detailedStage, url: detailed.url, canvas: detailed.canvas, path: overviewPath });

// Keep the historical filename for consumers that only need one proof image.
const legacyOutputPath = `${outputDir}/pawn-slug-industrial-runtime.png`;
await page.screenshot({ path: legacyOutputPath, fullPage: false });
await capture('00-idle');
await captureDetailedCloseup('00-idle', detailed.canvas);

// Exercise the actual Godot runtime, not only the packed sheet. The short burst
// samples almost every 16 fps run frame and makes blank/sunk/jumping frames or
// silhouette flicker obvious in the uploaded PR artifact.
await detailed.canvasLocator.click({ position: { x: detailed.canvas.width / 2, y: detailed.canvas.height / 2 } });
await page.keyboard.down('ArrowRight');
await page.waitForTimeout(320);
for (let frame = 0; frame < 12; frame += 1) {
  const label = `10-run-${String(frame).padStart(2, '0')}`;
  await capture(label);
  if ([0, 3, 7, 11].includes(frame)) await captureDetailedCloseup(label, detailed.canvas);
  await page.waitForTimeout(50);
}

// Fire while still moving so pistol-vs-SMG silhouette mistakes, bad muzzle
// alignment, or one-shot animation pops are visible frame-by-frame.
const pistolShotsBefore = await page.evaluate(() => window.__pawnSlugCaptureEvents.filter((type) => type === 'player-fired').length);
await page.keyboard.down('z');
for (let frame = 0; frame < 12; frame += 1) {
  const label = `20-run-fire-${String(frame).padStart(2, '0')}`;
  await capture(label);
  if ([0, 3, 7, 11].includes(frame)) await captureDetailedCloseup(label, detailed.canvas);
  await page.waitForTimeout(55);
}
await page.keyboard.up('z');
const pistolShotsAfter = await page.evaluate(() => window.__pawnSlugCaptureEvents.filter((type) => type === 'player-fired').length);
if (pistolShotsAfter <= pistolShotsBefore) {
  throw new Error('Pawn Action Web: real keyboard pistol fire never reached Godot');
}
await page.keyboard.up('ArrowRight');
await page.waitForTimeout(260);
await capture('30-idle-after-run-fire');

// Crouch is another high-risk body-anchor transition and costs almost nothing
// to sample while the runtime is already warm.
await page.keyboard.down('ArrowDown');
await page.waitForTimeout(160);
for (let frame = 0; frame < 4; frame += 1) {
  const label = `40-crouch-${String(frame).padStart(2, '0')}`;
  await capture(label);
  if ([0, 2, 3].includes(frame)) await captureDetailedCloseup(label, detailed.canvas);
  await page.waitForTimeout(90);
}
await page.keyboard.up('ArrowDown');

// Dedicated SMG render/switch proof. The local PR capture uses a JS-only
// visual probe rather than depending on combat traversal. Staging E2E remains
// responsible for proving the real pickup path and weapon-pickup event.
const smgStage = await loadStage(detailedStage, { weaponProbe: 'machinegun' });
const smgProbeSelected = await page.evaluate(() => (
  Array.isArray(window.__pawnSlugCaptureEvents)
  && window.__pawnSlugCaptureEvents.includes('weapon-changed')
));
if (!smgProbeSelected) {
  throw new Error('Pawn Slug SMG visual probe did not emit weapon-changed');
}
await smgStage.canvasLocator.click({ position: { x: smgStage.canvas.width / 2, y: smgStage.canvas.height / 2 } });
await capture('50-smg-selected-immediate');
await captureDetailedCloseup('50-smg-selected-immediate', smgStage.canvas);
await page.waitForTimeout(100);
await capture('51-smg-selected-after-100ms');
await captureDetailedCloseup('51-smg-selected-after-100ms', smgStage.canvas);

await page.keyboard.down('ArrowRight');
for (let frame = 0; frame < 13; frame += 1) {
  const label = `52-smg-run-${String(frame).padStart(2, '0')}`;
  await capture(label);
  if ([0, 4, 8, 12].includes(frame)) await captureDetailedCloseup(label, smgStage.canvas);
  await page.waitForTimeout(48);
}

const smgShotsBefore = await page.evaluate(() => window.__pawnSlugCaptureEvents.filter((type) => type === 'player-fired').length);
await page.keyboard.down('z');
for (let frame = 0; frame < 13; frame += 1) {
  const label = `53-smg-run-fire-${String(frame).padStart(2, '0')}`;
  await capture(label);
  if ([0, 4, 8, 12].includes(frame)) await captureDetailedCloseup(label, smgStage.canvas);
  await page.waitForTimeout(55);
}
await page.keyboard.up('z');
const smgShotsAfter = await page.evaluate(() => window.__pawnSlugCaptureEvents.filter((type) => type === 'player-fired').length);
if (smgShotsAfter <= smgShotsBefore) {
  throw new Error('Pawn Action Web: real keyboard SMG fire never reached Godot');
}
await page.keyboard.up('ArrowRight');
await page.waitForTimeout(120);
await capture('54-smg-idle');
await captureDetailedCloseup('54-smg-idle', smgStage.canvas);

// Cross-repository matched SMG frame: repeat the exact normal pickup path
// used by the legacy Chess Studio capture, not a pre-equipped gun at level start.
// Both captures use 1280x720, industrial_front_v1, spawn x=1170, the x=1240
// authored pickup and stop movement on the real Godot weapon-changed event.
const matchedStage = await loadStage(detailedStage, { pickupProbe: true });
const matchEvents = await page.evaluate(() => window.__pawnSlugCaptureEvents);
if (!matchEvents.includes('ready') || matchEvents.includes('weapon-changed')) {
  throw new Error('Matched Pawn Action pickup must begin with a ready pistol');
}
await matchedStage.canvasLocator.click({ position: {
  x: matchedStage.canvas.width / 2, y: matchedStage.canvas.height / 2,
} });
await page.keyboard.down('ArrowRight');
try {
  await page.waitForFunction(
    () => window.__pawnSlugCaptureEvents.includes('weapon-changed'),
    null, { timeout: 6500 },
  );
} finally {
  await page.keyboard.up('ArrowRight');
}
const pickupEvents = await page.evaluate(() => window.__pawnSlugCaptureEvents);
if (!pickupEvents.includes('weapon-pickup')) {
  throw new Error('Matched Pawn Action SMG did not emit real weapon-pickup');
}
let matchedFired = false;
for (let attempt = 0; attempt < 24 && !matchedFired; attempt += 1) {
  const before = await page.evaluate(() => window.__pawnSlugCaptureEvents.filter(
    type => type === 'player-fired').length);
  await page.keyboard.down('z');
  try { await page.waitForTimeout(240); }
  finally { await page.keyboard.up('z'); }
  matchedFired = await page.evaluate(previous =>
    window.__pawnSlugCaptureEvents.filter(type => type === 'player-fired').length > previous,
    before);
  if (!matchedFired) await page.waitForTimeout(450);
}
if (!matchedFired) {
  throw new Error('Matched Pawn Action SMG pickup never fired after 24 pulses');
}
await capture('57-smg-pickup-matched');
await captureDetailedCloseup('57-smg-pickup-matched', matchedStage.canvas, { followPlayer: true });
const matchedSmgProof = {
  method: 'pistol_ready_then_authored_pickup_at_x1240',
  stage: detailedStage, captureSpawnX: 1170, authoredPickupX: 1240,
  viewport: { width: 1280, height: 720 },
  screenshot: '57-smg-pickup-matched.png',
  ready: true, weaponPickup: true, weaponChanged: true,
  firedAfterPickup: true,
  events: await page.evaluate(() => window.__pawnSlugCaptureEvents.slice(-50)),
};

// Capture jump from a fresh, enemy-calm starting lane instead of the area
// reached after running and firing, where overhead platforms may cancel lift.
// A real Godot bridge event fires only after >=80 px of physics ascent.
const jumpStage = await loadStage(detailedStage, { weaponProbe: 'machinegun', jumpProbe: true });
if (!(await page.evaluate(() => window.__pawnSlugCaptureEvents.includes('weapon-changed')))) {
  throw new Error('SMG jump probe did not equip machinegun');
}
await jumpStage.canvasLocator.click({ position: { x: jumpStage.canvas.width / 2, y: jumpStage.canvas.height / 2 } });
const airborneBefore = await page.evaluate(() =>
  window.__pawnSlugCaptureEvents.filter((type) => type === 'player-airborne').length);
const landedBefore = await page.evaluate(() =>
  window.__pawnSlugCaptureEvents.filter((type) => type === 'player-landed').length);
// Chromium page.screenshot() blocks WebGL readback long enough to miss the
// entire 80px jump in both previous attempts. Record real compositor frames
// continuously with CDP; sample them into the existing PNG review contract.
const screencast = await page.context().newCDPSession(page);
const jumpFrames = [];
screencast.on('Page.screencastFrame', ({ data, sessionId }) => {
  if (jumpFrames.length < 160) jumpFrames.push(Buffer.from(data, 'base64'));
  void screencast.send('Page.screencastFrameAck', { sessionId }).catch(() => {});
});
await screencast.send('Page.startScreencast', {
  format: 'png', everyNthFrame: 1, maxWidth: 1280, maxHeight: 720,
});
try {
  await page.keyboard.down('ArrowRight');
  await page.keyboard.down('Space');
  // Capture the complete ascent, apex and landing. No sequential screenshots.
  await page.waitForTimeout(2600);
} finally {
  await page.keyboard.up('Space');
  await page.keyboard.up('ArrowRight');
  await screencast.send('Page.stopScreencast').catch(() => {});
  await screencast.detach().catch(() => {});
}
// Preserve the original compositor samples even when the frame-count or
// crop gate fails. They are the only trustworthy diagnosis of this visual path.
const screencastDir = `${outputDir}/jump-screencast-source`;
await mkdir(screencastDir, { recursive: true });
for (let i = 0; i < jumpFrames.length; i += 1) {
  await writeFile(`${screencastDir}/frame-${String(i).padStart(3, '0')}.png`, jumpFrames[i]);
}
await writeFile(`${screencastDir}/capture.json`, JSON.stringify({
  source: 'chromium-cdp-compositor', sourceFrameCount: jumpFrames.length,
  durationMs: 2600, selectedFrameCount: 16,
}, null, 2) + '\n');
if (jumpFrames.length < 16) {
  throw new Error('Chromium screencast delivered fewer than 16 real jump frames: ' + jumpFrames.length);
}
for (let frame = 0; frame < 16; frame += 1) {
  const label = `55-smg-jump-fall-${String(frame).padStart(2, '0')}`;
  const path = `${outputDir}/${label}.png`;
  const sampled = Math.round(frame * (jumpFrames.length - 1) / 15);
  await writeFile(path, jumpFrames[sampled]);
  captures.push({ label, path, kind: 'overview' });
}
execFileSync('python3', ['scripts/pawn_action_jump_screencast_crops.py', outputDir], {
  stdio: 'inherit',
});
for (const frame of [0, 3, 7, 11, 15]) {
  const label = `55-smg-jump-fall-${String(frame).padStart(2, '0')}-closeup`;
  captures.push({ label, path: `${outputDir}/${label}.png`, kind: 'player-closeup' });
}
const airborneAfter = await page.evaluate(() =>
  window.__pawnSlugCaptureEvents.filter((type) => type === 'player-airborne').length);
if (airborneAfter <= airborneBefore) {
  throw new Error('Real SMG jump never ascended 80px during compositor recording');
}
await page.waitForFunction((before) =>
  window.__pawnSlugCaptureEvents.filter((type) => type === 'player-landed').length > before,
  landedBefore, { timeout: 4_000 });
const landedAfter = await page.evaluate(() =>
  window.__pawnSlugCaptureEvents.filter((type) => type === 'player-landed').length);
await page.waitForTimeout(100);
await capture('56-smg-landed');
await captureDetailedCloseup('56-smg-landed', jumpStage.canvas, { followPlayer: true });
const jumpProof = {
  minHeightPx: 80, airborneBefore, airborneAfter, landedBefore, landedAfter,
};

// Capture one representative traversal sector where the new industrial
// ladder, pit mouth and stepping-route platforms share the same viewport.
// This is a real Godot runtime frame; the probe only chooses the starting X.
const traversalProbe = await loadStage(detailedStage, { visualProbe: true });
const traversalProbePath = `${outputDir}/stage-${detailedStage}-traversal.png`;
await page.screenshot({ path: traversalProbePath, fullPage: false });
stageOverviews.push({
  stageId: detailedStage,
  variant: 'traversal',
  url: traversalProbe.url,
  canvas: traversalProbe.canvas,
  path: traversalProbePath,
});

// Every shipped stage gets a first-screen visual proof. This keeps scenery,
// parallax and map-authored props reviewable without multiplying the expensive
// movement-frame sequence four times.
for (const stageId of stageIds.slice(1)) {
  const stage = await loadStage(stageId);
  const path = `${outputDir}/stage-${stageId}.png`;
  await page.screenshot({ path, fullPage: false });
  stageOverviews.push({ stageId, variant: 'overview', url: stage.url, canvas: stage.canvas, path });

  const traversal = await loadStage(stageId, { visualProbe: true });
  const traversalPath = `${outputDir}/stage-${stageId}-traversal.png`;
  await page.screenshot({ path: traversalPath, fullPage: false });
  stageOverviews.push({
    stageId,
    variant: 'traversal',
    url: traversal.url,
    canvas: traversal.canvas,
    path: traversalPath,
  });
}

await writeFile(
  `${outputDir}/runtime-visual-health.json`,
  `${JSON.stringify({
    schema: 7,
    detailedStage,
    jumpProof,
    matchedSmgProof,
    stageOverviews,
    captures,
  }, null, 2)}\n`,
  'utf8',
);

console.log(JSON.stringify({
  detailedStage,
  stageOverviews: stageOverviews.length,
  captures: captures.length,
  legacyOutputPath,
}));
await browser.close();
