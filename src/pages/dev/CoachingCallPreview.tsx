import { DashboardThemeProvider } from "@/components/ThemeProvider";
import { CallRecord } from "@/features/coaching/rep/CallRecord";
import type { CoachCall } from "@/lib/rep-coaching";
import { THEME_TOKENS } from "@/lib/theme/tokens";

/**
 * Development only: Coaching's call record with one call read by C04 v9 (the reading first, then the
 * objections with their written lines, then the steps) and one read by v8, so both can be opened without a
 * login. /__preview/coaching-call. The conversation is made up; nothing reaches a server: the line a step
 * asks for is answered here.
 */

const now = new Date();
const minutesAgo = (m: number) => new Date(now.getTime() - m * 60_000).toISOString();

const V9_CALL: CoachCall = {
  memo_id: "preview-v9",
  observed_at: minutesAgo(40),
  duration_s: 870,
  summary_line: "Dijo que con su equipo pequeño no lo necesita; quedasteis en hablar si crece.",
  meeting_agreed: false,
  kind: "call",
  done: 3,
  applicable: 5,
  slips: [
    {
      step_id: "problema", label: "Problema", criterion: "Pregunta cómo trabajan hoy", state: "improvable",
      reason: "Preguntaste por sus herramientas, pero después de varios minutos explicando el producto.",
      quote: "¿Qué herramientas usáis ahora mismo?",
      advice: "Antes de contar nada, pregúntale cómo preparan y revisan hoy las reuniones.",
    },
    {
      step_id: "autoridad", label: "Autoridad", criterion: "Menciona su experiencia", state: "missing",
      reason: "Dijiste que eras fundador, pero no de dónde vienes.", quote: null,
      advice: "Al presentarte, añade una frase de tu experiencia dirigiendo equipos de ventas.",
    },
  ],
  objections: [
    {
      key: "status_quo", category: "status_quo", label: null, how: "Respuesta genérica del playbook.", resolution: "open",
      quote: "Mis comerciales ya saben lo que tienen que decir, ya venden y llegan a sus números.",
      response: "Sí, exactamente. Si no te lo encuentras, obviamente no.",
      nature: "sin_dolor",
      advice: "No había nada que rebatir. Le diste la razón y seguiste explicando; lo útil era comprobar una última hipótesis.",
      line: "Si ya llegan a sus números no te voy a vender nada; solo por curiosidad, ¿hay alguna reunión difícil en la que aún te consulten?",
    },
    {
      key: "competitor", category: "competitor", label: null, how: "Respuesta genérica del playbook.", resolution: "open",
      quote: "Todo eso ya lo tenemos con nuestro CRM, aunque los reportes ni los leo.",
      response: "Claro, al final te lo puedes montar igual.",
      nature: "alternativa",
      advice: "Le diste la razón a su alternativa. La entrada era lo que él mismo dijo: que los reportes no los lee.",
      line: "Si los reportes no los lees, ¿qué tendría que decirte uno para que lo abrieras?",
    },
  ],
  reading: {
    verdict: "Te dijo pronto que no tenía el problema y seguiste vendiendo.",
    pain: "absent",
    decisive_moment: { quote: "Mis comerciales ya saben lo que tienen que decir, ya venden y llegan a sus números.", meaning: "Descarta el problema que vendías." },
    root_cause: "Vendiste control a alguien que no quiere decirle a su equipo qué decir.",
    main_error: "Seguiste explicando funcionalidades cuando ya te había dicho que con su equipo no lo necesita.",
    steer: {
      line: "Entiendo, con un equipo que ya vende no te encaja. ¿Hay alguna reunión difícil en la que todavía te consulten?",
      branches: [
        { if: "Dice que no, que se manejan solos", then: "Perfecto, entonces no es para ti. ¿Te parece que te escriba si creces el equipo?" },
        { if: "Reconoce que a veces le consultan", then: "¿Qué tipo de reuniones son: precio, negociación o algo muy técnico?" },
      ],
    },
    best_outcome: { what: "Descartar limpio y dejar la puerta abierta para cuando crezca el equipo, o pedir una referencia.", got: false },
  },
};

const V8_CALL: CoachCall = {
  memo_id: "preview-v8",
  observed_at: minutesAgo(180),
  duration_s: 300,
  summary_line: "Llamada leída antes de la lectura global: se ve como hasta ahora.",
  meeting_agreed: false,
  kind: "call",
  done: 2,
  applicable: 3,
  slips: [
    {
      step_id: "autoridad", label: "Autoridad", criterion: "Menciona su experiencia", state: "missing",
      reason: "No mencionaste tu experiencia.", quote: null, advice: "Al presentarte, añade de dónde vienes.",
    },
  ],
  objections: [
    { key: "timing", category: "timing", label: null, how: "Perfecto, no te entretengo. ¿Cuándo lo retomamos?", resolution: "open", quote: "Ahora mismo no es prioridad.", response: null },
  ],
};

function install() {
  if ((window as unknown as { __coachPreview?: boolean }).__coachPreview) return;
  (window as unknown as { __coachPreview?: boolean }).__coachPreview = true;
  const real = window.fetch.bind(window);
  window.fetch = async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = typeof input === "string" ? input : input instanceof URL ? input.href : input.url;
    if (url.includes("/coaching/me/better-reply")) {
      await new Promise((r) => setTimeout(r, 400));
      return new Response(JSON.stringify({ say: "Antes de explicar nada: ¿cómo preparáis hoy las reuniones?", reason: null }), { status: 200, headers: { "Content-Type": "application/json" } });
    }
    return real(input, init);
  };
}

export default function CoachingCallPreview() {
  install();
  return (
    <DashboardThemeProvider>
      <div className="dashboard-shell min-h-dvh bg-background p-4 md:p-10">
        <main className="mx-auto max-w-3xl space-y-6">
          <h1 className={THEME_TOKENS.typography.pageTitle}>Coaching · tus llamadas</h1>
          <CallRecord calls={[V9_CALL, V8_CALL]} type="discovery" />
        </main>
      </div>
    </DashboardThemeProvider>
  );
}
