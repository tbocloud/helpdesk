// The ring sounds of the call box, made in the browser (no sound file, no library). Only the
// ring is heard here: the conversation itself is on the person's phone.
import { useLocalStorage } from "@vueuse/core";
import { watch } from "vue";

export type RingKind = "ringback" | "incoming";

/** Mute is remembered on this device. */
export const ringMuted = useLocalStorage("call-box-muted", false);

// each kind: its notes as [Hz, seconds from the cycle's start, seconds long], the cycle's
// length and a modest volume. Ringback is the soft double burst of a phone ringing; the
// incoming ring is higher and brighter, so the two can be told apart without looking.
const PATTERNS: Record<
  RingKind,
  { notes: [number, number, number][]; cycle: number; volume: number }
> = {
  ringback: {
    notes: [
      [425, 0, 0.4],
      [425, 0.6, 0.4],
    ],
    cycle: 3,
    volume: 0.05,
  },
  incoming: {
    notes: [
      [880, 0, 0.25],
      [660, 0.3, 0.25],
      [880, 0.6, 0.25],
      [660, 0.9, 0.25],
    ],
    cycle: 2.4,
    volume: 0.1,
  },
};

let context: AudioContext | null = null;
let timer: ReturnType<typeof setInterval> | undefined;
let playing: RingKind | null = null;

/** Called from the Call click, so the browser allows the sound that follows. */
export function prepareRing() {
  try {
    context ??= new AudioContext();
    if (context.state === "suspended") void context.resume();
  } catch {
    // no audio here; the box still shows everything
  }
}

function burst([hz, at, length]: [number, number, number], volume: number) {
  const ctx = context;
  if (!ctx) return;
  const start = ctx.currentTime + at;
  const osc = ctx.createOscillator();
  const gain = ctx.createGain();
  osc.type = "sine";
  osc.frequency.value = hz;
  gain.gain.setValueAtTime(0.0001, start);
  gain.gain.exponentialRampToValueAtTime(volume, start + 0.03);
  gain.gain.setValueAtTime(volume, start + length - 0.05);
  gain.gain.exponentialRampToValueAtTime(0.0001, start + length);
  osc.connect(gain).connect(ctx.destination);
  osc.start(start);
  osc.stop(start + length + 0.02);
}

function cycle(kind: RingKind) {
  // a browser that hasn't allowed sound yet stays silent: nothing queues up to play later
  if (!context || context.state !== "running") return;
  const { notes, volume } = PATTERNS[kind];
  notes.forEach((note) => burst(note, volume));
}

/** Loops the ring until stopRing. Silent when muted or when the browser doesn't allow sound. */
export function startRing(kind: RingKind) {
  if (playing === kind) return;
  stopRing();
  playing = kind;
  if (ringMuted.value) return;
  try {
    prepareRing();
    cycle(kind);
    timer = setInterval(() => cycle(kind), PATTERNS[kind].cycle * 1000);
  } catch {
    // a refused sound is not an error
  }
}

/** Stops the ring; with `kind`, only when it is that one that is playing. */
export function stopRing(kind?: RingKind) {
  if (kind && playing !== kind) return;
  clearInterval(timer);
  timer = undefined;
  playing = null;
}

// muting stops the ring that is on; unmuting brings it back
watch(ringMuted, (muted) => {
  const kind = playing;
  if (!kind) return;
  stopRing();
  if (!muted) startRing(kind);
  else playing = kind;
});
