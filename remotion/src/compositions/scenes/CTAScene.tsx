import React from 'react';
import { AbsoluteFill, useCurrentFrame, useVideoConfig, Img, staticFile } from 'remotion';
import { COLORS } from '../../lib/constants';
import { interFont, garamondFont } from '../../Root';
import { snapIn, snapUp, slamEntry, fadeIn, countUp, pulseScale } from '../../lib/animations';

const Stat: React.FC<{ value: string; label: string; delay: number; frame: number; fps: number }> = ({ value, label, delay, frame, fps }) => (
  <div style={{ textAlign: 'center', ...slamEntry(frame, fps, delay) }}>
    <div style={{ fontFamily: interFont, fontWeight: 900, fontSize: 72, letterSpacing: '-2px', color: COLORS.cream, lineHeight: 1 }}>
      {value}
    </div>
    <div style={{ fontFamily: interFont, fontWeight: 600, fontSize: 14, letterSpacing: '0.2em', textTransform: 'uppercase', color: 'hsla(40,33%,96%,0.5)', marginTop: 6 }}>
      {label}
    </div>
  </div>
);

export const CTAScene: React.FC = () => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();

  // Stats count up
  const hoursCount = Math.min(5, countUp(frame, fps, 5, 1.4, 38));
  const accCount = Math.min(98, countUp(frame, fps, 98, 1.4, 38));
  const secCount = Math.min(60, countUp(frame, fps, 60, 1.4, 38));

  const btnPulse = pulseScale(frame, 36, 0.97, 1.03);

  return (
    <AbsoluteFill style={{
      backgroundColor: COLORS.beige,
      display: 'flex', flexDirection: 'column',
      alignItems: 'center', justifyContent: 'center',
      padding: '80px', textAlign: 'center', overflow: 'hidden',
    }}>
      {/* Radial glow */}
      <div style={{
        position: 'absolute', top: '50%', left: '50%',
        transform: 'translate(-50%, -50%)',
        width: 1400, height: 900, borderRadius: '50%',
        background: 'radial-gradient(circle, hsla(35,25%,55%,0.22), transparent 65%)',
        opacity: fadeIn(frame, 0, 16),
      }} />

      {/* Logo */}
      <div style={{ position: 'absolute', top: 56, left: 72, opacity: fadeIn(frame, 0, 10) }}>
        <Img src={staticFile('logo.png')} style={{ height: 52, width: 'auto', filter: 'brightness(0) invert(1) opacity(0.35)' }} />
      </div>

      <div style={{ maxWidth: 1100, position: 'relative' }}>
        {/* Headline */}
        <div style={{
          fontFamily: interFont, fontWeight: 800, fontSize: 96,
          letterSpacing: '-3px', lineHeight: 1.05, color: COLORS.cream,
          opacity: fadeIn(frame, 4, 12), transform: snapUp(frame, fps, 4, 50),
          marginBottom: 6,
        }}>
          ¿Quieres recuperar
        </div>
        <div style={{
          fontFamily: garamondFont, fontWeight: 500, fontStyle: 'italic',
          fontSize: 96, letterSpacing: '-2px', lineHeight: 1.05,
          color: 'hsla(40,33%,96%,0.82)',
          opacity: fadeIn(frame, 10, 12), transform: snapUp(frame, fps, 10, 50),
          marginBottom: 36,
        }}>
          esas 5 horas?
        </div>

        {/* Sub */}
        <div style={{
          fontFamily: interFont, fontWeight: 400, fontSize: 28,
          color: 'hsla(40,33%,96%,0.65)', lineHeight: 1.5, maxWidth: 780,
          margin: '0 auto 48px',
          opacity: fadeIn(frame, 18, 12), transform: snapUp(frame, fps, 18, 28),
        }}>
          Agenda una demo de 15 minutos y transforma la productividad de tu equipo.
        </div>

        {/* CTA Button — pulsing */}
        <div style={{
          display: 'inline-flex', alignItems: 'center', gap: 14,
          padding: '22px 60px', borderRadius: 56,
          backgroundColor: COLORS.cream, color: COLORS.beige,
          fontFamily: interFont, fontWeight: 800, fontSize: 22,
          letterSpacing: '0.12em', textTransform: 'uppercase',
          boxShadow: '0 12px 48px rgba(0,0,0,0.22)',
          marginBottom: 64,
          opacity: fadeIn(frame, 28, 10),
          transform: `scale(${snapIn(frame, fps, 28) * btnPulse})`,
        }}>
          <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
            <rect x="3" y="4" width="18" height="18" rx="2"/><line x1="16" y1="2" x2="16" y2="6"/><line x1="8" y1="2" x2="8" y2="6"/><line x1="3" y1="10" x2="21" y2="10"/>
          </svg>
          AGENDAR DEMO AHORA
        </div>

        {/* Stats row */}
        <div style={{ display: 'flex', justifyContent: 'center', gap: 100 }}>
          <Stat value={`${hoursCount}h+`} label="ahorradas / semana" delay={36} frame={frame} fps={fps} />
          <Stat value={`${accCount}%`} label="precisión IA" delay={42} frame={frame} fps={fps} />
          <Stat value={`${secCount}s`} label="actualizar CRM" delay={48} frame={frame} fps={fps} />
        </div>
      </div>

      {/* Footer */}
      <div style={{
        position: 'absolute', bottom: 44,
        fontFamily: interFont, fontWeight: 700, fontSize: 12,
        color: 'hsla(40,33%,96%,0.28)', letterSpacing: '0.5em', textTransform: 'uppercase',
        opacity: fadeIn(frame, 54, 10),
      }}>
        vocify.ai — la revolución de la voz en el crm
      </div>
    </AbsoluteFill>
  );
};
