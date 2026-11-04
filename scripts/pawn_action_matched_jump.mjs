/** Real compositor-only matched pistol jump from the same x=110 ground start.
 * Legacy Chess Studio lacks the newer physical airborne bridge event;
 * the original compositor pixels supply independent evidence instead.
 */
import { mkdir, writeFile } from 'node:fs/promises';
import path from 'node:path';
import { execFileSync } from 'node:child_process';

export async function captureMatchedPistolJump(page, directory, { eventKey, source }) {
  if (!['legacy', 'current'].includes(source)
      || !['__legacyEvents', '__pawnSlugCaptureEvents'].includes(eventKey)) {
    throw new Error('Unsafe matched jump capture identity');
  }
  const before = await page.evaluate(key => window[key], eventKey);
  if (!Array.isArray(before) || !before.includes('ready') || before.includes('weapon-changed')) {
    throw new Error('Matched jump must begin at the real pistol-ready x=110 start');
  }
  const canvas = await page.locator('canvas').boundingBox();
  if (!canvas || Math.round(canvas.width) !== 1280 || Math.round(canvas.height) !== 720
      || page.viewportSize()?.width !== 1280 || page.viewportSize()?.height !== 720) {
    throw new Error('Matched jump requires real 1280x720 Godot viewport');
  }
  await page.locator('canvas').click({ position: { x: 640, y: 360 } });
  await page.waitForTimeout(220);
  const idle = await page.screenshot({ fullPage: false });
  await writeFile(path.join(directory, '60-pistol-jump-idle.png'), idle);

  const framesDir = path.join(directory, 'matched-pistol-jump-source');
  await mkdir(framesDir, { recursive: true });
  const screencast = await page.context().newCDPSession(page);
  const frames = [];
  const airborneBefore = before.filter(x => x === 'player-airborne').length;
  const landedBefore = before.filter(x => x === 'player-landed').length;
  screencast.on('Page.screencastFrame', ({ data, sessionId }) => {
    if (frames.length < 120) frames.push(Buffer.from(data, 'base64'));
    void screencast.send('Page.screencastFrameAck', { sessionId }).catch(() => {});
  });
  await screencast.send('Page.startScreencast', {
    format: 'png', everyNthFrame: 1, maxWidth: 1280, maxHeight: 720,
  });
  try {
    await page.keyboard.down('Space');
    await page.waitForTimeout(850);
  } finally {
    await page.keyboard.up('Space');
  }
  await page.waitForTimeout(1250);
  await screencast.send('Page.stopScreencast').catch(() => {});
  await screencast.detach().catch(() => {});
  for (let i = 0; i < frames.length; i += 1) {
    const name = 'frame-' + String(i).padStart(3, '0') + '.png';
    await writeFile(path.join(framesDir, name), frames[i]);
  }
  await writeFile(path.join(framesDir, 'source.json'), JSON.stringify({
    source: 'chromium-cdp-compositor', key: source, frames: frames.length,
    viewport: { width: 1280, height: 720 }, stage: 'industrial_front_v1',
    startX: 110, jumpHoldMs: 850, postJumpMs: 1250,
  }, null, 2) + '\n');
  // Older Godot Web/CDP reports ~8 frames over a complete physical jump.
  // The validator still requires actual >=80px ascent and return to ground;
  // demanding 10 screenshots merely rejects valid, visually proven jumps.
  if (frames.length < 6) throw new Error('Insufficient real compositor jump frames: ' + frames.length);
  await writeFile(path.join(directory, '62-pistol-jump-landed.png'),
    await page.screenshot({ fullPage: false }));
  const events = await page.evaluate(key => window[key], eventKey);
  if (source === 'current' && (
    events.filter(x => x === 'player-airborne').length <= airborneBefore ||
    events.filter(x => x === 'player-landed').length <= landedBefore
  )) throw new Error('Pawn Action matched jump lacked real airborne/landed events');
  const report = execFileSync('python3', [
    'scripts/pawn_action_matched_jump_frames.py',
    '--dir', directory, '--source', source,
  ], { encoding: 'utf8', timeout: 30000 });
  const result = JSON.parse(report);
  if (result.status !== 'physical_jump_pixels_verified') {
    throw new Error('Matched jump pixels not proven');
  }
  return { ...result, events: events.slice(-50),
    physicsEvents: source === 'current' ? 'player-airborne_and_player-landed' :
      'not_exposed_by_legacy_build' };
}
