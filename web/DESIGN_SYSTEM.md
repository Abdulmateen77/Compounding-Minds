# Design system

The website's look is defined once, in `src/index.css`. Components use the names below, never raw numbers or hex codes. It follows
the `ui-design-system` skill (`.claude/skills/ui-design-system`).

## The rules

| Area | Rule | Where |
|---|---|---|
| Colour | Semantic names: `--primary`, `--secondary`, `--accent`, `--success`, `--warning`, `--error`, `--info`. Surfaces: `--background`, `--card`, `--card-alt`, `--divider`, `--foreground`, `--muted`. | `:root` |
| Contrast | Every text colour is at least 4.5:1 (3:1 for large text) on `--background`, `--card` and `--card-alt`, in dark and light mode. Light mode uses deeper status colours because the bright dark-mode ones are 1.7 to 3.2:1 on white. White text sits on `--primary-solid` (4.7:1), never on `--primary`. | `:root`, `@media (prefers-color-scheme: light)` |
| Type | 16px base, 1.25 ratio: caption 12, small 14, body 16, h5 20, h4 24, h3 28, h2 28 to 36 (fluid), h1 32 to 48 (fluid), display 36 to 60 (fluid). No arbitrary sizes such as `text-[11px]`. Heading line height and tracking come from the base layer. | `@theme` |
| Spacing | 8pt grid with 4px half-steps: `1` = 4, `2` = 8, `3` = 12, `4` = 16, `6` = 24, `8` = 32. No `0.5`, `1.5`, `2.5` or `3.5` steps. | Tailwind classes |
| Controls | Pills. Height 32 (`.sm`), 40 (default), 48 (`.lg`). On phones and touch screens every control is at least 44. A button keeps its own width in a grid (`justify-self: start`); full width only with `w-full`. Hover changes colour and shadow, nothing moves. | `.btn`, `--size-*` |
| Radius | 4 (`rounded-sm`), 8 (`rounded-lg`), 12 (`rounded-xl`), 16 (`rounded-2xl`, cards), 24, full. | `@theme` |
| Borders | 1px, 2px (focus), 4px (accent rules). | `--border-*` |
| Breakpoints | 480 `xs`, 640 `sm`, 768 `md`, 1024 `lg`, 1280 `xl`, 1536 `2xl`. Content width follows them up to 1152 and then stops (`.page`); text blocks and chat sit on `max-w-3xl` inside it, so nothing stretches on a wide monitor. | `@theme`, `.page` |
| Motion | 150ms fast, 250ms default, 350ms slow, 500ms slower, with `--ease-soft` (`EASE_SOFT`) for reveals. Colour and border changes fade (`transition-colors` feel); pressable cards warm their border and lift a shadow; sections open by growing a grid row from `0fr` to `1fr` (`.collapse`, `Collapse`); content blocks rise in once as they scroll into view (`FadeIn`); the page fades between routes. Reduced motion switches all of it off (CSS and `MotionConfig`). This follows the NourishwithB front end. | `--duration-*`, `DUR`, `.collapse`, `FadeIn` |
| Layers | dropdown 1000, sticky 1020, overlay 1030, modal 1040, popover 1050, tooltip 1060, notification 1070, via `z-[var(--z-...)]`. | `--z-*` |
| Accessibility | Visible focus ring, skip link, one `h1` per page, labelled landmarks, 16px form text on phones (stops iOS zoom), `prefers-reduced-motion` honoured. | `index.css`, `App.tsx` |

## Adding to it

- Need a colour? Add it to `:root` and the light block, check contrast, then use it by name.
- Need a size, gap or radius that is not on the scale? Pick the nearest one that is.
- The 3D scene (`src/scene/`) paints with its own palette in `scene/theme.ts`; it is not part of the page tokens.

## Checking

Paste `scripts/contrast-audit.js` into the browser console on any page to list text that fails contrast: it walks every text element, finds its real background
and reports ratios under 4.5 (3 for large text). The last full run (dark and light, desktop and phone widths) found none in 204 text nodes.
