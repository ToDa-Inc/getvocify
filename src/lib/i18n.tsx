import React, { createContext, useContext, useState, ReactNode, useEffect } from 'react';
import { productCatalog, type ProductTranslations } from './product-catalog';
import { setApiRequestLanguage, type ApiRequestLanguage } from '@/shared/lib/api-request-language';
import {
  appLanguageToPersistFromVisit,
  htmlLang,
  publicPathForLanguage,
  readStoredAppLanguage,
  resolveAppLanguage,
  shouldRewritePathForLanguage,
  writeStoredAppLanguage,
} from './app-language';

export type Language = 'EN' | 'ES';

interface LanguageContextType {
  language: Language;
  setLanguage: (lang: Language) => void;
  t: any;
}

const translations = {
  EN: {
    nav: {
      product: "Product",
      teams: "Teams",
      pricing: "Pricing",
      mcp: "Connect your AI",
      login: "Login",
      getStarted: "Get Started",
      download: "Download",
      menus: {
        product: [
          { title: "Before the conversation", desc: "Walk into every sales conversation with the full account story." },
          { title: "During the conversation", desc: "Answer hard questions with live, trusted context." },
          { title: "After the conversation", desc: "Turn conversations into follow-up and clean CRM data." },
          { title: "Coaching", desc: "See what drives performance across every sales conversation." },
        ],
        teams: [
          { title: "SDRs", desc: "Spend more time selling, and selling well." },
          { title: "Account Executives", desc: "Sharper discovery and precise answers on technical deals." },
          { title: "Sales managers", desc: "Coach with playbook data, not hunches." },
          { title: "Field reps", desc: "Talk to your CRM over WhatsApp, on the road." },
          { title: "RevOps", desc: "CRM data you can trust, without chasing anyone." },
        ],
      },
    },
    hero: {
      title1: "An unfair advantage",
      title2: "In every sale.",
      title2Prefix: "in every",
      title2Word: "sale.",
      subtitle1: "We prepare you beforehand, help you during,",
      subtitle2: "and automate all the admin",
      subtitle3: "afterwards.",
      cta1: "Book a Demo",
      cta2: "See How It Works",
      scroll: "Scroll to explore",
      trust1: "GDPR Compliant",
      trust2: "Doesn't replace your CRM",
      trust3: "EU-hosted data",
    },
    demo: {
      title: "Vocify in 50 seconds",
      subtitle: "See how Vocify turns a voice memo into structured CRM updates.",
    },
    integrations: {
      title: "Connects with the CRM and tools you already use",
      more: "+100 more",
    },
    bestRep: {
      label: "The question",
      title1: "How much more would you sell if everyone spoke",
      title2: "like your best rep?",
      body: "Your best rep has no secret gift. They run the playbook better than anyone else. Vocify puts that playbook in every rep's head, in every conversation.",
    },
    chapters: {
      label: "How it works",
      title1: "Before, during and after",
      title2: "every conversation.",
      subtitle: "Vocify works in the three moments that decide whether a deal moves forward.",
      sample: "Sample data",
      before: {
        tab: "Before",
        eyebrow: "Before the conversation",
        title1: "Walk in with the full",
        title2: "account story.",
        desc: "Account context, history, open questions and a plan for this specific conversation, not a generic summary.",
        badge: "Today · 11:30",
        account: "Acme Corp · Sarah Chen",
        summaryTitle: "Context",
        summary: "Second call. Interested in Enterprise, budget still open.",
        askTitle: "Questions to ask",
        asks: ["Who else is part of the decision?", "What budget is set aside for Q1?"],
        watchTitle: "Watch for",
        },
      during: {
        tab: "During",
        eyebrow: "During the conversation",
        title1: "Hard questions,",
        title2: "answered live.",
        desc: "Objections, product questions and your playbook steps, one glance away while you talk. Technical sale? Vocify knows your product and your context.",
        said: "This looks expensive compared with what we use today.",
        objection: "Objection · price",
        answerTitle: "Suggested answer",
        answer: "Anchor on the admin time recovered per rep, then ask how many hours the team spends on the CRM today.",
        playbookTitle: "Playbook",
        playbook: [
          { label: "Agenda agreed", done: true },
          { label: "Pain identified", done: true },
          { label: "Budget confirmed", done: false },
          { label: "Decision maker", done: false },
          { label: "Next step", done: false },
        ],
      },
      after: {
        tab: "After",
        eyebrow: "After the conversation",
        title1: "Follow-up and CRM,",
        title2: "clean without touching a thing.",
        desc: "It is done when you finish: CRM, emails, tasks. Spend your time on the next conversation, or on reviewing what you could do better.",
        doneTitle: "Done when you finish",
        items: ["CRM fields updated", "Call notes written", "Follow-up email drafted", "Tasks created with dates", "Next step scheduled", "Full transcript saved"],
      },
    },
    coaching: {
      label: "Coaching",
      title1: "See why your sales drop,",
      title2: "when and how.",
      subtitle: "Playbook adherence is the metric that moves your close rate directly. Vocify measures it on every conversation and shows you where to correct.",
      points: [
        "Which playbook step each rep skips",
        "At what point in the conversation the deal slips",
        "How your best reps handle that exact moment",
      ],
      sample: "Illustrative example",
      adherenceTitle: "Playbook adherence",
      team: "of the team",
      weak: "To fix",
      steps: [
        { name: "Agenda", value: 92 },
        { name: "Discovery", value: 74 },
        { name: "Objections", value: 58 },
        { name: "Next step", value: 81 },
      ],
      timelineTitle: "Conversation timeline",
      phases: ["Intro", "Discovery", "Objection", "Close"],
      moment: "Minute 14 · Price objection left unanswered",
      fix: "Your best reps answer with value before price.",
    },
    capture: {
      label: "Capture",
      title1: "Every interaction captured,",
      title2: "no bots in the room.",
      subtitle: "Nobody strange joins your conversations. Vocify records what you say from your computer and your phone, and understands it.",
      cube: { title: "Every interaction", desc: "Calls, meetings, field visits and WhatsApp. Nothing goes uncaptured.", faces: ["Calls", "Meetings", "Phone", "WhatsApp", "Visits", "Computer"] },
      cards: [
        { title: "No bots, on any device", desc: "Vocify records from your computer, with no awkward guests in your meeting. Calls you make from your phone are recorded too, even when your dialer won't allow a personal number." },
        { title: "Technical products", desc: "Vocify knows your product and your context, so answers come from your material, not generic advice." },
        { title: "Reps in the field", desc: "Teams on the road update the CRM and fill in the data with a WhatsApp bot." },
      ],
      languages: "100+ languages",
      languagesList: "Spanish · Catalan · Portuguese · Italian · French",
    },
    teams: {
      label: "Teams",
      title1: "Built for every",
      title2: "sales role.",
      subtitle: "SDRs, AEs, managers, reps in the field and RevOps. Vocify fits how each one works.",
      cards: [
        "Context before you dial, help with objections and no admin between one contact and the next.",
        "Discovery without gaps, technical answers from your own material and all the follow-up done when you finish.",
        "Playbook adherence for every rep, to see where a deal slips and how to correct it.",
        "Talk to your CRM over WhatsApp: send an update as you leave the visit and the CRM catches up.",
        "CRM fields filled from the conversation and reviewed before they land, in HubSpot, Salesforce or Pipedrive.",
      ],
    },
    pricing: {
      label: "Pricing",
      title1: "Simple plans.",
      title2: "Per workspace seat.",
      subtitle: "Both plans include HubSpot sync, transcription, and CRM updates. Pro adds the dialer.",
      starterTagline: "Every conversation, captured and closed.",
      proTagline: "The same craft, plus a dialer for going further.",
      perMonth: "/ month",
      orYearly: "or €{yearly} / year (€{monthly} / month)",
      proBadge: "Includes dialer",
      cta: "Book a demo",
      note: "Prices in euros, billed per workspace seat. Annual billing saves about 17%.",
      starterFeatures: [
        "Voice memos and transcription",
        "HubSpot field updates, notes, and tasks",
        "Follow-ups and coaching",
        "No Vocify dialer",
      ],
      proFeatures: [
        "Everything in Starter",
        "Vocify dialer with 1,000 minutes included",
        "Calls on the HubSpot timeline with recording",
      ],
    },
    faq: {
      label: "FAQ",
      title1: "Frequently Asked",
      title2: "Questions.",
      items: [
        { q: "Does this work with my CRM?", a: "Yes. We support HubSpot, Salesforce, and Pipedrive today. More integrations coming soon." },
        { q: "How accurate is the AI?", a: "85-90% accuracy out of the box. You always review before it updates your CRM." },
        { q: "What if I speak Spanish/French/German?", a: "Vocify transcribes in more than 100 languages, including Spanish, Catalan, Portuguese, Italian and French." },
        { q: "Is my data secure?", a: "Yes. GDPR compliant. Data stored in EU. Encrypted in transit and at rest." },
        { q: "Can I edit before it updates my CRM?", a: "Absolutely. You review and approve every update." }
      ]
    },
    finalCta: {
      title1: "Your best rep,",
      title2: "across the whole team.",
      subtitle: "No training. No CRM migration. No long setup.",
      trial: "15-Minute Demo",
      noCredit: "With the founder. No commitment.",
      claim: "Book a Call",
      questions: "Questions? Reach out at",
      responseTime: "Response time: Under 2 hours (M-F)",
      download: "Download the desktop app",
    },
    footer: {
      tagline: "The copilot that updates your CRM while you keep selling. No admin, no data left behind.",
      product: "Product",
      teams: "Teams",
      company: "Company",
      links: { how: "How it works", coaching: "Coaching", mcp: "Connect your AI (MCP)", docs: "HubSpot setup guide", support: "Support", demo: "Book a demo", about: "About us", blog: "Blog", privacy: "Privacy policy", terms: "Terms of service" },
      rights: "All rights reserved.",
      madeFor: "for sales teams.",
    },
    product: productCatalog.EN,
  },
  ES: {
    nav: {
      product: "Producto",
      teams: "Equipos",
      pricing: "Precios",
      mcp: "Conecta tu IA",
      login: "Acceder",
      getStarted: "Empezar",
      download: "Descargar",
      menus: {
        product: [
          { title: "Antes de la conversación", desc: "Llega a cada conversación de venta con la historia completa de la cuenta." },
          { title: "Durante la conversación", desc: "Responde a las preguntas difíciles con contexto fiable, en vivo." },
          { title: "Después de la conversación", desc: "Convierte las conversaciones en seguimiento y datos de CRM limpios." },
          { title: "Coaching", desc: "Mide qué impulsa el rendimiento en cada conversación de venta." },
        ],
        teams: [
          { title: "SDRs", desc: "Dedica más tiempo a vender, y a vender bien." },
          { title: "Account Executives", desc: "Descubrimiento más afilado y respuestas precisas en ventas técnicas." },
          { title: "Directores comerciales", desc: "Entrena con datos del playbook, no con intuiciones." },
          { title: "Comerciales de calle", desc: "Habla con tu CRM por WhatsApp, en ruta." },
          { title: "RevOps", desc: "Datos de CRM en los que confiar, sin perseguir a nadie." },
        ],
      },
    },
    hero: {
      title1: "Una ventaja injusta",
      title2: "En cada venta.",
      title2Prefix: "en cada",
      title2Word: "venta.",
      subtitle1: "Te preparamos antes, te ayudamos durante",
      subtitle2: "y automatizamos todo el admin",
      subtitle3: "después.",
      cta1: "Reservar demo",
      cta2: "Ver cómo funciona",
      scroll: "Desliza para explorar",
      trust1: "Cumple GDPR",
      trust2: "No sustituye tu CRM",
      trust3: "Datos alojados en la UE",
    },
    demo: {
      title: "Vocify en 50 segundos",
      subtitle: "Mira cómo Vocify convierte una nota de voz en datos estructurados en tu CRM.",
    },
    integrations: {
      title: "Se conecta con el CRM y las herramientas que ya usas",
      more: "+100 más",
    },
    bestRep: {
      label: "La pregunta",
      title1: "¿Cuánto venderías si todos hablaran",
      title2: "como tu mejor comercial?",
      body: "Tu mejor comercial no tiene un don secreto. Ejecuta el playbook mejor que nadie. Vocify pone ese playbook en la cabeza de cada comercial, en cada conversación.",
    },
    chapters: {
      label: "Cómo funciona",
      title1: "Antes, durante y después de",
      title2: "cada conversación.",
      subtitle: "Vocify trabaja en los tres momentos que deciden si el trato avanza.",
      sample: "Datos de ejemplo",
      before: {
        tab: "Antes",
        eyebrow: "Antes de la conversación",
        title1: "Llega con la historia",
        title2: "completa de la cuenta.",
        desc: "Contexto de la cuenta, historial, preguntas pendientes y un plan para esta conversación concreta, no un resumen genérico.",
        badge: "Hoy · 11:30",
        account: "Acme Corp · Sarah Chen",
        summaryTitle: "Contexto",
        summary: "Segunda llamada. Interesada en Enterprise, presupuesto aún abierto.",
        askTitle: "Preguntas para hacer",
        asks: ["¿Quién más participa en la decisión?", "¿Qué presupuesto hay reservado para el Q1?"],
        watchTitle: "Ojo con",
        },
      during: {
        tab: "Durante",
        eyebrow: "Durante la conversación",
        title1: "Preguntas difíciles,",
        title2: "respondidas en vivo.",
        desc: "Objeciones, dudas de producto y los pasos de tu playbook, a un vistazo mientras hablas. ¿Venta técnica? Vocify conoce tu producto y tu contexto.",
        said: "Nos parece caro comparado con lo que usamos hoy.",
        objection: "Objeción · precio",
        answerTitle: "Respuesta sugerida",
        answer: "Ancla en el tiempo de admin recuperado por comercial y pregunta cuántas horas dedica hoy el equipo al CRM.",
        playbookTitle: "Playbook",
        playbook: [
          { label: "Agenda acordada", done: true },
          { label: "Dolor identificado", done: true },
          { label: "Presupuesto confirmado", done: false },
          { label: "Decisor", done: false },
          { label: "Siguiente paso", done: false },
        ],
      },
      after: {
        tab: "Después",
        eyebrow: "Después de la conversación",
        title1: "Seguimiento y CRM limpios,",
        title2: "sin tocar nada.",
        desc: "Terminas y está hecho: CRM, emails, tareas. Dedica tu tiempo a la siguiente conversación, o a revisar qué puedes mejorar.",
        doneTitle: "Hecho al terminar",
        items: ["Campos del CRM actualizados", "Notas de la llamada", "Email de seguimiento", "Tareas con fecha", "Siguiente paso agendado", "Transcripción completa"],
      },
    },
    coaching: {
      label: "Coaching",
      title1: "Entiende por qué se caen tus ventas,",
      title2: "cuándo y cómo.",
      subtitle: "La adherencia al playbook es la métrica que impacta directamente en tu tasa de cierre. Vocify la mide en cada conversación y te muestra dónde corregir.",
      points: [
        "Qué paso del playbook se salta cada comercial",
        "En qué momento de la conversación se enfría el trato",
        "Cómo resuelven ese momento tus mejores comerciales",
      ],
      sample: "Ejemplo ilustrativo",
      adherenceTitle: "Adherencia al playbook",
      team: "del equipo",
      weak: "A corregir",
      steps: [
        { name: "Agenda", value: 92 },
        { name: "Descubrimiento", value: 74 },
        { name: "Objeciones", value: 58 },
        { name: "Siguiente paso", value: 81 },
      ],
      timelineTitle: "Línea de tiempo de la conversación",
      phases: ["Intro", "Descubrimiento", "Objeción", "Cierre"],
      moment: "Minuto 14 · Objeción de precio sin responder",
      fix: "Tus mejores comerciales responden con valor antes que con precio.",
    },
    capture: {
      label: "Captura",
      title1: "Cada interacción capturada,",
      title2: "sin bots en la sala.",
      subtitle: "Nadie extraño entra en tus conversaciones. Vocify graba lo que dices desde tu ordenador y tu móvil, y lo entiende.",
      cube: { title: "Todas las interacciones", desc: "Llamadas, reuniones, visitas en calle y WhatsApp. Nada se queda sin capturar.", faces: ["Llamadas", "Reuniones", "Móvil", "WhatsApp", "Visitas", "Ordenador"] },
      cards: [
        { title: "Sin bots, en cualquier dispositivo", desc: "Vocify graba desde tu ordenador, sin invitados raros en tu reunión. Las llamadas que haces desde el móvil también se graban, incluso si tu dialer no admite un número personal." },
        { title: "Productos técnicos", desc: "Vocify conoce tu producto y tu contexto, así que las respuestas salen de tu material, no de consejos genéricos." },
        { title: "Comerciales de calle", desc: "Tus equipos en ruta actualizan el CRM y rellenan los datos con un bot de WhatsApp." },
      ],
      languages: "Más de 100 idiomas",
      languagesList: "Español · Catalán · Portugués · Italiano · Francés",
    },
    teams: {
      label: "Equipos",
      title1: "Pensado para cada",
      title2: "rol de ventas.",
      subtitle: "SDRs, AEs, directores, comerciales de calle y RevOps. Vocify se adapta a cómo trabaja cada uno.",
      cards: [
        "Contexto antes de marcar, ayuda con las objeciones y cero admin entre un contacto y el siguiente.",
        "Descubrimiento sin huecos, respuestas técnicas con tu propio material y todo el seguimiento hecho al terminar.",
        "Adherencia al playbook de cada comercial, para ver dónde se cae un trato y cómo corregirlo.",
        "Hablan con su CRM por WhatsApp: mandan una actualización al salir de la visita y el CRM se pone al día.",
        "Campos del CRM rellenos desde la conversación y revisados antes de entrar, en HubSpot, Salesforce o Pipedrive.",
      ],
    },
    pricing: {
      label: "Precios",
      title1: "Planes sencillos.",
      title2: "Por usuario del workspace.",
      subtitle: "Ambos planes incluyen sync con HubSpot, transcripción y actualizaciones de CRM. Pro añade el dialer.",
      starterTagline: "Cada conversación, capturada y cerrada.",
      proTagline: "Lo mismo, más un dialer para llegar más lejos.",
      perMonth: "/ mes",
      orYearly: "o {yearly}€ / año ({monthly}€ / mes)",
      proBadge: "Incluye dialer",
      cta: "Reservar demo",
      note: "Precios en euros, por usuario del workspace. El pago anual ahorra un ~17%.",
      starterFeatures: [
        "Notas de voz y transcripción",
        "Actualizaciones HubSpot, notas y tareas",
        "Seguimientos y coaching",
        "Sin dialer de Vocify",
      ],
      proFeatures: [
        "Todo lo de Starter",
        "Dialer de Vocify con 1.000 minutos incluidos",
        "Llamadas en la timeline de HubSpot con grabación",
      ],
    },
    faq: {
      label: "FAQ",
      title1: "Preguntas",
      title2: "Frecuentes.",
      items: [
        { q: "¿Funciona con mi CRM?", a: "Sí. Soportamos HubSpot, Salesforce y Pipedrive hoy mismo. Próximamente más integraciones." },
        { q: "¿Qué tan precisa es la IA?", a: "85-90% de precisión de serie. Siempre revisas antes de actualizar el CRM." },
        { q: "¿Qué pasa si hablo español/francés/alemán?", a: "Vocify transcribe en más de 100 idiomas, incluidos español, catalán, portugués, italiano y francés." },
        { q: "¿Mis datos están seguros?", a: "Sí. Cumplimos con GDPR. Datos guardados en la UE. Encriptados en tránsito y reposo." },
        { q: "¿Puedo editar antes de actualizar el CRM?", a: "Absolutamente. Revisas y apruebas cada actualización." }
      ]
    },
    finalCta: {
      title1: "Tu mejor comercial,",
      title2: "en todo el equipo.",
      subtitle: "Sin formación. Sin cambiar de CRM. Sin implantación larga.",
      trial: "Demo de 15 minutos",
      noCredit: "Con el fundador. Sin compromiso.",
      claim: "Reservar llamada",
      questions: "¿Preguntas? Escríbenos a",
      responseTime: "Respuesta: Menos de 2 horas (L-V)",
      download: "Descargar la app de escritorio",
    },
    footer: {
      tagline: "El copiloto que actualiza tu CRM mientras sigues vendiendo. Sin admin, sin datos perdidos.",
      product: "Producto",
      teams: "Equipos",
      company: "Empresa",
      links: { how: "Cómo funciona", coaching: "Coaching", mcp: "Conecta tu IA (MCP)", docs: "Guía de HubSpot", support: "Soporte", demo: "Reservar demo", about: "Sobre nosotros", blog: "Blog", privacy: "Política de privacidad", terms: "Términos del servicio" },
      rights: "Todos los derechos reservados.",
      madeFor: "para equipos de ventas.",
    },
    product: productCatalog.ES,
  }
};

