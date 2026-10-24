import {loadFont as loadRubik} from '@remotion/google-fonts/Rubik';
import {loadFont as loadFraunces} from '@remotion/google-fonts/Fraunces';
import type {Look} from './three/Analyst';

export const rubik = loadRubik('normal', {weights: ['500', '700', '800', '900'], subsets: ['latin']});
export const fraunces = loadFraunces('italic', {weights: ['700'], subsets: ['latin']});

export const SANS = `"${rubik.fontFamily}", "Helvetica Neue", Arial, sans-serif`;
export const SERIF = `"${fraunces.fontFamily}", Georgia, serif`;

export const C = {
  bg: '#121831',
  wall: '#1f2647',
  floor: '#5a3d2a',
  desk: '#c08a55',
  deskDark: '#8c5d36',
  paper: '#f4ecdc',
  ink: '#1d1d2b',
  red: '#e5533d',
  green: '#36c48a',
  amber: '#f4b23e',
  violet: '#7b5cff',
  violetDark: '#2a2350',
  terracotta: '#c8643c',
  grey: '#9aa0b5',
};

export type Member = {name: string; role: string; look: Look};

export const TEAM: Member[] = [
  {
    name: 'BUFFETT',
    role: 'FUNDAMENTALS AGENT',
    look: {shirt: '#2f4b8f', hair: '#dcd7cf', tie: '#d8433a', glasses: true, hairStyle: 'swoop'},
  },
  {
    name: 'GRAHAM',
    role: 'VALUATION AGENT',
    look: {shirt: '#5c6670', hair: '#8f8f8f', bowtie: '#26263d', hairStyle: 'side'},
  },
  {
    name: 'MUNGER',
    role: 'RISK AGENT',
    look: {shirt: '#3d3d4f', hair: '#ececec', tie: '#27408b', glasses: true, hairStyle: 'bald'},
  },
  {
    name: 'DALIO',
    role: 'SCENARIOS AGENT',
    look: {shirt: '#2b7a78', hair: '#b9b2a6', hairStyle: 'flat'},
  },
];

// Scene lengths in frames (30 fps). Transitions overlap by TRANSITION frames.
export const FPS = 30;
export const TRANSITION = 12;
export const SCENES = {office: 150, call: 180, mubit: 185, chart: 225};
export const TOTAL =
  SCENES.office + SCENES.call + SCENES.mubit + SCENES.chart - 3 * TRANSITION;

export const clamp01 = (v: number) => Math.min(1, Math.max(0, v));
export const lerp = (a: number, b: number, t: number) => a + (b - a) * t;
export const lerp3 = (
  a: [number, number, number],
  b: [number, number, number],
  t: number,
): [number, number, number] => [lerp(a[0], b[0], t), lerp(a[1], b[1], t), lerp(a[2], b[2], t)];
export const easeInOut = (t: number) => (t < 0.5 ? 2 * t * t : 1 - Math.pow(-2 * t + 2, 2) / 2);
