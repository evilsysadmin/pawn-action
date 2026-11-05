/** Probe real browser input after Chess Studio's authored SMG pickup.
 * Success is ONLY a real Godot player-fired bridge event after pickup.
 */
export const SMG_FIRE_PHASES = Object.freeze([
  Object.freeze({ name:'keyboard-z', kind:'key', value:'z', timeoutMs:2800 }),
  Object.freeze({ name:'keyboard-j', kind:'key', value:'j', timeoutMs:2800 }),
  Object.freeze({ name:'mouse-left', kind:'mouse', timeoutMs:2800 }),
]);

export async function probeRealSmgFire(page, readShots) {
  if (typeof readShots !== 'function') throw new Error('Missing Godot fire-event reader');
  const attempts = [];
  const startingShots = await readShots();
  if (!Number.isSafeInteger(startingShots) || startingShots < 0) {
    throw new Error('Invalid Godot fire-event counter');
  }
  let fired = false;
  for (const phase of SMG_FIRE_PHASES) {
    await page.bringToFront();
    await page.locator('canvas').focus();
    const before = await readShots();
    if (before > startingShots) { fired = true; break; }
    if (phase.kind === 'key') await page.keyboard.down(phase.value);
    else {
      await page.mouse.move(640, 360);
      await page.mouse.down({button:'left'});
    }
    let timeout = false;
    try {
      await page.waitForFunction(
        prev => window.__legacyEvents.filter(type => type === 'player-fired').length > prev,
        before, {timeout:phase.timeoutMs, polling:80},
      );
    } catch(error) {
      if (error?.name !== 'TimeoutError' &&
          !/Timeout \d+ms exceeded/.test(String(error?.message))) throw error;
      timeout = true;
    } finally {
      if (phase.kind === 'key') await page.keyboard.up(phase.value);
      else await page.mouse.up({button:'left'});
    }
    const after = await readShots();
    if (!Number.isSafeInteger(after) || after < before) {
      throw new Error('Inconsistent Godot fire-event counter');
    }
    attempts.push({input:phase.name, timeout,
      shotsBefore:before, shotsAfter:after, fired:after>before});
    if (after>before) {fired=true;break;}
  }
  return {fired,attempts,startingShots,finalShots:await readShots()};
}
