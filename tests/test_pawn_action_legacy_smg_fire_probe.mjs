import assert from 'node:assert/strict';
import {test} from 'node:test';
import {probeRealSmgFire, SMG_FIRE_PHASES} from '../scripts/pawn_action_legacy_smg_fire_probe.mjs';

function fake(success=null, unexpected=false) {
  let shots=0, held=null;
  const downs=[], ups=[], focuses=[];
  const page={
    bringToFront:async()=>focuses.push('window'),
    locator:()=>({focus:async()=>focuses.push('canvas')}),
    keyboard:{
      down:async key=>{downs.push(key);held=key;},
      up:async key=>{ups.push(key);held=null;},
    },
    mouse:{
      move:async()=>{},
      down:async()=>{downs.push('mouse');held='mouse';},
      up:async()=>{ups.push('mouse');held=null;},
    },
    waitForFunction:async()=>{
      if(unexpected)throw new Error('Browser crashed');
      if(held===success){shots++;return;}
      const error=new Error('page.waitForFunction: Timeout 2800ms exceeded');
      error.name='TimeoutError';throw error;
    },
  };
  return {page,readShots:async()=>shots,downs,ups,focuses};
}
test('J fallback counts only real post-input Godot firing',async()=>{
  const x=fake('j'),r=await probeRealSmgFire(x.page,x.readShots);
  assert.equal(r.fired,true);
  assert.deepEqual(r.attempts.map(a=>a.input),['keyboard-z','keyboard-j']);
  assert.deepEqual(r.attempts.map(a=>a.fired),[false,true]);
  assert.deepEqual(x.downs,['z','j']);assert.deepEqual(x.ups,x.downs);
  assert.equal(x.focuses.length,4);
});
test('all three inputs without a bridge shot remain unverified',async()=>{
  const x=fake(),r=await probeRealSmgFire(x.page,x.readShots);
  assert.equal(r.fired,false);assert.equal(r.finalShots,0);
  assert.equal(r.attempts.length,SMG_FIRE_PHASES.length);
  assert.deepEqual(x.downs,['z','j','mouse']);assert.deepEqual(x.ups,x.downs);
});
test('unexpected error propagates and releases held input',async()=>{
  const x=fake(null,true);
  await assert.rejects(probeRealSmgFire(x.page,x.readShots),/Browser crashed/);
  assert.deepEqual(x.ups,['z']);
});
