import { useState, type ReactNode } from "react";
import { useSearchParams } from "react-router-dom";
import { DashboardThemeProvider } from "@/components/ThemeProvider";
import type { GapSession, ModelProposal } from "@/features/playbooks/assistantApi";
import { GapAssistantView } from "@/features/playbooks/components/GapAssistant";
import { ImproveHubView } from "@/features/playbooks/components/ImproveHub";
import { ModelCallImport } from "@/features/playbooks/components/ModelCallImport";
import { ModelCallProposalsView } from "@/features/playbooks/components/ModelCallProposals";
import { UnderstoodSummary } from "@/features/playbooks/components/UnderstoodSummary";
import { THEME_TOKENS } from "@/lib/theme/tokens";
import { cn } from "@/lib/utils";

/**
 * Development only (the route is not in the production bundle): every state of the playbook assistant screens with
 * made-up data and no login, to look at them in light, dark and phone width before they meet real data.
 * Open /__preview/playbook-assistant?s=<scenario>.
 */

const REAL = {
  key: "real:1",
  kind: "real" as const,
  question: "Un cliente dijo «Y si no nos gusta, ¿cómo cancelamos el servicio?» ¿Qué respondéis?",
  seen: 3,
  example: "Y si no nos gusta, ¿cómo cancelamos el servicio?",
  motion_key: "discovery",
};
const TOPIC = {
  key: "topic:security",
  kind: "topic" as const,
  question: "Un cliente pregunta «¿Dónde se guardan nuestros datos y qué seguridad tenéis?» ¿Qué respondéis?",
  seen: 0,
  example: "¿Dónde se guardan nuestros datos y qué seguridad tenéis?",
  motion_key: null,
};
const CONFLICT = {
  key: "conflict:pricing",
  kind: "conflict" as const,
  question: "Tu material no coincide sobre los precios: «Desde 39 € al mes por usuario.» frente a «Desde 49 € al mes por usuario.». ¿Cuál es el correcto?",
  seen: 0,
  example: null,
  motion_key: null,
};

const session = (current: GapSession["current"], over: Partial<GapSession> = {}): GapSession => ({
  id: "s1",
  status: "open",
  total: 10,
  answered: 3,
  skipped: 1,
  current,
  pending_text: null,
  ...over,
});

const noop = () => undefined;

const PROPOSALS: ModelProposal[] = [
  {
    id: "p1",
    kind: "step_example",
    step_index: 1,
    text: "Hola Marcos, soy Dani de Vocify, ¿tienes un minuto?",
    excerpt: [{ speaker: "rep", text: "Hola Marcos, soy Dani de Vocify, ¿tienes un minuto?" }],
  },
  {
    id: "p2",
    kind: "objection_branch",
    category: "price",
    when: "dicen que cambiar es caro mientras usan un Excel",
    text: "Reconoce la duda y pregunta cuánto tiempo pierden a la semana apuntando a mano antes de hablar de precio.",
    excerpt: [
      { speaker: "client", text: "Es muy caro cambiar de herramienta ahora mismo." },
      { speaker: "rep", text: "Antes de hablar de precio, ¿cuánto tiempo pierde el equipo a la semana apuntando a mano?" },
    ],
  },
];

function Proposals({ warning = false, skipped = {} }: { warning?: boolean; skipped?: Record<string, string> }) {
  const [chosen, setChosen] = useState<Record<string, boolean>>({});
  const [swapped, setSwapped] = useState(false);
  return (
    <div className="mx-auto max-w-xl">
      <ModelCallProposalsView
        proposals={PROPOSALS}
        stepLabel={() => "Apertura con permiso"}
        objectionLabel={() => "Precio"}
        speakerWarning={warning}
        swapped={swapped}
        chosen={chosen}
        texts={{}}
        skipped={skipped}
        applying={false}
        onToggle={(id, on) => setChosen((now) => ({ ...now, [id]: on }))}
        onText={noop}
        onDiscard={noop}
        onSwap={() => setSwapped((now) => !now)}
        onApply={noop}
        onOwn={noop}
      />
    </div>
  );
}

function Gap({ s, saved = null, saving = false, problem = null, status = "ready", start = "" }: {
  s: GapSession | null;
  saved?: { line: string } | null;
  saving?: boolean;
  problem?: string | null;
  status?: "loading" | "ready" | "done" | "error" | "not_activated";
  start?: string;
}) {
  const [value, setValue] = useState(start);
  return (
    <GapAssistantView
      status={status}
      session={s}
      saved={saved}
      saving={saving}
      undoing={false}
      problem={problem}
      value={value}
      onValue={setValue}
      onAnswer={noop}
      onSkip={noop}
      onUndo={noop}
      onTry={noop}
      onBack={noop}
      onRetry={noop}
    />
  );
}

function Hub({ line, primary, view = null, views = ["assistant"] }: { line: string; primary: string; view?: "assistant" | "trial" | "improve" | null; views?: ("assistant" | "trial" | "improve")[] }) {
  return <ImproveHubView view={view} views={views} line={line} primaryLabel={primary} onView={noop} onPrimary={noop} />;
}

