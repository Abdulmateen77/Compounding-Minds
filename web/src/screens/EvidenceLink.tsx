/** A one-line pointer from a company page to the proof that the checks work, which lives on the Track record page. */
export function EvidenceLink() {
  return (
    <p className="m-0 text-sm mute">
      Do these checks actually work? We tested them on 50 companies against what happened next: <a href="#/mubit" className="underline underline-offset-4" style={{ color: "var(--blue)" }}>see the track record</a>.
    </p>
  );
}
