import React from 'react';
import { AbsoluteFill, useCurrentFrame, useVideoConfig } from 'remotion';
import { COLORS } from '../../lib/constants';
import { interFont, garamondFont } from '../../Root';
import { snapIn, snapUp, slamEntry, fadeIn } from '../../lib/animations';

const CrmBadge: React.FC<{ name: string; color: string; icon: React.ReactNode; delay: number; frame: number; fps: number }> = ({ name, color, icon, delay, frame, fps }) => {
  const scale = snapIn(frame, fps, delay);
  const opacity = fadeIn(frame, delay, 8);
  return (
    <div style={{
      opacity, transform: `scale(${scale})`,
      display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 10,
    }}>
      <div style={{
        width: 88, height: 88, borderRadius: 24, backgroundColor: COLORS.white,
        border: `1px solid ${COLORS.border}`,
        display: 'flex', alignItems: 'center', justifyContent: 'center',
        boxShadow: '0 4px 16px rgba(0,0,0,0.07)',
      }}>
        {icon}
      </div>
      <div style={{ fontFamily: interFont, fontWeight: 600, fontSize: 15, color: COLORS.foreground }}>{name}</div>
    </div>
  );
};

export const IntegrationsScene: React.FC = () => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();

  return (
    <AbsoluteFill style={{
      background: `radial-gradient(ellipse at 50% 0%, hsla(35,25%,35%,0.07) 0, transparent 55%), hsl(40,33%,96%)`,
      display: 'flex', flexDirection: 'column',
      alignItems: 'center', justifyContent: 'center', padding: '64px 80px',
    }}>
      <div style={{ textAlign: 'center', width: '100%', maxWidth: 1300 }}>
        <div style={{ fontFamily: interFont, fontWeight: 700, fontSize: 14, letterSpacing: '0.3em', textTransform: 'uppercase', color: COLORS.beige, marginBottom: 16, opacity: fadeIn(frame, 0, 8), transform: snapUp(frame, fps, 0, 20) }}>Ecosistema</div>

        <div style={{ fontFamily: interFont, fontWeight: 800, fontSize: 68, letterSpacing: '-2px', lineHeight: 1.1, color: COLORS.foreground, marginBottom: 52, opacity: fadeIn(frame, 4, 10), transform: snapUp(frame, fps, 4, 36) }}>
          Se integra con{' '}
          <span style={{ fontFamily: garamondFont, fontWeight: 500, fontStyle: 'italic', color: COLORS.beige }}>tus herramientas.</span>
        </div>

        {/* CRM logos */}
        <div style={{ display: 'flex', justifyContent: 'center', gap: 80, marginBottom: 16, alignItems: 'flex-end' }}>
          <CrmBadge name="HubSpot" color="#FF7A59" delay={12} frame={frame} fps={fps} icon={
            <svg width="48" height="48" viewBox="0 0 512 512" fill="#FF7A59">
              <path d="M388 233.7v-60.8a43.4 43.4 0 0 0 18-35c0-24-19.4-43.4-43.4-43.4s-43.4 19.4-43.4 43.4c0 14.2 6.8 26.7 17.4 34.6l-1 .5v61.4c-26.6 4.2-50.5 16.3-69.5 33.3L126.8 151.4a48.3 48.3 0 0 0 2-13.5C128.8 111.5 107.3 90 80.9 90S33 111.5 33 137.9s21.5 47.9 47.9 47.9c10.1 0 19.4-3 27-8.2l136.2 113.8C239 302 234 318.8 234 336.7c0 66.2 53.8 120 120 120s120-53.8 120-120c0-52.3-33.4-96.8-80-113z"/>
            </svg>
          } />
          <CrmBadge name="Salesforce" color="#00A1E0" delay={20} frame={frame} fps={fps} icon={
            <svg width="50" height="34" viewBox="0 0 300 200" fill="none">
              <ellipse cx="150" cy="130" rx="100" ry="70" fill="#00A1E0"/>
              <ellipse cx="220" cy="80" rx="70" ry="58" fill="#00A1E0"/>
              <ellipse cx="80" cy="100" rx="58" ry="46" fill="#00A1E0"/>
              <ellipse cx="150" cy="68" rx="84" ry="64" fill="#00A1E0"/>
            </svg>
          } />
          <CrmBadge name="Pipedrive" color="#21B462" delay={28} frame={frame} fps={fps} icon={
            <svg width="48" height="48" viewBox="0 0 56 56" fill="none">
              <circle cx="28" cy="28" r="28" fill="#21B462"/>
              <path d="M28 14c-7.7 0-14 6.3-14 14 0 6.4 4.3 11.8 10.2 13.4V46h7.6v-4.6C37.7 39.8 42 34.4 42 28c0-7.7-6.3-14-14-14zm0 22c-4.4 0-8-3.6-8-8s3.6-8 8-8 8 3.6 8 8-3.6 8-8 8z" fill="white"/>
            </svg>
          } />
        </div>

        <div style={{ fontFamily: interFont, fontWeight: 600, fontSize: 17, color: COLORS.muted, marginBottom: 48, opacity: fadeIn(frame, 32, 10) }}>
          + y muchos más CRMs
        </div>

        {/* Feature row */}
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 20 }}>
          {[
            { delay: 22, title: 'Mapeo Inteligente', icon: <svg width="26" height="26" viewBox="0 0 24 24" fill="none" stroke={COLORS.beige} strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"><circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/></svg>, desc: 'Sincronizamos con tus campos personalizados. Sin forzar estructuras.' },
            { delay: 30, title: 'Seguridad GDPR', icon: <svg width="26" height="26" viewBox="0 0 24 24" fill="none" stroke={COLORS.beige} strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"><path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/></svg>, desc: 'Datos cifrados en la UE. Tu soberanía de datos es nuestra prioridad.' },
          ].map((c) => (
            <div key={c.title} style={{
              ...slamEntry(frame, fps, c.delay),
              padding: '28px 32px', borderRadius: 28,
              backgroundColor: 'rgba(255,255,255,0.7)', border: '1px solid rgba(0,0,0,0.06)',
              display: 'flex', gap: 18, alignItems: 'flex-start', textAlign: 'left',
            }}>
              <div style={{ width: 48, height: 48, borderRadius: 13, backgroundColor: COLORS.creamDark, display: 'flex', alignItems: 'center', justifyContent: 'center', flexShrink: 0 }}>
                {c.icon}
              </div>
              <div>
                <div style={{ fontFamily: interFont, fontWeight: 800, fontSize: 16, letterSpacing: '0.15em', textTransform: 'uppercase', color: COLORS.beige, marginBottom: 8 }}>{c.title}</div>
                <div style={{ fontFamily: interFont, fontWeight: 400, fontSize: 16, color: COLORS.muted, lineHeight: 1.5 }}>{c.desc}</div>
              </div>
            </div>
          ))}
        </div>
      </div>
    </AbsoluteFill>
  );
};
