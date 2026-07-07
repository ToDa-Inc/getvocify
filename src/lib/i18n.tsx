import React, { createContext, useContext, useState, ReactNode, useEffect } from 'react';

export type Language = 'EN' | 'ES';

interface LanguageContextType {
  language: Language;
  setLanguage: (lang: Language) => void;
  t: any;
}

const translations = {
  EN: {
    nav: {
      features: "Features",
      calculator: "Calculator",
      about: "How it works",
      login: "Login",
      getStarted: "Get Started",
    },
    hero: {
      title1: "Talk for 30 seconds.",
      title2: "And focus on selling.",
      title2Prefix: "And focus on",
      title2Word: "selling.",
      subtitle1: "The copilot that handles everything else.",
      subtitle2: "After a call, a demo, a visit.",
      subtitle3: "Without touching the CRM.",
      cta1: "Book a Demo",
      cta2: "See How It Works",
      scroll: "Scroll to explore",
      trust1: "GDPR Compliant",
      trust2: "Doesn't replace your CRM",
      trust3: "EU-hosted data",
      rotating: ["Never touch the CRM again", "Works after any client conversation", "The CRM finds out before you sit down"],
    },
    demo: {
      title: "Watch the 40-second demo",
      subtitle: "See how Vocify turns a voice memo into structured CRM updates.",
    },
    integrations: {
      text1: "Seamlessly",
      text2: "integrates",
      text3: "with your stack",
    },
    problem: {
      label: "The Problem",
      title1: "The sales rep does two jobs.",
      title2: "One they like. The other, they don't.",
      likeTitle: "The one they like",
      likeItems: ["Visiting", "Calling", "Negotiating", "Closing"],
      hateTitle: "The one they don't",
      hateItems: ["Updating the CRM", "Filling in fields", "Writing follow-ups", "Remembering everything"],
    },
    features: {
      label: "Features",
      title1: "What the",
      title2Prefix: "copilot",
      title2Word: "does.",
      subtitle: "Updates opportunities. Creates tasks. Prepares follow-ups. The rep doesn't touch a thing.",
      f1: { title: "Updates opportunities", desc: "Contacts, deals, and fields — up to date without you touching them." },
      f2: { title: "Understands the conversation", desc: "Pulls out who, how much, when, and what's next — from a normal chat, not a form." },
      f3: { title: "Talks where you already are", desc: "WhatsApp, Slack, Chrome, or in person — no new apps to learn." },
      f4: { title: "Creates tasks and follow-ups", desc: "The next step gets scheduled on its own — who, when, and why." },
      f5: { title: "Speaks your language", desc: "Full support for English, Spanish, French, German, Italian, and Portuguese." },
      f6: { title: "GDPR Compliant", desc: "End-to-end encrypted. Your data stays yours." },
    },
    solution: {
      label: "How It Works",
      title1: "The copilot understands",
      title2: "what you say",
      title3: "and updates the CRM.",
      subtitle: "No new apps. No forms. Just talk.",
      s1: { title: "TALK", desc: "Anywhere — WhatsApp, Slack, Chrome, or in person." },
      s2: { title: "PROCESS", desc: "The copilot understands who, how much, and what's next." },
      s3: { title: "UPDATE", desc: "The CRM is up to date. Tasks and follow-ups created on their own." },
      badge: "Zero manual entry required.",
      example1: "Just met Sarah at Acme Corp. She's interested in Enterprise. Budget is €50K. Decision by Q1. She wants demo next Tuesday. Also mentioned competitor DataCo.",
      label1: "Contact",
      label2: "Company",
      label3: "Deal Value",
      label4: "Next Step",
    },
    comparison: {
      label: "Before / After",
      title1: "How it used to be.",
      title2: "How it is now.",
      without: "Without the copilot",
      with: "With the copilot",
      f1: "Updating the CRM",
      v1: "Happens on its own, right after the call",
      t1: "From memory, at the end of the day (if there's time)",
      f2: "The data",
      v2: "Complete, pulled from the conversation",
      t2: "Incomplete, depends on what you remember",
      f3: "Follow-ups",
      v3: "Created automatically",
      t3: "Forgotten if you didn't write them down",
      f4: "The rep's day",
      v4: "Just selling",
      t4: "Selling and doing admin work",
      f5: "The team's pipeline",
      v5: "Always up to date, for everyone",
      t5: "Depends on each rep updating it",
    },
    useCases: {
      label: "Use Cases",
      title1: "Perfect for Every",
      title2: "Sales Situation.",
      subtitle: "Whether you're in the car, on a call, or in the clinic, Vocify is designed to live where your work happens.",
      uc1: { title: "Field Sales Reps", tag: "Mobile First", desc: "Record notes instantly between client visits. Never lose a detail. CRM updated before you even reach your next meeting." },
      uc2: { title: "B2B Account Executives", tag: "Complex Deals", desc: "Navigate complex multi-stakeholder deals. Track every decision-maker, pain point, and next step with zero friction." },
      uc3: { title: "Medical Device Sales", tag: "Regulated", desc: "Detailed meeting notes with physician-specific terminology. Fully compliant documentation for highly regulated environments." },
      uc4: { title: "Inside Sales Teams", tag: "High Velocity", desc: "Lightning-fast updates after discovery calls. Capture objections, budget shifts, and timelines in the heat of the moment." },
      uc5: { title: "Sales Managers", tag: "Real-time Visibility", desc: "Get a crystalline view of your team's pipeline in real-time. Coach based on objective meeting data, not post-hoc guesses." },
      uc6: { title: "Real Estate Agents", tag: "Property Tours", desc: "Capture property details and client preferences instantly while showing homes. Keep your lead data pristine on the go." },
    },
    socialProof: {
      label: "Testimonials",
      title1: "Elite Sales Teams",
      title2: "Trust Vocify.",
      q1: "I used to spend 45 minutes at end of day doing CRM. Now it takes 5 minutes.",
      q2: "My team's CRM compliance went from 60% to 95% in two weeks. It's a game changer.",
      q3: "I log deals while walking between meetings. My manager thinks I'm a CRM machine.",
      q4: "Finally, a tool that actually saves time instead of creating more work.",
    },
    roi: {
      label: "ROI Calculator",
      title1: "Stop Burning Time.",
      title2: "Calculate Your ROI.",
      subtitle: "See how much admin time your sales team could reclaim with voice-first CRM updates.",
      label1: "Sales Reps",
      label2: "Avg. Salary (€)",
      note1: "Est. 5 hours wasted / rep / week on CRM admin",
      saved: "Total Hours Saved",
      perYear: "/ year",
      potential: "% of payroll (admin time)",
      yearly: "Estimated yearly value of reclaimed time",
      cta: "Reclaim Your Time Now",
    },
    faq: {
      label: "FAQ",
      title1: "Frequently Asked",
      title2: "Questions.",
      items: [
        { q: "Does this work with my CRM?", a: "Yes. We support HubSpot, Salesforce, and Pipedrive today. More integrations coming soon." },
        { q: "How accurate is the AI?", a: "85-90% accuracy out of the box. You always review before it updates your CRM." },
        { q: "What if I speak Spanish/French/German?", a: "Vocify supports 6 languages: English, Spanish, French, German, Italian, Portuguese." },
        { q: "Is my data secure?", a: "Yes. GDPR compliant. Data stored in EU. Encrypted in transit and at rest." },
        { q: "Can I edit before it updates my CRM?", a: "Absolutely. You review and approve every update." }
      ]
    },
    finalCta: {
      title1: "Talk for 30 seconds.",
      title2: "Focus on selling.",
      subtitle: "No training. No CRM migration. No long setup.",
      onboarding: "How to Start",
      trial: "15-Minute Demo",
      noCredit: "With the founder. No commitment.",
      claim: "Book a Call",
      watch: "See How It Works",
      questions: "Questions? Reach out at",
      responseTime: "Response time: Under 2 hours (M-F)",
      steps: [
        "Book 15 minutes",
        "Connect your CRM",
        "Your reps try it day to day",
        "The copilot handles the rest",
        "Your team just sells"
      ]
    }
  },
  ES: {
    nav: {
      features: "Funciones",
      calculator: "Calculadora",
      about: "Cómo funciona",
      login: "Acceder",
      getStarted: "Empezar",
    },
    hero: {
      title1: "Habla 30 segundos.",
      title2: "Y dedícate a vender.",
      title2Prefix: "Y dedícate",
      title2Word: "a vender.",
      subtitle1: "El copiloto que hace todo lo demás.",
      subtitle2: "Después de una llamada, una demo, una visita.",
      subtitle3: "Sin tocar el CRM.",
      cta1: "Reservar demo",
      cta2: "Ver cómo funciona",
      scroll: "Desliza para explorar",
      trust1: "Cumple GDPR",
      trust2: "No sustituye tu CRM",
      trust3: "Datos alojados en la UE",
      rotating: ["No vuelvas a tocar el CRM", "Funciona después de cualquier conversación", "El CRM se entera antes de que te sientes"],
    },
    demo: {
      title: "Demo de 40 segundos",
      subtitle: "Mira cómo Vocify convierte una nota de voz en datos estructurados en tu CRM.",
    },
    integrations: {
      text1: "Se integra",
      text2: "perfectamente",
      text3: "con tus herramientas",
    },
    problem: {
      label: "El Problema",
      title1: "El comercial hace dos trabajos.",
      title2: "Uno le gusta. El otro no.",
      likeTitle: "El que le gusta",
      likeItems: ["Visitar", "Llamar", "Negociar", "Cerrar"],
      hateTitle: "El que no",
      hateItems: ["Actualizar el CRM", "Rellenar campos", "Escribir seguimientos", "Acordarse de todo"],
    },
    features: {
      label: "Funciones",
      title1: "Qué hace",
      title2Prefix: "el",
      title2Word: "copiloto.",
      subtitle: "Actualiza oportunidades. Crea tareas. Prepara seguimientos. El comercial no toca nada.",
      f1: { title: "Actualiza oportunidades", desc: "Contactos, tratos y campos — al día sin que los toques." },
      f2: { title: "Entiende la conversación", desc: "Saca quién, cuánto, cuándo y qué sigue — de una charla normal, no de un formulario." },
      f3: { title: "Habla donde ya estás", desc: "WhatsApp, Slack, Chrome o en persona — sin apps nuevas que aprender." },
      f4: { title: "Crea tareas y seguimientos", desc: "El siguiente paso queda agendado solo, con quién y cuándo." },
      f5: { title: "Habla en tu idioma", desc: "Soporte completo para español, inglés, francés, alemán, italiano y portugués." },
      f6: { title: "Cumple GDPR", desc: "Cifrado de extremo a extremo. Tus datos son tuyos." },
    },
    solution: {
      label: "Cómo Funciona",
      title1: "El copiloto entiende",
      title2: "lo que dices",
      title3: "y actualiza el CRM.",
      subtitle: "Sin apps nuevas. Sin formularios. Solo hablas.",
      s1: { title: "HABLA", desc: "En cualquier sitio — WhatsApp, Slack, Chrome o en persona." },
      s2: { title: "PROCESA", desc: "El copiloto entiende quién, cuánto y qué sigue." },
      s3: { title: "ACTUALIZA", desc: "El CRM se pone al día. Tareas y seguimientos creados solos." },
      badge: "Cero entrada manual requerida.",
      example1: "Acabo de ver a Sarah en Acme Corp. Le interesa Enterprise. Presupuesto 50k€. Decisión en Q1. Quiere demo el próximo martes. También mencionó a DataCo.",
      label1: "Contacto",
      label2: "Empresa",
      label3: "Valor del Trato",
      label4: "Siguiente Paso",
    },
    comparison: {
      label: "Antes y Después",
      title1: "Así se hacía.",
      title2: "Así se hace ahora.",
      without: "Sin copiloto",
      with: "Con copiloto",
      f1: "Actualizar el CRM",
      v1: "Se hace solo, nada más colgar",
      t1: "De memoria, al final del día (si da tiempo)",
      f2: "Los datos",
      v2: "Completos, extraídos de la conversación",
      t2: "Incompletos, según lo que recuerdes",
      f3: "Los seguimientos",
      v3: "Se crean automáticamente",
      t3: "Se olvidan si no los escribiste",
      f4: "El día del comercial",
      v4: "Solo vender",
      t4: "Vender y hacer de administrativo",
      f5: "El pipeline del equipo",
      v5: "Siempre al día, para todos",
      t5: "Depende de que cada uno lo actualice",
    },
    useCases: {
      label: "Casos de Uso",
      title1: "Ideal para cada",
      title2: "situación de ventas.",
      subtitle: "Ya sea en el coche, en una llamada o en la clínica, Vocify está diseñado para vivir donde ocurre tu trabajo.",
      uc1: { title: "Comerciales de Calle", tag: "Móvil Primero", desc: "Graba notas al instante entre visitas. No pierdas ni un detalle. CRM actualizado antes de llegar a la siguiente reunión." },
      uc2: { title: "Account Executives B2B", tag: "Ventas Complejas", desc: "Navega tratos complejos con múltiples partes interesadas. Rastrea cada decisión y próximo paso sin fricción." },
      uc3: { title: "Ventas de Equipos Médicos", tag: "Regulado", desc: "Notas de reunión detalladas con terminología médica. Documentación totalmente compatible para entornos regulados." },
      uc4: { title: "Equipos de Inside Sales", tag: "Alta Velocidad", desc: "Actualizaciones ultra rápidas tras llamadas de descubrimiento. Captura objeciones y presupuestos al momento." },
      uc5: { title: "Directores de Ventas", tag: "Visibilidad Real", desc: "Obtén una visión cristalina del pipeline de tu equipo en tiempo real. Entrena basado en datos objetivos, no suposiciones." },
      uc6: { title: "Agentes Inmobiliarios", tag: "Visitas a Propiedades", desc: "Captura detalles de propiedades y preferencias de clientes al instante durante las visitas. Mantén tus datos impecables." },
    },
    socialProof: {
      label: "Testimonios",
      title1: "Equipos de Elite",
      title2: "Confían en Vocify.",
      q1: "Solía pasar 45 minutos al final del día con el CRM. Ahora me lleva 5 minutos.",
      q2: "El cumplimiento del CRM de mi equipo pasó del 60% al 95% en dos semanas.",
      q3: "Registro tratos mientras camino entre reuniones. Mi jefe cree que soy una máquina.",
      q4: "Finalmente, una herramienta que ahorra tiempo en lugar de crear más trabajo.",
    },
    roi: {
      label: "Calculadora ROI",
      title1: "Deja de quemar tiempo.",
      title2: "Calcula tu ROI.",
      subtitle: "Descubre cuánto tiempo administrativo podría recuperar tu equipo con actualizaciones de CRM por voz.",
      label1: "Comerciales",
      label2: "Salario Medio (€)",
      note1: "Est. 5 horas perdidas / rep / semana en admin del CRM",
      saved: "Horas Totales Ahorradas",
      perYear: "/ año",
      potential: "% coste salarial (tiempo admin)",
      yearly: "Valor anual estimado del tiempo recuperado",
      cta: "Recupera tu tiempo ahora",
    },
    faq: {
      label: "FAQ",
      title1: "Preguntas",
      title2: "Frecuentes.",
      items: [
        { q: "¿Funciona con mi CRM?", a: "Sí. Soportamos HubSpot, Salesforce y Pipedrive hoy mismo. Próximamente más integraciones." },
        { q: "¿Qué tan precisa es la IA?", a: "85-90% de precisión de serie. Siempre revisas antes de actualizar el CRM." },
        { q: "¿Qué pasa si hablo español/francés/alemán?", a: "Vocify soporta 6 idiomas: inglés, español, francés, alemán, italiano y portugués." },
        { q: "¿Mis datos están seguros?", a: "Sí. Cumplimos con GDPR. Datos guardados en la UE. Encriptados en tránsito y reposo." },
        { q: "¿Puedo editar antes de actualizar el CRM?", a: "Absolutamente. Revisas y apruebas cada actualización." }
      ]
    },
    finalCta: {
      title1: "Habla 30 segundos.",
      title2: "Dedícate a vender.",
      subtitle: "Sin formación. Sin cambiar de CRM. Sin implantación larga.",
      onboarding: "Cómo empezar",
      trial: "Demo de 15 minutos",
      noCredit: "Con el fundador. Sin compromiso.",
      claim: "Reservar llamada",
      watch: "Ver cómo funciona",
      questions: "¿Preguntas? Escríbenos a",
      responseTime: "Respuesta: Menos de 2 horas (L-V)",
      steps: [
        "Reservas 15 minutos",
        "Conectamos tu CRM",
        "Tus comerciales lo prueban en el día a día",
        "El copiloto se encarga del resto",
        "Tu equipo solo vende"
      ]
    }
  }
};

const LanguageContext = createContext<LanguageContextType | undefined>(undefined);

export const LanguageProvider: React.FC<{ children: ReactNode }> = ({ children }) => {
  const [language, setLanguage] = useState<Language>('ES');

  // Detect language from URL on mount
  useEffect(() => {
    const path = window.location.pathname;
    if (path.startsWith('/en')) {
      setLanguage('EN');
    } else {
      setLanguage('ES');
    }
  }, []);

  const t = translations[language];

  const handleSetLanguage = (lang: Language) => {
    setLanguage(lang);
    // Update URL without full refresh
    const newPath = lang === 'EN' ? '/en' : '/';
    window.history.pushState({}, '', newPath);
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
