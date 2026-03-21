import React from 'react';
import { AbsoluteFill, useCurrentFrame, useVideoConfig } from 'remotion';
import { COLORS } from '../../lib/constants';
import { interFont, garamondFont } from '../../Root';
import { snapIn, snapUp, snapLeft, slamEntry, fadeIn, countUp } from '../../lib/animations';

export const ProblemScene: React.FC = () => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();

  const count = countUp(frame, fps, 12400, 2.2, 20);
  const countOpacity = fadeIn(frame, 14, 10);

  return (
    <AbsoluteFill style={{
      background: `
        radial-gradient(ellipse at 10% 90%, hsla(35,25%,35%,0.07) 0, transparent 55%),
        hsl(40,33%,96%)
      `,
      display: 'flex', alignItems: 'center', justifyContent: 'center', padding: '80px',
    }}>
      <div style={{ maxWidth: 1440, width: '100%', display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 72, alignItems: 'center' }}>

        {/* LEFT */}
        <div>
          <div style={{
            fontFamily: interFont, fontWeight: 700, fontSize: 14,
            letterSpacing: '0.3em', textTransform: 'uppercase', color: COLORS.beige,
            marginBottom: 22, opacity: fadeIn(frame, 0, 8), transform: snapUp(frame, fps, 0, 20),
          }}>
            El Problema
          </div>

          <div style={{
            fontFamily: interFont, fontWeight: 800, fontSize: 66,
            letterSpacing: '-2px', lineHeight: 1.12, color: COLORS.foreground,
            marginBottom: 48,
            opacity: fadeIn(frame, 4, 10), transform: snapLeft(frame, fps, 4, 70),
          }}>
            Estás perdiendo{' '}
            <span style={{ fontFamily: garamondFont, fontWeight: 500, fontStyle: 'italic', color: COLORS.beige }}>
              5+ horas semanales
            </span>{' '}
            en burocracia.
          </div>

          {/* Issue 1 */}
          <div style={{ display: 'flex', gap: 22, marginBottom: 32, ...slamEntry(frame, fps, 22) }}>
            <div style={{
              width: 60, height: 60, borderRadius: 18, backgroundColor: COLORS.white,
              border: `1px solid ${COLORS.border}`, display: 'flex', alignItems: 'center',
              justifyContent: 'center', flexShrink: 0, boxShadow: '0 2px 8px rgba(0,0,0,0.04)',
            }}>
              <svg width="26" height="26" viewBox="0 0 24 24" fill="none" stroke={COLORS.beige} strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
                <circle cx="12" cy="12" r="10"/><polyline points="12 6 12 12 16 14"/>
              </svg>
            </div>
            <div>
              <div style={{ fontFamily: interFont, fontWeight: 700, fontSize: 24, color: COLORS.foreground, marginBottom: 4 }}>Admin vs. Venta</div>
              <div style={{ fontFamily: interFont, fontWeight: 400, fontSize: 17, color: COLORS.muted, lineHeight: 1.5 }}>
                En el coche, tras demos o visitas. Notas en lugar de cerrar tratos.
              </div>
            </div>
          </div>

          {/* Issue 2 */}
          <div style={{ display: 'flex', gap: 22, ...slamEntry(frame, fps, 32) }}>
            <div style={{
              width: 60, height: 60, borderRadius: 18, backgroundColor: COLORS.white,
              border: `1px solid ${COLORS.border}`, display: 'flex', alignItems: 'center',
              justifyContent: 'center', flexShrink: 0, boxShadow: '0 2px 8px rgba(0,0,0,0.04)',
            }}>
              <svg width="26" height="26" viewBox="0 0 24 24" fill="none" stroke={COLORS.beige} strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
                <path d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z"/>
              </svg>
            </div>
            <div>
              <div style={{ fontFamily: interFont, fontWeight: 700, fontSize: 24, color: COLORS.foreground, marginBottom: 4 }}>Pipeline "Ciego"</div>
              <div style={{ fontFamily: interFont, fontWeight: 400, fontSize: 17, color: COLORS.muted, lineHeight: 1.5 }}>
                Registros incompletos. El negocio no puede escalar.
              </div>
            </div>
          </div>
        </div>

        {/* RIGHT — animated counter */}
        <div style={{
          ...slamEntry(frame, fps, 8),
          background: 'rgba(255,255,255,0.88)',
          border: '1px solid rgba(0,0,0,0.06)',
          borderRadius: 48, padding: '56px 48px', textAlign: 'center',
          boxShadow: '0 12px 48px rgba(0,0,0,0.1)',
        }}>
          <div style={{
            fontFamily: interFont, fontWeight: 800, fontSize: 11,
            letterSpacing: '0.3em', textTransform: 'uppercase',
            color: 'rgba(0,0,0,0.28)', marginBottom: 24,
          }}>
            Fuga Financiera Estimada
          </div>

          {/* Animated counter */}
          <div style={{ opacity: countOpacity }}>
            <div style={{
              fontFamily: interFont, fontWeight: 900, fontSize: 112,
              letterSpacing: '-4px', lineHeight: 1, color: COLORS.beige, marginBottom: 12,
              fontVariantNumeric: 'tabular-nums',
            }}>
              €{count.toLocaleString('es-ES')}
            </div>
          </div>

          <div style={{
            fontFamily: interFont, fontWeight: 700, fontSize: 26, color: COLORS.foreground, marginBottom: 24,
          }}>
            anuales por comercial
          </div>

          <div style={{ width: 48, height: 2, backgroundColor: COLORS.creamDark, margin: '0 auto 0' }} />
        </div>
      </div>
    </AbsoluteFill>
  );
};
