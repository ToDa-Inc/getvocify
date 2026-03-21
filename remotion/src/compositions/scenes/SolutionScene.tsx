import React from 'react';
import { AbsoluteFill, useCurrentFrame, useVideoConfig } from 'remotion';
import { COLORS } from '../../lib/constants';
import { interFont, garamondFont } from '../../Root';
import { snapIn, snapUp, slamEntry, fadeIn } from '../../lib/animations';

const Card: React.FC<{
  icon: React.ReactNode; title: string; desc: string; delay: number; frame: number; fps: number;
}> = ({ icon, title, desc, delay, frame, fps }) => (
  <div style={{
    ...slamEntry(frame, fps, delay),
    background: 'rgba(255,255,255,0.75)',
    border: '1px solid rgba(0,0,0,0.06)', borderRadius: 36,
    padding: '40px 32px', textAlign: 'center',
    boxShadow: '0 6px 24px rgba(0,0,0,0.05)',
  }}>
    <div style={{
      width: 84, height: 84, borderRadius: 22, backgroundColor: COLORS.beige,
      display: 'flex', alignItems: 'center', justifyContent: 'center',
      margin: '0 auto 24px', boxShadow: '0 6px 20px rgba(0,0,0,0.14)',
    }}>
      {icon}
    </div>
    <div style={{
      fontFamily: interFont, fontWeight: 800, fontSize: 16,
      letterSpacing: '0.2em', textTransform: 'uppercase', color: COLORS.beige, marginBottom: 12,
    }}>{title}</div>
    <div style={{ fontFamily: interFont, fontWeight: 400, fontSize: 16, color: COLORS.muted, lineHeight: 1.6 }}>
      {desc}
    </div>
  </div>
);

export const SolutionScene: React.FC = () => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();

  return (
    <AbsoluteFill style={{
      background: `radial-gradient(ellipse at 80% 10%, hsla(35,25%,35%,0.06) 0, transparent 55%), hsl(40,33%,96%)`,
      display: 'flex', flexDirection: 'column',
      alignItems: 'center', justifyContent: 'center', padding: '60px 80px',
    }}>
      <div style={{ textAlign: 'center', width: '100%', maxWidth: 1440 }}>
        <div style={{
          fontFamily: interFont, fontWeight: 700, fontSize: 14,
          letterSpacing: '0.3em', textTransform: 'uppercase', color: COLORS.beige, marginBottom: 18,
          opacity: fadeIn(frame, 0, 8), transform: snapUp(frame, fps, 0, 20),
        }}>La Solución</div>

        <div style={{
          fontFamily: interFont, fontWeight: 800, fontSize: 74,
          letterSpacing: '-2px', lineHeight: 1.1, color: COLORS.foreground, marginBottom: 48,
          opacity: fadeIn(frame, 4, 10), transform: snapUp(frame, fps, 4, 40),
        }}>
          Tu asistente de ventas{' '}
          <span style={{ fontFamily: garamondFont, fontWeight: 500, fontStyle: 'italic', color: COLORS.beige }}>omnipotente.</span>
        </div>

        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 24, marginBottom: 44 }}>
          <Card frame={frame} fps={fps} delay={14}
            title="Actualiza el CRM"
            desc="Tratos, contactos y presupuestos. 98% precisión. 60 segundos."
            icon={<svg width="42" height="42" viewBox="0 0 24 24" fill="none" stroke={COLORS.cream} strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"><path d="M12 2a3 3 0 0 0-3 3v7a3 3 0 0 0 6 0V5a3 3 0 0 0-3-3z"/><path d="M19 10v2a7 7 0 0 1-14 0v-2"/><line x1="12" y1="19" x2="12" y2="22"/></svg>}
          />
          <Card frame={frame} fps={fps} delay={22}
            title="Crea Tareas"
            desc={`"Llama a Carlos el martes." → Tarea creada. Sola.`}
            icon={<svg width="42" height="42" viewBox="0 0 24 24" fill="none" stroke={COLORS.cream} strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"><path d="M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2m-6 9l2 2 4-4"/></svg>}
          />
          <Card frame={frame} fps={fps} delay={30}
            title="Envía Emails"
            desc="Borradores de seguimiento listos. Un clic para enviar."
            icon={<svg width="42" height="42" viewBox="0 0 24 24" fill="none" stroke={COLORS.cream} strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"><path d="M3 8l7.89 5.26a2 2 0 002.22 0L21 8M5 19h14a2 2 0 002-2V7a2 2 0 00-2-2H5a2 2 0 00-2 2v10a2 2 0 002 2z"/></svg>}
          />
        </div>

        <div style={{
          display: 'inline-flex', alignItems: 'center', gap: 12,
          padding: '14px 36px', borderRadius: 48,
          backgroundColor: COLORS.beige, color: COLORS.cream,
          fontFamily: interFont, fontWeight: 700, fontSize: 18,
          letterSpacing: '0.1em', textTransform: 'uppercase',
          boxShadow: '0 8px 32px rgba(0,0,0,0.14)',
          opacity: fadeIn(frame, 44, 8),
          transform: `scale(${snapIn(frame, fps, 44)})`,
        }}>
          ✓ Cero tareas manuales
        </div>
      </div>
    </AbsoluteFill>
  );
};
