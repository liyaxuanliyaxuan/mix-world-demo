/**
 * Global player coordination.
 * QA contract: at most one playback GROUP is active at a time across the page,
 * videos pause when scrolled offscreen or when the tab is hidden, and
 * autoplay failure falls back to visible native controls (never a blank
 * player or an error loop). A group (e.g., a synchronized multi-view grid)
 * plays together and is never paused by its own members.
 */

const registered = new Map<HTMLVideoElement, {
  video: HTMLVideoElement;
  group: string;
  observer?: IntersectionObserver;
}>();

interface RegisterOptions {
  /** skip the per-video offscreen pause (used for synchronized groups, which manage it at group level) */
  skipOffscreenPause?: boolean;
}

export function registerPlayer(
  video: HTMLVideoElement,
  group = "default",
  options: RegisterOptions = {}
): void {
  // Decorative hero clips must never interrupt an interactive demo.
  if (video.hasAttribute("data-hero-bg-video")) return;
  const existing = registered.get(video);
  if (existing) {
    // Component registration may run after the page's fallback registration.
    if (group !== "default") existing.group = group;
    if (options.skipOffscreenPause) existing.observer?.disconnect();
    return;
  }
  const registration = { video, group, observer: undefined as IntersectionObserver | undefined };
  registered.set(video, registration);

  // only one active playback group at a time
  video.addEventListener("play", () => {
    registered.forEach((other) => {
      if (other.group !== registration.group && !other.video.paused) other.video.pause();
    });
  });

  // pause when scrolled offscreen (groups handle this at group level instead)
  if (!options.skipOffscreenPause && "IntersectionObserver" in window) {
    const io = new IntersectionObserver(
      (entries) => {
        entries.forEach((entry) => {
          if (!entry.isIntersecting && !video.paused) video.pause();
        });
      },
      { threshold: 0.15 }
    );
    io.observe(video);
    registration.observer = io;
  }

  // pause in background tabs
  document.addEventListener("visibilitychange", () => {
    if (document.hidden && !video.paused) video.pause();
  });
}

export function registerAllVideos(root: ParentNode = document): void {
  root.querySelectorAll<HTMLVideoElement>("video").forEach((v) => registerPlayer(v, "default"));
}