const SCENARIOS: { id: string; label: string; render: () => ReactNode }[] = [
  { id: "hub-fresh", label: "Portada, primera vez", render: () => <Hub line="Vocify te hace unas preguntas para completar el playbook. Son unos 10 minutos." primary="Responder lo que falta" /> },
  { id: "hub-open", label: "Portada, preguntas pendientes", render: () => <Hub line="Tienes 6 preguntas por responder." primary="Continuar" /> },
  { id: "hub-views", label: "Portada, con vistas", render: () => <Hub view="assistant" views={["assistant", "trial", "improve"]} line="Tienes 6 preguntas por responder." primary="Continuar" /> },
  {
    id: "understood",
    label: "Lo que he entendido",
    render: () => (
      <UnderstoodSummary summary={{ types: 2, steps: 9, objections: 4, questions: 12, proofs: 1 }} failed={[]} conflicts readError={() => ""} onNext={noop} onLater={noop} />
    ),
  },
  {
    id: "understood-failed",
    label: "Lo que he entendido, con un archivo ilegible",
    render: () => (
      <UnderstoodSummary summary={{ types: 1, steps: 4, objections: 2, questions: 0, proofs: 0 }} failed={[{ name: "nota-de-voz.m4a", code: "audio_has_no_speech" }]} conflicts={false} readError={() => "No se oye nada en el audio."} onNext={noop} onLater={noop} />
    ),
  },
  { id: "model-form", label: "Llamada modelo, formulario", render: () => <ModelCallImport open onOpenChange={noop} motionKey="discovery" typeName="Llamada en frío" onApplied={noop} /> },
  { id: "model-proposals", label: "Llamada modelo, propuestas", render: () => <Proposals /> },
  { id: "model-warning", label: "Llamada modelo, hablantes dudosos", render: () => <Proposals warning /> },
  { id: "model-skipped", label: "Llamada modelo, una no cabe", render: () => <Proposals skipped={{ p2: "guidance_too_long" }} /> },
  { id: "gap-loading", label: "Pregunta, cargando", render: () => <Gap s={null} status="loading" /> },
  { id: "gap-real", label: "Pregunta de llamadas reales", render: () => <Gap s={session(REAL)} /> },
  { id: "gap-topic", label: "Pregunta habitual", render: () => <Gap s={session(TOPIC, { answered: 0, skipped: 0 })} /> },
  { id: "gap-conflict", label: "Datos que no coinciden", render: () => <Gap s={session(CONFLICT, { answered: 1, skipped: 0 })} /> },
  { id: "gap-writing", label: "Pregunta, escribiendo", render: () => <Gap s={session(REAL)} start="Cancelan cuando quieran desde Ajustes; no hay permanencia y no se cobra el mes siguiente." /> },
  { id: "gap-saving", label: "Pregunta, guardando", render: () => <Gap s={session(REAL)} saving start="Cancelan cuando quieran desde Ajustes." /> },
  { id: "gap-saved", label: "Guardado, siguiente pregunta", render: () => <Gap s={session(TOPIC, { answered: 4 })} saved={{ line: "Añadida la respuesta a «Cancelar el servicio»." }} /> },
  { id: "gap-problem", label: "Pregunta, error al guardar", render: () => <Gap s={session(REAL)} start="Cancelan cuando quieran." problem="Alguien ha cambiado el playbook a la vez. Tu respuesta sigue aquí: vuelve a guardar." /> },
  { id: "gap-done", label: "Todo respondido", render: () => <Gap s={session(null, { answered: 8, skipped: 2, status: "done" })} status="done" saved={{ line: "Añadida la respuesta a «Dónde se guardan los datos»." }} /> },
  { id: "gap-error", label: "No se pudo cargar", render: () => <Gap s={null} status="error" /> },
  { id: "gap-off", label: "Aún sin activar", render: () => <Gap s={null} status="not_activated" /> },
];

export default function PlaybookAssistantPreview() {
  const [params, setParams] = useSearchParams();
  const active = SCENARIOS.find((item) => item.id === params.get("s")) ?? SCENARIOS[0];
  // &still=1 freezes every animation, so a screenshot shows the final state of a screen.
  const still = params.get("still") === "1";
  return (
    <DashboardThemeProvider>
      {still ? <style>{"*,*::before,*::after{animation:none!important;transition:none!important}"}</style> : null}
      <div className="dashboard-shell min-h-dvh w-full bg-background p-4 md:p-8">
        <div className="mx-auto max-w-5xl space-y-6">
          <nav aria-label="Escenarios" className="flex flex-wrap gap-1.5">
            {SCENARIOS.map((item) => (
              <button
                key={item.id}
                type="button"
                onClick={() => setParams({ s: item.id })}
                className={cn(
                  THEME_TOKENS.interaction.navPill,
                  item.id === active.id ? THEME_TOKENS.interaction.navPillActive : THEME_TOKENS.interaction.navPillIdle,
                )}
              >
                {item.label}
              </button>
            ))}
          </nav>
          <div className={THEME_TOKENS.motion.fadeIn} key={active.id}>
            {active.render()}
          </div>
        </div>
      </div>
    </DashboardThemeProvider>
  );
}
