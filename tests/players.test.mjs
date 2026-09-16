import test from 'node:test';
import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import { runInNewContext } from 'node:vm';
import { transform } from 'esbuild';

const source = await readFile(new URL('../src/scripts/players.ts', import.meta.url), 'utf8');
const { code } = await transform(source, { loader: 'ts', format: 'cjs' });

function setup() {
  const observers = [];
  class Observer {
    constructor(callback) { this.callback = callback; observers.push(this); }
    observe(target) { this.target = target; }
    disconnect() { this.disconnected = true; }
  }
  class Video extends EventTarget {
    constructor(hero = false) { super(); this.hero = hero; this.paused = true; }
    hasAttribute(name) { return name === 'data-hero-bg-video' && this.hero; }
    play() { this.paused = false; this.dispatchEvent(new Event('play')); }
    pause() { this.paused = true; this.dispatchEvent(new Event('pause')); }
  }
  const document = new EventTarget();
  const module = { exports: {} };
  runInNewContext(code, { module, exports: module.exports, document, window: { IntersectionObserver: Observer }, IntersectionObserver: Observer });
  return { ...module.exports, Video, document, observers };
}

test('hero rotation cannot pause an action video, including fallback registration', () => {
  const { registerAllVideos, registerPlayer, Video } = setup();
  const action = new Video();
  const backgrounds = Array.from({ length: 4 }, () => new Video(true));
  registerAllVideos({ querySelectorAll: () => [action, ...backgrounds] });
  registerPlayer(action, 'actions');
  action.play();
  for (const hero of backgrounds) {
    registerPlayer(hero, 'hero');
    hero.play();
    assert.equal(action.paused, false);
    hero.pause();
  }
});

test('late component registration preserves synchronized views and group exclusivity', () => {
  const { registerAllVideos, registerPlayer, Video, observers } = setup();
  const [left, right, action] = Array.from({ length: 3 }, () => new Video());
  registerAllVideos({ querySelectorAll: () => [left, right, action] });
  registerPlayer(left, 'views', { skipOffscreenPause: true });
  registerPlayer(right, 'views', { skipOffscreenPause: true });
  registerPlayer(action, 'actions');
  assert.equal(observers[0].disconnected, true);
  assert.equal(observers[1].disconnected, true);
  left.play(); right.play();
  assert.equal(left.paused, false);
  assert.equal(right.paused, false);
  action.play();
  assert.equal(left.paused, true);
  assert.equal(right.paused, true);
  // A second fallback pass must not replace the explicit group.
  registerAllVideos({ querySelectorAll: () => [left, right, action] });
  left.play();
  assert.equal(action.paused, true);
  right.play();
  assert.equal(left.paused, false);
});

test('interactive videos still pause offscreen and in a hidden document', () => {
  const { registerPlayer, Video, observers, document } = setup();
  const video = new Video();
  registerPlayer(video, 'actions');
  video.play();
  observers[0].callback([{ isIntersecting: false }]);
  assert.equal(video.paused, true);
  video.play();
  document.hidden = true;
  document.dispatchEvent(new Event('visibilitychange'));
  assert.equal(video.paused, true);
});
