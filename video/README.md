# Showcase video

A ~23 second voxel-style explainer clip for Compounding Minds, made with [Remotion](https://www.remotion.dev) (React to video) and Three.js. Everything is code: no video model, no assets to download.

## Run it

```bash
cd video
npm install
npm run studio    # live preview and scrubbing in the browser
npm run render    # writes out/showcase.mp4 (1920x1080, 30 fps)
```

## Scenes

| Scene | File | What happens |
|---|---|---|
| The team | `src/scenes/Office.tsx` | Four analysts (Buffett, Graham, Munger, Dalio agents) at their desks |
| The call | `src/scenes/TheCall.tsx` | Buffett agent calls "FCF margin up next quarter?", the 10-Q lands, stamped WRONG |
| Mubit | `src/scenes/MubitUpdate.tsx` | Wrong call goes into Mubit, a lesson comes back, model v1 becomes v2 |
| Compounding | `src/scenes/Compounding.tsx` | Accuracy bars 2018-2024 with the COVID dip and the frozen twin line, then the end card |

Scene lengths live in `SCENES` in `src/theme.ts`. Characters are built in `src/three/Analyst.tsx` (looks are set in `TEAM`).

## Before showing it to judges

The chart numbers in `Compounding.tsx` (`ACC`, `FROZEN`) are **illustrative**, and the scene is badged "ILLUSTRATIVE DATA". Once the replay has run, swap in the real per-year accuracy for the learned agents and the frozen twin, then remove the badge.
