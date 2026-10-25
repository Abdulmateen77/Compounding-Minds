import type { Check, Lens } from "../research";
import { checkLabel, cut, surname } from "../scene/lenses";

/* The investors speak for themselves on the Investor panel: their call, why, and the checks behind it, in the first person. Every
   fact is still the report's (the check, what was found, the call); only the wording turns from "this investor" into "I". */

const CALL_SAID: Record<string, string> = { invest: "I would invest", wait: "I would wait", avoid: "I would not invest" };

/** "Would wait" as they would say it. */
export const myCall = (l: Lens) =>
  !l.decision ? `My reading: ${l.word.toLowerCase()}` : l.decision.label === "Not enough data" ? "I can't make a call yet" : CALL_SAID[l.decision.call];

/** The call's reason in the first person ("Passes most of this investor's checks" becomes "It passes most of my checks"). */
export function myWhy(l: Lens) {
  const why = (l.decision?.why ?? "").replace(/\.$/, "");
  if (!why) return "";
  return why
    .replace(/this investor's checks/g, "my checks")
    .replace(/^Passes most checks/, "It passes most of my checks")
    .replace(/^Passes/, "It passes")
    .replace(/^Fails/, "It fails")
    .replace(/^Some checks pass and some fail: not enough to commit/, "Some of my checks pass and some fail, not enough for me to commit");
}

/** A check's name as said aloud: a trailing bracketed hint ("(half is very good, double is a warning)") is dropped, cut or not. */
const tidy = (head: string) => head.replace(/\s*\([^)]*(\)|…)?\s*$/, "").replace(/…$/, "").trim();

/** One spoken fact from a check's name and what was found: "Short cash runway while debt rises? Not burning cash." */
export const fact = (head: string, shown: string) => { const h = tidy(head); return `${h}${/[?:]$/.test(h) ? "" : ":"} ${shown}`; };

/** One check as a spoken fact. */
export const said = (k: Check) => fact(checkLabel(k), cut(k.shown, 96));

/** The checks that count for and against, strongest first: passes in its favour, fails then partials against it. */
export function forAndAgainst(l: Lens, n = 3) {
  const by = (r: Check["result"]) => l.checks.filter((k) => k.result === r);
  return { pros: by("pass").slice(0, n), cons: [...by("fail"), ...by("partial")].slice(0, n) };
}

/** Their opening statement: the call and why, then the strongest point each way. */
export function opening(l: Lens) {
  const { pros, cons } = forAndAgainst(l, 1), why = myWhy(l);
  return [
    `${myCall(l)}${why ? `. ${why}` : ""}.`,
    pros[0] ? `In its favour: ${said(pros[0])}.` : "",
    cons[0] ? `Against it: ${said(cons[0])}.` : "",
  ].filter(Boolean).join(" ");
}

/** "What I'd watch next", turning the written view's "Munger would watch..." into "I would watch...". Null if it does not start
    with their name, so a third-person sentence is never put in their mouth. */
export function myWatch(l: Lens) {
  const s = l.ahead?.trim().match(/^[\s\S]+?[.!?](?=\s+[A-Z“"]|\s*$)/)?.[0] ?? l.ahead?.trim();
  if (!s) return null;
  const re = new RegExp(`\\b(${l.name}|${surname(l)}|He|She|he|she)\\s+would\\b`);
  if (!re.test(s)) return null;
  const mine = s.replace(re, "I would")
    .replace(new RegExp(`\\b(${l.name}|${surname(l)})'s\\b`, "g"), "my")
    .replace(/\b(he|she)\b/g, "I").replace(/\b(his|her)\b/g, "my").replace(/\bhim\b/g, "me");
  return cut(mine, 220);
}
