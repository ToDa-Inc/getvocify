import React from 'react';
import { Composition } from 'remotion';
import { loadFont as loadInter } from '@remotion/google-fonts/Inter';
import { loadFont as loadGaramond } from '@remotion/google-fonts/EBGaramond';
import { VocifyDemoVideo } from './compositions/VocifyDemoVideo';
import { COMP_WIDTH, COMP_HEIGHT, COMP_FPS, TOTAL_DURATION_FRAMES } from './lib/constants';

// Load fonts at module level so they're ready before rendering
const { fontFamily: interFont } = loadInter('normal', {
  weights: ['300', '400', '500', '600', '700'],
  subsets: ['latin'],
});

const { fontFamily: garamondFont } = loadGaramond('normal', {
  weights: ['400', '500'],
  subsets: ['latin'],
});

export { interFont, garamondFont };

export const RemotionRoot: React.FC = () => {
  return (
    <>
      <Composition
        id="vocify-demo"
        component={VocifyDemoVideo}
        durationInFrames={TOTAL_DURATION_FRAMES}
        fps={COMP_FPS}
        width={COMP_WIDTH}
        height={COMP_HEIGHT}
        defaultProps={{}}
      />
    </>
  );
};
