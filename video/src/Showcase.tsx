import React, {useEffect, useState} from 'react';
import {AbsoluteFill, continueRender, delayRender} from 'remotion';
import {TransitionSeries, linearTiming} from '@remotion/transitions';
import {fade} from '@remotion/transitions/fade';
import {Office} from './scenes/Office';
import {TheCall} from './scenes/TheCall';
import {MubitUpdate} from './scenes/MubitUpdate';
import {Compounding} from './scenes/Compounding';
import {C, SCENES, TRANSITION, fraunces, rubik} from './theme';

// Canvas textures draw text, so wait for the web fonts before mounting the scenes.
const useFontsReady = () => {
  const [ready, setReady] = useState(false);
  const [handle] = useState(() => delayRender('Loading fonts'));
  useEffect(() => {
    Promise.all([rubik.waitUntilDone(), fraunces.waitUntilDone()]).then(() => {
      setReady(true);
      continueRender(handle);
    });
  }, [handle]);
  return ready;
};

export const Showcase: React.FC = () => {
  const ready = useFontsReady();
  if (!ready) return <AbsoluteFill style={{background: C.bg}} />;
  const timing = linearTiming({durationInFrames: TRANSITION});
  return (
    <AbsoluteFill style={{background: C.bg}}>
      <TransitionSeries>
        <TransitionSeries.Sequence durationInFrames={SCENES.office}>
          <Office />
        </TransitionSeries.Sequence>
        <TransitionSeries.Transition presentation={fade()} timing={timing} />
        <TransitionSeries.Sequence durationInFrames={SCENES.call}>
          <TheCall />
        </TransitionSeries.Sequence>
        <TransitionSeries.Transition presentation={fade()} timing={timing} />
        <TransitionSeries.Sequence durationInFrames={SCENES.mubit}>
          <MubitUpdate />
        </TransitionSeries.Sequence>
        <TransitionSeries.Transition presentation={fade()} timing={timing} />
        <TransitionSeries.Sequence durationInFrames={SCENES.chart}>
          <Compounding />
        </TransitionSeries.Sequence>
      </TransitionSeries>
    </AbsoluteFill>
  );
};
