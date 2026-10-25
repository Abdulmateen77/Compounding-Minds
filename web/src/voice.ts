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

/** Play one line in this investor's voice ("judge" for the judge). Resolves when it finishes, or rejects if voices are off. */
export async function speak(investor: string, text: string, signal?: AbortSignal): Promise<void> {
  const r = await fetch("/api/voice", { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify({ investor, text }), signal });
  if (!r.ok) throw new Error((await r.json().catch(() => ({ detail: r.statusText }))).detail ?? r.statusText);
  const url = URL.createObjectURL(await r.blob());
  stopSpeaking();
  const audio = new Audio(url);
  current = audio;
  await new Promise<void>((resolve, reject) => {
    audio.onended = () => resolve();
    audio.onerror = () => reject(new Error("could not play the audio"));
    signal?.addEventListener("abort", () => { audio.pause(); resolve(); });
    audio.play().catch(reject);
  }).finally(() => URL.revokeObjectURL(url));
}

export type Line = { investor: string; name: string; text: string };

/** Play a debate line by line, in each speaker's voice. `onLine` reports which line is playing (or null at the end). */
export async function playDebate(lines: Line[], onLine: (i: number | null) => void, signal: AbortSignal) {
  try {
    for (let i = 0; i < lines.length; i++) {
      if (signal.aborted) break;
      onLine(i);
      await speak(lines[i].investor, lines[i].text, signal);
    }
  } finally {
    onLine(null);
  }
}
