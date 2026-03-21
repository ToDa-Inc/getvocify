import React from 'react';
import { AbsoluteFill, Sequence, Audio, staticFile, useVideoConfig, interpolate } from 'remotion';
import { SCENE_DUR, TOTAL_DURATION_FRAMES, COLORS } from '../lib/constants';
import { IntroScene } from './scenes/IntroScene';
import { ProblemScene } from './scenes/ProblemScene';
import { SolutionScene } from './scenes/SolutionScene';
import { WhatsAppScene } from './scenes/WhatsAppScene';
import { ChromeExtensionScene } from './scenes/ChromeExtensionScene';
import { IntegrationsScene } from './scenes/IntegrationsScene';
import { CTAScene } from './scenes/CTAScene';

export const VocifyDemoVideo: React.FC = () => {
  const { fps } = useVideoConfig();

  const s0 = 0;
  const s1 = s0 + SCENE_DUR.intro;
  const s2 = s1 + SCENE_DUR.problem;
  const s3 = s2 + SCENE_DUR.solution;
  const s4 = s3 + SCENE_DUR.whatsapp;
  const s5 = s4 + SCENE_DUR.chrome;
  const s6 = s5 + SCENE_DUR.integrations;

  return (
    <AbsoluteFill style={{ backgroundColor: COLORS.cream }}>
      {/* Music with fade in/out */}
      <Audio
        src={staticFile('music.mp3')}
        loop
        volume={(f) => {
          if (f < fps * 1.5) return interpolate(f, [0, fps * 1.5], [0, 0.42], { extrapolateRight: 'clamp' });
          if (f > TOTAL_DURATION_FRAMES - fps * 2.5)
            return interpolate(f, [TOTAL_DURATION_FRAMES - fps * 2.5, TOTAL_DURATION_FRAMES], [0.42, 0], { extrapolateLeft: 'clamp', extrapolateRight: 'clamp' });
          return 0.42;
        }}
      />

      <Sequence from={s0} durationInFrames={SCENE_DUR.intro}><IntroScene /></Sequence>
      <Sequence from={s1} durationInFrames={SCENE_DUR.problem}><ProblemScene /></Sequence>
      <Sequence from={s2} durationInFrames={SCENE_DUR.solution}><SolutionScene /></Sequence>
      <Sequence from={s3} durationInFrames={SCENE_DUR.whatsapp}><WhatsAppScene /></Sequence>
      <Sequence from={s4} durationInFrames={SCENE_DUR.chrome}><ChromeExtensionScene /></Sequence>
      <Sequence from={s5} durationInFrames={SCENE_DUR.integrations}><IntegrationsScene /></Sequence>
      <Sequence from={s6} durationInFrames={SCENE_DUR.cta}><CTAScene /></Sequence>
    </AbsoluteFill>
  );
};
