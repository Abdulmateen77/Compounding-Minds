import React from 'react';
import {AbsoluteFill, interpolate, spring, useCurrentFrame, useVideoConfig} from 'remotion';
import {C, SANS, SERIF} from '../theme';

const Tape: React.FC<{side: 'left' | 'right'}> = ({side}) => (
  <div
    style={{
      position: 'absolute',
      top: -14,
      [side]: -26,
      width: 90,
      height: 34,
      background: 'rgba(232, 220, 190, 0.85)',
      transform: `rotate(${side === 'left' ? -28 : 24}deg)`,
      boxShadow: '0 2px 4px rgba(0,0,0,0.15)',
    }}
  />
);

// Paper title card taped to the top of the frame.
export const TitleTape: React.FC<{text: string; start?: number; end?: number}> = ({text, start = 0, end}) => {
  const f = useCurrentFrame();
  const {fps} = useVideoConfig();
  const pop = spring({frame: f - start, fps, config: {damping: 12, stiffness: 160}});
  const out = end === undefined ? 0 : interpolate(f, [end, end + 8], [0, 1], {extrapolateLeft: 'clamp', extrapolateRight: 'clamp'});
  if (f < start) return null;
  return (
    <AbsoluteFill style={{alignItems: 'center', justifyContent: 'flex-start', paddingTop: 64}}>
      <div
        style={{
          position: 'relative',
          background: C.paper,
          color: C.ink,
          fontFamily: SANS,
          fontWeight: 900,
          fontSize: 66,
          letterSpacing: 2,
          padding: '20px 54px 18px',
          borderRadius: 6,
          boxShadow: '0 10px 0 rgba(0,0,0,0.25), 0 18px 40px rgba(0,0,0,0.35)',
          transform: `scale(${(0.6 + 0.4 * pop) * (1 - out)}) rotate(-1.5deg)`,
          opacity: Math.min(1, pop * 1.5) * (1 - out),
        }}
      >
        <Tape side="left" />
        <Tape side="right" />
        {text}
      </div>
    </AbsoluteFill>
  );
};

// Word-by-word caption chips along the bottom, like the reels.
export const Caption: React.FC<{words: string[]; start?: number; perWord?: number; end?: number}> = ({
  words,
  start = 0,
  perWord = 5,
  end,
}) => {
  const f = useCurrentFrame();
  const {fps} = useVideoConfig();
  const out = end === undefined ? 0 : interpolate(f, [end, end + 8], [0, 1], {extrapolateLeft: 'clamp', extrapolateRight: 'clamp'});
  return (
    <AbsoluteFill style={{alignItems: 'center', justifyContent: 'flex-end', paddingBottom: 70, opacity: 1 - out}}>
      <div style={{display: 'flex', gap: 14, flexWrap: 'wrap', justifyContent: 'center', maxWidth: 1820}}>
        {words.map((w, i) => {
          const s = spring({frame: f - start - i * perWord, fps, config: {damping: 11, stiffness: 200}});
          if (s <= 0.001) return null;
          return (
            <span
              key={i}
              style={{
                fontFamily: SERIF,
                fontStyle: 'italic',
                fontWeight: 700,
                fontSize: 50,
                color: C.paper,
                background: C.terracotta,
                padding: '6px 22px 12px',
                borderRadius: 8,
                boxShadow: '0 6px 0 rgba(0,0,0,0.25)',
                transform: `translateY(${(1 - s) * 30}px) scale(${0.7 + 0.3 * s})`,
                opacity: Math.min(1, s * 2),
              }}
            >
              {w}
            </span>
          );
        })}
      </div>
    </AbsoluteFill>
  );
};

export const Badge: React.FC<{text: string; start?: number}> = ({text, start = 0}) => {
  const f = useCurrentFrame();
  const o = interpolate(f, [start, start + 10], [0, 1], {extrapolateLeft: 'clamp', extrapolateRight: 'clamp'});
  return (
    <AbsoluteFill style={{alignItems: 'flex-end', justifyContent: 'flex-start', padding: 40, opacity: o}}>
      <div
        style={{
          fontFamily: SANS,
          fontWeight: 700,
          fontSize: 24,
          letterSpacing: 2,
          color: C.paper,
          border: `2px solid ${C.paper}66`,
          padding: '8px 16px',
          borderRadius: 999,
          background: 'rgba(0,0,0,0.25)',
        }}
      >
        {text}
      </div>
    </AbsoluteFill>
  );
};

export const Vignette: React.FC = () => (
  <AbsoluteFill
    style={{
      pointerEvents: 'none',
      background: 'radial-gradient(ellipse at center, rgba(0,0,0,0) 55%, rgba(5,8,25,0.55) 100%)',
    }}
  />
);
