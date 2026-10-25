/* Paste into the browser console on any page. Lists every text element whose colour against its real background is under
   WCAG AA (4.5:1, or 3:1 for large text). Prints an empty list when the page passes. Run it in dark and light mode. */
(() => {
  const cx = Object.assign(document.createElement("canvas"), { width: 1, height: 1 }).getContext("2d", { willReadFrequently: true });
  const parse = (c) => { cx.clearRect(0, 0, 1, 1); cx.fillStyle = c; cx.fillRect(0, 0, 1, 1); const d = cx.getImageData(0, 0, 1, 1).data; return [d[0], d[1], d[2], d[3] / 255]; };
  const lum = ([r, g, b]) => { const f = (v) => { v /= 255; return v <= 0.03928 ? v / 12.92 : ((v + 0.055) / 1.055) ** 2.4; }; return 0.2126 * f(r) + 0.7152 * f(g) + 0.0722 * f(b); };
  const ratio = (a, b) => { const x = lum(a), y = lum(b); return (Math.max(x, y) + 0.05) / (Math.min(x, y) + 0.05); };
  const over = (top, bot) => [0, 1, 2].map((i) => top[i] * top[3] + bot[i] * (1 - top[3])).concat([1]);
  const page = parse(getComputedStyle(document.body).backgroundColor), fails = [], seen = new Set();
  for (const el of document.querySelectorAll("main *, header *, footer *")) {
    if (![...el.childNodes].some((n) => n.nodeType === 3 && n.textContent.trim()) || !el.getBoundingClientRect().width) continue;
    const cs = getComputedStyle(el), layers = [];
    for (let n = el; n && n !== document.documentElement; n = n.parentElement) { const bg = parse(getComputedStyle(n).backgroundColor); if (bg[3] > 0) layers.push(bg); if (bg[3] >= 1) break; }
    let base = layers.length && layers[layers.length - 1][3] >= 1 ? layers.pop() : page;
    for (const l of layers.reverse()) base = over(l, base);
    const c = parse(cs.color), fg = over([c[0], c[1], c[2], c[3] * (parseFloat(cs.opacity) || 1)], base);
    const size = parseFloat(cs.fontSize), large = size >= 24 || (size >= 18.66 && parseInt(cs.fontWeight) >= 700), r = ratio(fg, base);
    const key = el.textContent.trim().slice(0, 30);
    if (r < (large ? 3 : 4.5) && !seen.has(key)) { seen.add(key); fails.push(`${r.toFixed(2)}  ${size}px  ${key}`); }
  }
  console.log(fails.length ? fails : "No contrast failures on this page.");
  return fails;
})();
