let audioContext: AudioContext | null = null;

function getContext() {
  if (typeof window === "undefined") return null;
  const AudioContextCtor = window.AudioContext || window.webkitAudioContext;
  if (!AudioContextCtor) return null;
  if (!audioContext) audioContext = new AudioContextCtor();
  return audioContext;
}

function beep(frequency: number, duration: number, type: OscillatorType) {
  const context = getContext();
  if (!context) return;

  const oscillator = context.createOscillator();
  const gain = context.createGain();
  oscillator.type = type;
  oscillator.frequency.value = frequency;
  gain.gain.setValueAtTime(0.0001, context.currentTime);
  gain.gain.exponentialRampToValueAtTime(0.08, context.currentTime + 0.01);
  gain.gain.exponentialRampToValueAtTime(0.0001, context.currentTime + duration);
  oscillator.connect(gain);
  gain.connect(context.destination);
  oscillator.start();
  oscillator.stop(context.currentTime + duration);
}

export function primeAudio() {
  void getContext()?.resume();
}

export function playCorrect(enabled: boolean) {
  if (!enabled) return;
  beep(880, 0.11, "sine");
  window.setTimeout(() => beep(1175, 0.12, "sine"), 90);
}

export function playWrong(enabled: boolean) {
  if (!enabled) return;
  beep(180, 0.16, "sawtooth");
}

export function playClear(enabled: boolean) {
  if (!enabled) return;
  beep(660, 0.1, "triangle");
  window.setTimeout(() => beep(990, 0.12, "triangle"), 90);
  window.setTimeout(() => beep(1320, 0.14, "triangle"), 190);
}

declare global {
  interface Window {
    webkitAudioContext?: typeof AudioContext;
  }
}
