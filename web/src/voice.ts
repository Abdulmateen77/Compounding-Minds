/** Investor voices (ElevenLabs, through our server: the key never reaches the browser). The foundation for spoken debates:
    `speak` plays one line in an investor's voice and resolves when it ends; `useVoiceStatus` says whether voices are on. */
import { useQuery } from "@tanstack/react-query";

export type VoiceStatus = { enabled: boolean; voices: Record<string, { label: string; persona: string }> };

export function useVoiceStatus() {
  return useQuery({
    queryKey: ["voice-status"], staleTime: 5 * 60_000, retry: 0,
    queryFn: async (): Promise<VoiceStatus> => { const r = await fetch("/api/voice/status"); if (!r.ok) throw new Error(); return r.json(); },
  });
}

let current: HTMLAudioElement | null = null;

export function stopSpeaking() {
  if (current) { current.pause(); current.src = ""; current = null; }
}

/** Fetch one line in this investor's voice ("judge" for the judge) and return a playable URL. Rejects if voices are off.
    Fetching is the slow part, so callers fetch the next line while the current one plays. */
export async function fetchVoice(investor: string, text: string, signal?: AbortSignal): Promise<string> {
  const r = await fetch("/api/voice", { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify({ investor, text }), signal });
  if (!r.ok) throw new Error((await r.json().catch(() => ({ detail: r.statusText }))).detail ?? r.statusText);
  return URL.createObjectURL(await r.blob());
}

/** Play a fetched line at once. Resolves when it finishes (or on abort) and frees the URL. */
export async function playVoice(url: string, signal?: AbortSignal, rate = 1): Promise<void> {
  try {
    if (signal?.aborted) return;
    stopSpeaking();
    const audio = new Audio(url);
    audio.playbackRate = rate;   // faster without a higher pitch (Eleven v4 has no speed setting)
    audio.preservesPitch = true;
    current = audio;
    await new Promise<void>((resolve, reject) => {
      audio.onended = () => resolve();
      audio.onerror = () => reject(new Error("could not play the audio"));
      signal?.addEventListener("abort", () => { audio.pause(); resolve(); });
      audio.play().catch(reject);
    });
  } finally {
    URL.revokeObjectURL(url);
  }
}

/** Fetch and play one line. Resolves when it finishes, or rejects if voices are off. */
export async function speak(investor: string, text: string, signal?: AbortSignal, rate = 1): Promise<void> {
  await playVoice(await fetchVoice(investor, text, signal), signal, rate);
}

export type Line = { investor: string; name: string; text: string };

/** Play a debate line by line, in each speaker's voice. `onLine` reports which line is playing (or null at the end).
    A line is reported only once its audio is ready, so the text and the voice start together, and the next line is fetched while this one plays. */
export async function playDebate(lines: Line[], onLine: (i: number | null) => void, signal: AbortSignal, rate = 2) {
  const fetchLine = (i: number) => (i < lines.length ? fetchVoice(lines[i].investor, lines[i].text, signal) : null);
  let next: Promise<string> | null = fetchLine(0);
  next?.catch(() => {});   // a failure is raised where the line is awaited, not as an unhandled rejection
  try {
    for (let i = 0; i < lines.length; i++) {
      if (signal.aborted) break;
      const url = await next!;
      next = fetchLine(i + 1);
      next?.catch(() => {});
      if (signal.aborted) { URL.revokeObjectURL(url); break; }
      onLine(i);
      await playVoice(url, signal, rate);
    }
  } finally {
    onLine(null);
  }
}
