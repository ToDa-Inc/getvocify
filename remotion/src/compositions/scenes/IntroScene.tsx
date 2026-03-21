import React from 'react';
import { AbsoluteFill, useCurrentFrame, useVideoConfig, Img, staticFile } from 'remotion';
import { COLORS } from '../../lib/constants';
import { interFont, garamondFont } from '../../Root';
import { snapIn, snapUp, fadeIn, wordRevealCount, pulseScale } from '../../lib/animations';

// Animated dot grid for mysterious background
const DotGrid: React.FC<{ frame: number }> = ({ frame }) => {
  const dots = [];
  for (let r = 0; r < 8; r++) {
    for (let c = 0; c < 14; c++) {
      const i = r * 14 + c;
      const delay = i * 1.2;
      const opacity = Math.min(0.18, Math.max(0, (frame - delay) / 20) * 0.18);
      dots.push(
        <div key={i} style={{
          position: 'absolute',
          left: 80 + c * 130,
          top: 80 + r * 120,
          width: 4, height: 4, borderRadius: '50%',
          backgroundColor: COLORS.beige,
          opacity,
        }} />
      );
    }
  }
  return <>{dots}</>;
};

const WORDS_LINE1 = ['Deja', 'de', 'escribir', 'notas', 'en', 'el', 'CRM.'];
const WORDS_LINE2 = ['Empieza', 'a', 'hablar.'];

export const IntroScene: React.FC = () => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();

  const logoScale = snapIn(frame, fps, 0);
  const tagOpacity = fadeIn(frame, 4, 8);
  const tagTY = snapUp(frame, fps, 4, 20);

  // Word-by-word: 3.5 words/sec — comfortable reading pace
  // Line 1: 7 words at 3.5wps = 2s = 60 frames; starts frame 8 → done ~frame 68
  const vis1 = wordRevealCount(frame, fps, 8, 3.5);
  // Line 2: 3 words at 4wps; starts frame 74 → done ~frame 96
  const vis2 = wordRevealCount(frame, fps, 74, 4);

  const subOpacity = fadeIn(frame, 100, 12);
  const subTY = snapUp(frame, fps, 100, 30);

  const ctaScale = snapIn(frame, fps, 126);
  const ctaOpacity = fadeIn(frame, 126, 8);

  // Pulsing mic circle
  const micPulse = pulseScale(frame, 28, 0.9, 1.12);

  return (
    <AbsoluteFill style={{
      background: `
        radial-gradient(ellipse at 20% 50%, hsla(35,25%,35%,0.09) 0px, transparent 60%),
        radial-gradient(ellipse at 80% 20%, hsla(35,30%,45%,0.06) 0px, transparent 50%),
        hsl(40,33%,96%)
      `,
      overflow: 'hidden',
    }}>
      <DotGrid frame={frame} />

      {/* Logo */}
      <div style={{
        position: 'absolute', top: 56, left: 72,
        opacity: fadeIn(frame, 0, 10),
        transform: `scale(${logoScale})`,
      }}>
        <Img src={staticFile('logo.png')} style={{ height: 64, width: 'auto' }} />
      </div>

      {/* Pulsing mic orb — top right */}
      <div style={{
        position: 'absolute', top: 120, right: 140,
        width: 180, height: 180, borderRadius: '50%',
        border: `2px solid hsla(35,25%,35%,0.15)`,
        display: 'flex', alignItems: 'center', justifyContent: 'center',
        transform: `scale(${micPulse})`,
        opacity: fadeIn(frame, 4, 16),
      }}>
        <div style={{
          width: 100, height: 100, borderRadius: '50%',
          border: `2px solid hsla(35,25%,35%,0.25)`,
          display: 'flex', alignItems: 'center', justifyContent: 'center',
        }}>
          <svg width="42" height="42" viewBox="0 0 24 24" fill="none" stroke={COLORS.beige} strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" style={{ opacity: 0.7 }}>
            <path d="M12 2a3 3 0 0 0-3 3v7a3 3 0 0 0 6 0V5a3 3 0 0 0-3-3z"/>
            <path d="M19 10v2a7 7 0 0 1-14 0v-2"/>
            <line x1="12" y1="19" x2="12" y2="22"/>
          </svg>
        </div>
      </div>

      {/* Main content */}
      <div style={{
        position: 'absolute', top: '50%', left: 80, right: 80,
        transform: 'translateY(-55%)',
      }}>
        {/* Tag */}
        <div style={{
          display: 'inline-flex', alignItems: 'center', gap: 10, marginBottom: 36,
          opacity: tagOpacity, transform: tagTY,
        }}>
          <div style={{ width: 6, height: 6, borderRadius: '50%', backgroundColor: COLORS.beige }} />
          <span style={{
            fontFamily: interFont, fontWeight: 600, fontSize: 16,
            letterSpacing: '0.3em', textTransform: 'uppercase', color: COLORS.beige,
          }}>Voice to CRM</span>
          <div style={{ width: 6, height: 6, borderRadius: '50%', backgroundColor: COLORS.beige }} />
        </div>

        {/* Line 1 — word by word */}
        <div style={{ marginBottom: 4, minHeight: 130 }}>
          <div style={{
            fontFamily: interFont, fontWeight: 800, fontSize: 108,
            letterSpacing: '-3.5px', lineHeight: 1.03, color: COLORS.foreground,
          }}>
            {WORDS_LINE1.slice(0, vis1).join(' ')}
            {vis1 > 0 && vis1 < WORDS_LINE1.length && (
              <span style={{ opacity: 0.3 }}>|</span>
            )}
          </div>
        </div>

        {/* Line 2 — EB Garamond italic, word by word */}
        <div style={{ marginBottom: 40, minHeight: 130 }}>
          <div style={{
            fontFamily: garamondFont, fontWeight: 500, fontStyle: 'italic',
            fontSize: 108, letterSpacing: '-2.5px', lineHeight: 1.03, color: COLORS.beige,
          }}>
            {WORDS_LINE2.slice(0, vis2).join(' ')}
            {vis2 > 0 && vis2 < WORDS_LINE2.length && (
              <span style={{ opacity: 0.3 }}>|</span>
            )}
          </div>
        </div>

        {/* Subtext */}
        <div style={{
          fontFamily: interFont, fontWeight: 400, fontSize: 30,
          color: COLORS.muted, lineHeight: 1.5, maxWidth: 900,
          opacity: subOpacity, transform: subTY,
        }}>
          Notas de voz → CRM actualizado en 60 segundos.{' '}
          <span style={{ fontFamily: garamondFont, fontStyle: 'italic' }}>5 horas ahorradas. Cada semana.</span>
        </div>
      </div>

      {/* CTA bottom-right */}
      <div style={{
        position: 'absolute', bottom: 72, right: 80,
        display: 'flex', alignItems: 'center', gap: 14,
        padding: '16px 36px', borderRadius: 48,
        backgroundColor: COLORS.beige, color: COLORS.cream,
        fontFamily: interFont, fontWeight: 700, fontSize: 18,
        letterSpacing: '0.12em', textTransform: 'uppercase',
        boxShadow: '0 8px 32px rgba(0,0,0,0.16)',
        opacity: ctaOpacity, transform: `scale(${ctaScale})`,
      }}>
        Habla. Vocify hace el resto. →
      </div>
    </AbsoluteFill>
  );
};
