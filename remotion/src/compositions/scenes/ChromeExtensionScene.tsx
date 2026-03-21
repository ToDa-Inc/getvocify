import React from 'react';
import { AbsoluteFill, useCurrentFrame, useVideoConfig, Img, staticFile } from 'remotion';
import { COLORS } from '../../lib/constants';
import { interFont, garamondFont } from '../../Root';
import { snapLeft, snapRight, slamEntry, fadeIn, waveBar, pulseScale } from '../../lib/animations';

export const ChromeExtensionScene: React.FC = () => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();

  const recOpacity = fadeIn(frame, 8, 12);
  const revOpacity = fadeIn(frame, 28, 12);
  const recPulse = pulseScale(frame, 22, 0.85, 1.18);
  const outerPulse = pulseScale(frame, 30, 0.92, 1.06);

  // Independent idle floats
  const recFloat = Math.sin(frame * 0.045) * 8;
  const revFloat = Math.sin(frame * 0.045 + 1.4) * 8;

  return (
    <AbsoluteFill style={{
      background: 'hsl(40,33%,96%)',
      display: 'flex', alignItems: 'center', justifyContent: 'center', padding: '60px 80px',
    }}>
      <div style={{ maxWidth: 1440, width: '100%', display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 72, alignItems: 'center' }}>

        {/* LEFT — Content */}
        <div style={{ opacity: fadeIn(frame, 4, 14), transform: snapLeft(frame, fps, 4, 80) }}>
          <div style={{ fontFamily: interFont, fontWeight: 700, fontSize: 16, letterSpacing: '0.3em', textTransform: 'uppercase', color: COLORS.beige, marginBottom: 18 }}>
            Chrome Extension
          </div>
          <div style={{ fontFamily: interFont, fontWeight: 800, fontSize: 62, letterSpacing: '-2px', lineHeight: 1.15, color: COLORS.foreground, marginBottom: 40 }}>
            Directo desde{' '}
            <span style={{ fontFamily: garamondFont, fontWeight: 500, fontStyle: 'italic', color: COLORS.beige }}>tu navegador.</span>
          </div>

          {[
            { num: '1', bold: '⌥+⇧+V', rest: 'Graba al instante, sin salir del CRM.', delay: 18 },
            { num: '2', bold: 'Contexto automático', rest: 'Detecta el trato activo en pantalla.', delay: 26 },
            { num: '3', bold: 'Ideal para demos', rest: 'Inside Sales, llamadas, reuniones.', delay: 34 },
          ].map((s) => (
            <div key={s.num} style={{ display: 'flex', gap: 18, alignItems: 'flex-start', marginBottom: 28, ...slamEntry(frame, fps, s.delay) }}>
              <div style={{
                width: 46, height: 46, borderRadius: '50%',
                backgroundColor: COLORS.beige, color: COLORS.cream,
                display: 'flex', alignItems: 'center', justifyContent: 'center',
                fontFamily: interFont, fontWeight: 800, fontSize: 18, flexShrink: 0,
              }}>{s.num}</div>
              <div style={{ paddingTop: 4 }}>
                <span style={{ fontFamily: interFont, fontWeight: 700, fontSize: 23, color: COLORS.foreground }}>{s.bold}: </span>
                <span style={{ fontFamily: interFont, fontWeight: 400, fontSize: 23, color: COLORS.muted }}>{s.rest}</span>
              </div>
            </div>
          ))}
        </div>

        {/* RIGHT — Two clearly separated popups stacked vertically */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: 22 }}>

          {/* ── Recording popup ── */}
          <div style={{
            backgroundColor: COLORS.creamDark, borderRadius: 22,
            border: `1px solid ${COLORS.border}`, overflow: 'hidden',
            boxShadow: '0 8px 28px rgba(0,0,0,0.1)',
            opacity: recOpacity,
            transform: `${snapRight(frame, fps, 8, 90)} translateY(${recFloat}px)`,
          }}>
            {/* Header */}
            <div style={{ padding: '14px 18px', borderBottom: `1px solid ${COLORS.border}`, display: 'flex', justifyContent: 'space-between', alignItems: 'center', backgroundColor: COLORS.white }}>
              <Img src={staticFile('logo.png')} style={{ height: 28, width: 'auto' }} />
              <div style={{ display: 'flex', alignItems: 'center', gap: 8, fontFamily: interFont, fontWeight: 800, fontSize: 14, color: '#ef4444', letterSpacing: '0.15em' }}>
                <div style={{ width: 9, height: 9, borderRadius: '50%', backgroundColor: '#ef4444', transform: `scale(${recPulse})` }} />
                RECORDING
              </div>
            </div>

            {/* Body — horizontal: button + waveform | transcript below */}
            <div style={{ padding: '20px 22px' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 20, marginBottom: 18 }}>
                {/* Pulsing record button */}
                <div style={{
                  width: 72, height: 72, borderRadius: '50%', border: '2px solid #fecaca',
                  display: 'flex', alignItems: 'center', justifyContent: 'center', flexShrink: 0,
                  transform: `scale(${outerPulse})`,
                }}>
                  <div style={{ width: 28, height: 28, backgroundColor: '#ef4444', borderRadius: 6 }} />
                </div>

                {/* Waveform + label */}
                <div style={{ flex: 1 }}>
                  <div style={{ fontFamily: interFont, fontWeight: 800, fontSize: 14, color: '#ef4444', letterSpacing: '0.18em', marginBottom: 10 }}>TAP TO STOP</div>
                  <div style={{ display: 'flex', gap: 3, alignItems: 'center', height: 44 }}>
                    {[5, 9, 14, 8, 20, 12, 7, 18, 10, 6, 16, 9, 12, 7, 15, 11, 19, 8].map((base, i) => (
                      <div key={i} style={{
                        width: 4,
                        height: waveBar(frame, i, base, 0.8),
                        backgroundColor: COLORS.beige, borderRadius: 2, opacity: 0.8,
                      }} />
                    ))}
                  </div>
                </div>
              </div>

              {/* Transcript */}
              <div style={{ backgroundColor: COLORS.white, borderRadius: 12, padding: '14px 16px', border: `1px solid ${COLORS.border}` }}>
                <div style={{ fontFamily: interFont, fontWeight: 700, fontSize: 12, color: COLORS.muted, letterSpacing: '0.2em', marginBottom: 8 }}>LIVE TRANSCRIPT</div>
                <div style={{ fontFamily: garamondFont, fontStyle: 'italic', fontSize: 17, color: COLORS.foreground, lineHeight: 1.5 }}>
                  "Reunión con Construcciones Pérez. Interesados en el plan Team para 15 comerciales..."
                </div>
              </div>
            </div>
          </div>

          {/* ── Deal Update / Review popup ── */}
          <div style={{
            backgroundColor: COLORS.white, borderRadius: 22,
            border: `1px solid ${COLORS.border}`, overflow: 'hidden',
            boxShadow: '0 12px 40px rgba(0,0,0,0.14)',
            opacity: revOpacity,
            transform: `${snapRight(frame, fps, 28, 80)} translateY(${revFloat}px)`,
          }}>
            {/* Header */}
            <div style={{ padding: '14px 18px', borderBottom: `1px solid ${COLORS.border}`, backgroundColor: 'hsla(35,25%,35%,0.07)', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
              <div style={{ fontFamily: interFont, fontWeight: 800, fontSize: 14, color: COLORS.beige, letterSpacing: '0.2em' }}>PROPOSED CHANGES</div>
              <div style={{ fontFamily: interFont, fontSize: 12, color: COLORS.muted }}>v1.0.2</div>
            </div>

            {/* Fields — 3 in a row */}
            <div style={{ padding: '18px', display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 12 }}>
              {[['Deal Name', 'Construcciones Pérez'], ['Amount', '€3,600 / año'], ['Next Step', 'Enviar contrato']].map(([label, val], i) => (
                <div key={i} style={{ padding: '13px 14px', backgroundColor: COLORS.successBg, borderRadius: 12, border: `1px solid ${COLORS.successBorder}` }}>
                  <div style={{ fontFamily: interFont, fontWeight: 800, fontSize: 12, color: COLORS.successText, marginBottom: 5 }}>{label}</div>
                  <div style={{ fontFamily: interFont, fontWeight: 700, fontSize: 15, color: COLORS.foreground, lineHeight: 1.3 }}>{val}</div>
                </div>
              ))}
            </div>
            <div style={{ margin: '0 18px 18px', padding: '14px 0', backgroundColor: COLORS.beige, borderRadius: 12, textAlign: 'center', fontFamily: interFont, fontWeight: 800, fontSize: 14, color: COLORS.cream, letterSpacing: '0.15em', textTransform: 'uppercase' }}>
              CONFIRM & UPDATE CRM
            </div>
          </div>

        </div>
      </div>
    </AbsoluteFill>
  );
};
