// one context for the app; browsers only let it play after the person has used the page
let context: AudioContext | null = null;

/** A completed task: two rising notes. */
export const CHIME = [880, 1318.5];
/** A new ticket: a lower, three-note figure, so it can be told apart without looking. */
export const NEW_TICKET_TONE = [659.25, 880, 659.25];

/**
 * Whether the page may play sound now. Browsers block audio until the person has
 * clicked or typed on the page; where the browser can't say, try and let
 * playNotificationSound fail quietly.
 */
export function canPlaySound(): boolean {
  return navigator.userActivation?.hasBeenActive ?? true;
}

/**
 * A short tone made in the browser, so no sound file ships with the app.
 * Fails silently when audio is blocked or unsupported; the bell still updates.
 */
export function playNotificationSound(notes: number[] = CHIME) {
  try {
    context ??= new AudioContext();
    if (context.state === "suspended") void context.resume();
    const start = context.currentTime;
    notes.forEach((frequency, i) => {
      const osc = context!.createOscillator();
      const gain = context!.createGain();
      const at = start + i * 0.12;
      osc.type = "sine";
      osc.frequency.value = frequency;
      gain.gain.setValueAtTime(0.0001, at);
      gain.gain.exponentialRampToValueAtTime(0.15, at + 0.02);
      gain.gain.exponentialRampToValueAtTime(0.0001, at + 0.35);
      osc.connect(gain).connect(context!.destination);
      osc.start(at);
      osc.stop(at + 0.4);
    });
  } catch {
    // no audio here; nothing else depends on it
  }
}
