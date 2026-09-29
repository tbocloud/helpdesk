import { __ } from "@/translation";

/** Mirrors the vendored copy in helpdesk/public/js/lib/rrweb-player (see its README). */
const PLAYER_VERSION = "2.1.6";
const PLAYER_BASE = "/assets/helpdesk/js/lib/rrweb-player";

export interface ReplayEvent {
  type: number;
  timestamp: number;
  data?: unknown;
}

export interface RrwebPlayerOptions {
  target: HTMLElement;
  props: {
    events: ReplayEvent[];
    width?: number;
    height?: number;
    autoPlay?: boolean;
    skipInactive?: boolean;
    showController?: boolean;
    tags?: Record<string, string>;
    [key: string]: unknown;
  };
}

export interface RrwebPlayer {
  $destroy?: () => void;
  $set?: (props: Record<string, unknown>) => void;
  pause?: () => void;
  triggerResize?: () => void;
}

type RrwebPlayerConstructor = new (options: RrwebPlayerOptions) => RrwebPlayer;

declare global {
  interface Window {
    rrwebPlayer?: {
      default?: RrwebPlayerConstructor;
      Player?: RrwebPlayerConstructor;
    };
  }
}

/** An error whose message is safe to show to the agent as is. */
export class ReplayError extends Error {}

let playerPromise: Promise<RrwebPlayerConstructor> | null = null;

function playerFromWindow(): RrwebPlayerConstructor | undefined {
  return window.rrwebPlayer?.default ?? window.rrwebPlayer?.Player;
}

function addStylesheet(href: string) {
  if (document.querySelector(`link[href="${href}"]`)) return;
  const link = document.createElement("link");
  link.rel = "stylesheet";
  link.href = href;
  document.head.appendChild(link);
}

/**
 * Loads the vendored rrweb-player on first use. It is ~230 KB and only needed
 * when an agent actually watches a replay, so it stays out of the desk bundle.
 */
export function loadRrwebPlayer(): Promise<RrwebPlayerConstructor> {
  const loaded = playerFromWindow();
  if (loaded) return Promise.resolve(loaded);
  if (playerPromise) return playerPromise;

  addStylesheet(`${PLAYER_BASE}/style.min.css?v=${PLAYER_VERSION}`);
  playerPromise = new Promise((resolve, reject) => {
    const script = document.createElement("script");
    script.src = `${PLAYER_BASE}/rrweb-player.min.js?v=${PLAYER_VERSION}`;
    script.async = true;
    script.onload = () => {
      const player = playerFromWindow();
      if (player) resolve(player);
      else reject(new ReplayError(__("The replay player could not start.")));
    };
    script.onerror = () => {
      // let the next attempt retry instead of reusing a failed load
      playerPromise = null;
      script.remove();
      reject(new ReplayError(__("The replay player could not be loaded.")));
    };
    document.head.appendChild(script);
  });
  return playerPromise;
}

function isGzip(bytes: Uint8Array): boolean {
  return bytes[0] === 0x1f && bytes[1] === 0x8b;
}

async function gunzip(bytes: Uint8Array): Promise<string> {
  if (typeof DecompressionStream === "undefined") {
    throw new ReplayError(
      __("This browser can't open session replays. Try a current Chrome, Edge, Firefox or Safari.")
    );
  }
  const stream = new Blob([bytes])
    .stream()
    .pipeThrough(new DecompressionStream("gzip"));
  return new Response(stream).text();
}

/** Downloads the private session-replay.json.gz and returns its rrweb events. */
export async function fetchReplayEvents(url: string): Promise<ReplayEvent[]> {
  const response = await fetch(url, { credentials: "same-origin" });
  if (!response.ok) {
    throw new ReplayError(
      response.status === 403
        ? __("You don't have access to this replay.")
        : __("The replay file could not be downloaded.")
    );
  }
  const bytes = new Uint8Array(await response.arrayBuffer());

  let replay: unknown;
  try {
    // a proxy may already have inflated it in transit
    const text = isGzip(bytes)
      ? await gunzip(bytes)
      : new TextDecoder().decode(bytes);
    replay = JSON.parse(text);
  } catch (error) {
    if (error instanceof ReplayError) throw error;
    throw new ReplayError(__("The replay file is damaged and can't be played."));
  }

  const events = Array.isArray(replay)
    ? replay
    : (replay as { events?: unknown })?.events;
  const playable =
    Array.isArray(events) &&
    events.length > 1 &&
    events.some((event) => (event as ReplayEvent)?.type === 2);
  if (!playable) {
    throw new ReplayError(__("This replay has nothing to play."));
  }
  return events as ReplayEvent[];
}

/** Resolved theme colours for the player's timeline markers (it needs real CSS colours). */
export function replayMarkerColors(): Record<string, string> {
  const styles = getComputedStyle(document.documentElement);
  const token = (name: string, fallback: string) =>
    styles.getPropertyValue(name).trim() || fallback;
  return {
    "frappe-call-error": token("--danger", "#bf3328"),
    "frappe-msgprint": token("--warning", "#955700"),
    "raise-ticket": token("--brand", "#4f46e5"),
  };
}
