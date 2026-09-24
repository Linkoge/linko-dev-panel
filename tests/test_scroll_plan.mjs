import assert from 'node:assert/strict';
import test from 'node:test';
import {nextScrollPosition} from '../scroll_plan.mjs';

function positions(height, overlap, bottom, regions = []) {
  const samples = [0];
  while (samples.at(-1) < bottom && samples.length < 100) {
    samples.push(nextScrollPosition(samples.at(-1), bottom, height, overlap, regions));
  }
  return samples;
}

test('ordinary and long pages use the configured overlap and reach the bottom', () => {
  assert.deepEqual(positions(1000, 20, 2400), [0, 800, 1600, 2400]);
  assert.equal(positions(844, 20, 15000).at(-1), 15000);
  assert.equal(positions(900, 20, 15000).at(-1), 15000);
});

test('a normal sticky header does not change page intervals', () => {
  assert.deepEqual(positions(1000, 20, 2400, []), [0, 800, 1600, 2400]);
});

test('Linko-sized four-state sticky stage includes every state for mobile and desktop', () => {
  for (const height of [844, 900]) {
    for (const offset of [150, 430, 710, 1030]) {
      const region = {top: offset, end: offset + height * 3};
      const samples = positions(height, 20, region.end + height * 2, [region]);
      assert.ok(samples.includes(offset));
      const stages = new Set(samples.filter(y => y >= region.top && y < region.end)
        .map(y => Math.floor((y - region.top) / (height * 3) * 4)));
      assert.deepEqual([...stages].sort(), [0, 1, 2, 3]);
      assert.equal(samples.at(-1), region.end + height * 2);
    }
  }
});
