import React from 'react';
import { AbsoluteFill, useCurrentFrame, useVideoConfig } from 'remotion';
import { COLORS } from '../../lib/constants';
import { interFont, garamondFont } from '../../Root';
import { snapLeft, snapRight, slamEntry, fadeIn, waveBar } from '../../lib/animations';

export const WhatsAppScene: React.FC = () => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();

  const msg1Opacity = fadeIn(frame, 16, 8);
  const msg2Opacity = fadeIn(frame, 32, 10);
  const bar2Opacity = fadeIn(frame, 40, 6);

  // Idle float — gentle sine oscillation after entry settles
  const phoneFloat = Math.sin(frame * 0.05) * 10;

  return (
    <AbsoluteFill style={{
      background: 'hsl(40,33%,96%)',
      display: 'flex', alignItems: 'center', justifyContent: 'center', padding: '80px',
    }}>
      <div style={{ maxWidth: 1440, width: '100%', display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 72, alignItems: 'center' }}>

        {/* LEFT — Phone (bigger: 460×880) */}
        <div style={{
          opacity: fadeIn(frame, 4, 14),
          transform: `${snapLeft(frame, fps, 4, 110)} translateY(${phoneFloat}px)`,
          display: 'flex', justifyContent: 'center',
        }}>
          <div style={{
            width: 460, height: 880, backgroundColor: '#111', borderRadius: 66,
            border: '12px solid #222', overflow: 'hidden', position: 'relative',
            boxShadow: '0 36px 100px rgba(0,0,0,0.42)', display: 'flex', flexDirection: 'column',
          }}>
            {/* Status bar */}
            <div style={{ backgroundColor: '#111', height: 28, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
              <div style={{ width: 72, height: 8, borderRadius: 4, backgroundColor: '#333' }} />
            </div>

            {/* WA Header */}
            <div style={{ backgroundColor: COLORS.waHeader, color: '#fff', padding: '12px 18px', display: 'flex', alignItems: 'center', gap: 13 }}>
              <div style={{ width: 46, height: 46, borderRadius: '50%', backgroundColor: 'rgba(255,255,255,0.2)', flexShrink: 0 }} />
              <div>
                <div style={{ fontFamily: interFont, fontWeight: 700, fontSize: 22 }}>Vocify AI</div>
                <div style={{ fontFamily: interFont, fontSize: 16, opacity: 0.7 }}>En línea</div>
              </div>
            </div>

            {/* Chat */}
            <div style={{ flex: 1, backgroundColor: COLORS.waBg, padding: '16px 13px', display: 'flex', flexDirection: 'column', gap: 13, overflow: 'hidden' }}>

              {/* User audio bubble */}
              <div style={{
                alignSelf: 'flex-end', backgroundColor: COLORS.waGreen,
                borderRadius: '20px 20px 4px 20px', padding: '11px 16px',
                display: 'flex', gap: 11, alignItems: 'center', maxWidth: '88%',
                boxShadow: '0 2px 6px rgba(0,0,0,0.1)', opacity: msg1Opacity,
              }}>
                <div style={{
                  width: 40, height: 40, borderRadius: '50%',
                  backgroundColor: 'rgba(93,72,53,0.12)',
                  display: 'flex', alignItems: 'center', justifyContent: 'center', flexShrink: 0,
                }}>
                  <svg width="18" height="18" viewBox="0 0 24 24" fill={COLORS.beige}><path d="M8 5v14l11-7z"/></svg>
                </div>
                {/* Animated waveform */}
                <div style={{ display: 'flex', gap: 3, alignItems: 'center', height: 36 }}>
                  {[7, 14, 6, 22, 10, 18, 5, 17, 8, 13, 6, 16].map((base, i) => (
                    <div key={i} style={{
                      width: 4,
                      height: waveBar(frame, i, base, 0.65),
                      backgroundColor: COLORS.beige,
                      borderRadius: 2, opacity: 0.75,
                    }} />
                  ))}
                </div>
                <span style={{ fontFamily: interFont, fontSize: 11, color: '#666', alignSelf: 'flex-end' }}>14:20</span>
              </div>

              {/* AI response */}
              <div style={{
                alignSelf: 'flex-start', backgroundColor: '#fff',
                borderRadius: '20px 20px 20px 4px', padding: '16px',
                maxWidth: '94%', border: '1px solid rgba(0,0,0,0.05)',
                boxShadow: '0 2px 8px rgba(0,0,0,0.08)', opacity: msg2Opacity,
              }}>
                <div style={{
                  fontFamily: interFont, fontWeight: 800, fontSize: 16,
                  color: COLORS.beige, textTransform: 'uppercase', letterSpacing: '0.2em', marginBottom: 14,
                }}>
                  ✓ Extracción Completada
                </div>
                {[
                  ['Trato', 'SolarTech S.L.'],
                  ['Valor', '€12.500'],
                  ['Tarea', 'Enviar presupuesto'],
                ].map(([label, val], i) => (
                  <div key={i} style={{
                    display: 'flex', justifyContent: 'space-between', alignItems: 'center',
                    borderBottom: i < 2 ? '1px solid #f5f0eb' : 'none', paddingBottom: 8, marginBottom: 8,
                  }}>
                    <span style={{ fontFamily: interFont, fontSize: 16, color: COLORS.muted }}>{label}</span>
                    <span style={{ fontFamily: interFont, fontWeight: 700, fontSize: 18, color: COLORS.foreground }}>{val}</span>
                  </div>
                ))}
                <div style={{ display: 'flex', gap: 10, marginTop: 16, opacity: bar2Opacity }}>
                  <div style={{ padding: '11px 22px', backgroundColor: COLORS.beige, color: COLORS.cream, borderRadius: 26, fontFamily: interFont, fontWeight: 800, fontSize: 14, letterSpacing: '0.15em', textTransform: 'uppercase' }}>APROBAR</div>
                  <div style={{ padding: '11px 22px', border: `1px solid ${COLORS.beige}`, borderRadius: 26, fontFamily: interFont, fontWeight: 700, fontSize: 14, color: COLORS.beige, letterSpacing: '0.1em', textTransform: 'uppercase' }}>EDITAR</div>
                </div>
              </div>
            </div>
          </div>
        </div>

        {/* RIGHT — Content */}
        <div style={{ opacity: fadeIn(frame, 6, 14), transform: snapRight(frame, fps, 6, 80) }}>
          <div style={{ fontFamily: interFont, fontWeight: 700, fontSize: 14, letterSpacing: '0.3em', textTransform: 'uppercase', color: COLORS.beige, marginBottom: 18 }}>Experiencia</div>
          <div style={{ fontFamily: interFont, fontWeight: 800, fontSize: 60, letterSpacing: '-2px', lineHeight: 1.15, color: COLORS.foreground, marginBottom: 40 }}>
            WhatsApp:{' '}
            <span style={{ fontFamily: garamondFont, fontWeight: 500, fontStyle: 'italic', color: COLORS.beige }}>
              Como hablar con un colega.
            </span>
          </div>

          {[
            { num: '1', bold: 'Envía un Audio', rest: 'Sin abrir el CRM ni el portátil.', delay: 20 },
            { num: '2', bold: 'IA Extrae Todo', rest: 'Valores, tareas, seguimientos.', delay: 28 },
            { num: '3', bold: 'Un Botón', rest: 'Confirma y el CRM se actualiza solo.', delay: 36 },
          ].map((s) => (
            <div key={s.num} style={{ display: 'flex', gap: 18, alignItems: 'flex-start', marginBottom: 28, ...slamEntry(frame, fps, s.delay) }}>
              <div style={{
                width: 44, height: 44, borderRadius: '50%',
                backgroundColor: COLORS.beige, color: COLORS.cream,
                display: 'flex', alignItems: 'center', justifyContent: 'center',
                fontFamily: interFont, fontWeight: 800, fontSize: 17, flexShrink: 0,
              }}>{s.num}</div>
              <div style={{ paddingTop: 3 }}>
                <span style={{ fontFamily: interFont, fontWeight: 700, fontSize: 21, color: COLORS.foreground }}>{s.bold}: </span>
                <span style={{ fontFamily: interFont, fontWeight: 400, fontSize: 21, color: COLORS.muted }}>{s.rest}</span>
              </div>
            </div>
          ))}
        </div>
      </div>
    </AbsoluteFill>
  );
};
