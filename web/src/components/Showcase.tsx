import { useEffect, useRef, useState } from "react";
import { AnimatePresence, motion } from "framer-motion";
import { useReducedMotion } from "../route";

const SRC = "/showcase-web.mp4";
const POSTER = "/showcase-poster.jpg";
const CAPTION = "The call and the lesson in this clip are an example. The scores at the end are the real 2023-24 held-out results.";

const PlayIcon = () => (
  <svg width="14" height="14" viewBox="0 0 14 14" aria-hidden><path d="M2 1.2v11.6L12.5 7z" fill="currentColor" /></svg>
);

/** Homepage explainer: muted looping preview that opens the full clip, with sound, in a dialog. */
export function ShowcaseVideo() {
  const reduced = useReducedMotion();
  const [failed, setFailed] = useState(false);
  const [open, setOpen] = useState(false);
  const btn = useRef<HTMLButtonElement>(null);

  return (
    <figure aria-label="Product intro video" className="m-0 grid gap-3 self-center">
      <div className="relative overflow-hidden rounded-xl" style={{ aspectRatio: "16 / 9", background: "#0b1020", border: "1px solid var(--divider)" }}>
        {failed || reduced ? (
          <img src={POSTER} alt="Four voxel-style analysts at their desks under the title Compounding Minds" className="w-full h-full object-cover block" onError={(e) => { e.currentTarget.style.display = "none"; }} />
        ) : (
          <video className="w-full h-full object-cover block" src={SRC} poster={POSTER} autoPlay muted loop playsInline preload="metadata"
            aria-label="Preview of the explainer clip, muted" onError={() => setFailed(true)} />
        )}
        <button ref={btn} aria-label="Watch the explainer video with sound" onClick={() => setOpen(true)}
          className="group absolute inset-0 w-full h-full cursor-pointer bg-transparent border-0 grid place-items-center">
          <span className="grid place-items-center w-14 h-14 rounded-full transition-transform duration-200 group-hover:scale-110 group-focus-visible:scale-110"
            style={{ background: "var(--accent)", color: "#1a1006", boxShadow: "0 6px 24px rgba(0,0,0,.45)" }}><PlayIcon /></span>
        </button>
        <span className="chip absolute left-3 top-3" style={{ background: "color-mix(in srgb, var(--background) 82%, transparent)", color: "var(--warning)", borderColor: "var(--warning)" }}>
          Example call, real scores
        </span>
      </div>
      <figcaption className="flex items-center justify-between gap-x-4 gap-y-1 flex-wrap text-sm">
        <span className="font-semibold">See how it works <span className="num mute font-normal">0:23</span></span>
        <a href="#/mubit" className="mute underline underline-offset-4">Read the real track record</a>
      </figcaption>
      <AnimatePresence>{open && <ShowcaseModal onClose={() => { setOpen(false); btn.current?.focus(); }} />}</AnimatePresence>
    </figure>
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
    <motion.div className="fixed inset-0 z-[var(--z-modal)] flex items-center justify-center p-4" style={{ background: "rgba(3,6,12,.82)" }}
      initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} onClick={onClose}>
      <motion.div data-modal role="dialog" aria-modal="true" aria-label="How Compounding Minds works" className="card w-full max-w-4xl overflow-hidden"
        initial={{ scale: 0.96, y: 10 }} animate={{ scale: 1, y: 0 }} exit={{ scale: 0.97, opacity: 0 }} onClick={(e) => e.stopPropagation()}>
        <div className="flex items-center justify-between px-4 py-3" style={{ borderBottom: "1px solid var(--divider)" }}>
          <span className="font-semibold">How it works</span>
          <button ref={closeBtn} className="btn ghost sm" onClick={onClose} aria-label="Close video">Close</button>
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
        <p className="mute text-xs m-0 px-4 py-3" style={{ borderTop: "1px solid var(--divider)" }}>{CAPTION}</p>
      </motion.div>
    </motion.div>
  );
}