export type { ProductTranslations };

export { translations };

const LanguageContext = createContext<LanguageContextType | undefined>(undefined);

function apiLanguageFromAppLanguage(lang: Language): ApiRequestLanguage {
  return lang === 'EN' ? 'en' : 'es';
}

export const LanguageProvider: React.FC<{ children: ReactNode }> = ({ children }) => {
  const [language, setLanguage] = useState<Language>('ES');

  useEffect(() => {
    const path = window.location.pathname;
    const stored = readStoredAppLanguage();
    const resolved = resolveAppLanguage({ stored, path });
    const toPersist = appLanguageToPersistFromVisit({ stored, path });
    if (toPersist) {
      writeStoredAppLanguage(toPersist);
    }
    setLanguage(resolved);
    setApiRequestLanguage(apiLanguageFromAppLanguage(resolved));
  }, []);

  useEffect(() => {
    document.documentElement.lang = htmlLang(language);
  }, [language]);

  const t = translations[language];

  const handleSetLanguage = (lang: Language) => {
    setLanguage(lang);
    writeStoredAppLanguage(lang);
    setApiRequestLanguage(apiLanguageFromAppLanguage(lang));
    const path = window.location.pathname;
    if (shouldRewritePathForLanguage(path)) {
      window.history.pushState({}, '', publicPathForLanguage(lang));
    }
  };

  return (
    <LanguageContext.Provider value={{ language, setLanguage: handleSetLanguage, t }}>
      {children}
    </LanguageContext.Provider>
  );
};

export const useLanguage = () => {
  const context = useContext(LanguageContext);
  if (context === undefined) {
    throw new Error('useLanguage must be used within a LanguageProvider');
  }
  return context;
};
