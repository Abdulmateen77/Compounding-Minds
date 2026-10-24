import { useEffect, useRef, useState } from "react";
import { AnimatePresence, motion } from "framer-motion";
import { useReducedMotion } from "../route";

const SRC = "/showcase-web.mp4";
const POSTER = "/showcase-poster.jpg";
const CAPTION = "Illustrative data: the accuracy chart in this clip is a mock-up, not real results.";

const PlayIcon = () => (
  <svg width="14" height="14" viewBox="0 0 14 14" aria-hidden><path d="M2 1.2v11.6L12.5 7z" fill="currentColor" /></svg>
);

/** Intro hero for the Select screen: muted looping preview plus a button that opens the full clip with sound. */
export function ShowcaseHero() {
  const reduced = useReducedMotion();
  const [failed, setFailed] = useState(false);
  const [open, setOpen] = useState(false);
  const btn = useRef<HTMLButtonElement>(null);

  return (
    <section aria-label="Product intro video" className="card overflow-hidden grid md:grid-cols-[1fr_1.15fr] items-stretch mb-8"
      style={{ background: "linear-gradient(135deg, color-mix(in srgb, var(--warm) 9%, var(--panel)), var(--panel))" }}>
      <div className="p-6 md:p-8 flex flex-col justify-center order-2 md:order-1">
        <h1 className="text-3xl md:text-4xl font-bold tracking-tight m-0">Is it investable?</h1>
        <p className="mute mt-3 mb-5 text-[15px] leading-relaxed max-w-md">
          A committee of AI analysts, each following a legendary investor&apos;s principles, reads the filings as they stood on the date you choose. Wrong calls are graded against what happened, and Mubit turns them into model updates.
        </p>
        <div className="flex items-center gap-3 flex-wrap">
          <button ref={btn} className="btn inline-flex items-center gap-2" style={{ background: "var(--warm)", color: "#1a1006" }} onClick={() => setOpen(true)}>
            <PlayIcon /> Watch how it works <span className="num text-xs opacity-70">0:23</span>
          </button>
          <a href="#/mubit" className="text-sm mute underline underline-offset-4">See what Mubit has taught them</a>
        </div>
      </div>

      <div className="relative order-1 md:order-2 min-h-[200px]" style={{ background: "#0b1020" }}>
        {failed || reduced ? (
          <img src={POSTER} alt="Four voxel-style analysts at their desks under the title Compounding Minds" className="w-full h-full object-cover block" onError={(e) => { e.currentTarget.style.display = "none"; }} />
        ) : (
          <video className="w-full h-full object-cover block" src={SRC} poster={POSTER} autoPlay muted loop playsInline preload="metadata"
            aria-label="Preview of the explainer clip, muted" onError={() => setFailed(true)} />
        )}
        <button aria-label="Open the explainer video with sound" onClick={() => setOpen(true)} className="absolute inset-0 w-full h-full cursor-pointer bg-transparent border-0" />
        <span className="chip absolute left-3 bottom-3" style={{ background: "color-mix(in srgb, var(--bg) 82%, transparent)", color: "var(--amber)", borderColor: "var(--amber)" }}>
          Illustrative data
        </span>
      </div>
      <p className="mute text-xs m-0 px-6 py-2 order-3 md:col-span-2" style={{ borderTop: "1px solid var(--line)" }}>{CAPTION}</p>

      <AnimatePresence>{open && <ShowcaseModal onClose={() => { setOpen(false); btn.current?.focus(); }} />}</AnimatePresence>
    </section>
  );
}

function ShowcaseModal({ onClose }: { onClose: () => void }) {
  const closeBtn = useRef<HTMLButtonElement>(null);
  const [err, setErr] = useState(false);

  useEffect(() => {
    closeBtn.current?.focus();
    const prev = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    const key = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
      if (e.key === "Tab") { // keep focus inside the dialog
        const els = Array.from(document.querySelectorAll<HTMLElement>("[data-modal] button, [data-modal] video, [data-modal] a"));
        if (!els.length) return;
        const first = els[0], last = els[els.length - 1];
        if (e.shiftKey && document.activeElement === first) { e.preventDefault(); last.focus(); }
        else if (!e.shiftKey && document.activeElement === last) { e.preventDefault(); first.focus(); }
      }
    };
    document.addEventListener("keydown", key);
    return () => { document.removeEventListener("keydown", key); document.body.style.overflow = prev; };
  }, [onClose]);

  return (
    <motion.div className="fixed inset-0 z-50 flex items-center justify-center p-4" style={{ background: "rgba(3,6,12,.82)" }}
      initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} onClick={onClose}>
      <motion.div data-modal role="dialog" aria-modal="true" aria-label="How Compounding Minds works" className="card w-full max-w-4xl overflow-hidden"
        initial={{ scale: 0.96, y: 10 }} animate={{ scale: 1, y: 0 }} exit={{ scale: 0.97, opacity: 0 }} onClick={(e) => e.stopPropagation()}>
        <div className="flex items-center justify-between px-4 py-3" style={{ borderBottom: "1px solid var(--line)" }}>
          <span className="font-semibold">How it works</span>
          <button ref={closeBtn} className="btn ghost" style={{ padding: ".35rem .8rem" }} onClick={onClose} aria-label="Close video">Close</button>
        </div>
        {err ? (
          <div className="p-8 text-center">
            <p className="m-0">The video could not be loaded.</p>
            <p className="mute text-sm mt-2"><a href={SRC} className="underline">Open the file directly</a> or try again later.</p>
          </div>
        ) : (
          <video src={SRC} poster={POSTER} controls autoPlay playsInline className="w-full block bg-black" style={{ aspectRatio: "16 / 9" }} onError={() => setErr(true)}>
            <track kind="captions" />
          </video>
        )}
        <p className="mute text-xs m-0 px-4 py-3" style={{ borderTop: "1px solid var(--line)" }}>{CAPTION}</p>
      </motion.div>
    </motion.div>
  );
}
