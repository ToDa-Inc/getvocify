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
      pricing: "Pricing",
      about: "About",
      login: "Login",
      getStarted: "Get Started",
    },
    hero: {
      title1: "Stop Typing CRM Notes.",
      title2: "Start Talking.",
      subtitle1: "Voice memos that automatically update your CRM in 60 seconds.",
      subtitle2: "Save 5+ hours per week.",
      subtitle3: "Get back to selling.",
      cta1: "Start Free Trial",
      cta2: "Watch 60-Second Demo",
      scroll: "Scroll to explore",
      trust1: "Multi-CRM Sync",
      trust2: "GDPR Compliant",
      trust3: "No Credit Card",
    },
    integrations: {
      text1: "Seamlessly",
      text2: "integrates",
      text3: "with your stack",
    },
    problem: {
      title1: "You're Wasting",
      title2: "5+ Hours Every Week",
      title3: "on This:",
      p1: "Sitting in your car after meetings, frantically typing notes before you forget",
      p2: "End-of-day CRM catch-up when you just want to go home",
      p3: 'Incomplete records because you "forgot to log it"',
      p4: '"Why isn\'t your CRM updated?" — Manager',
      p5: "Lost deals because you missed a follow-up you never wrote down",
      bottomLine: "The bottom line:",
      result1: "Your manager thinks you're not working. Your pipeline is a mess. And you're spending",
      result2: "selling time",
      result3: "doing admin work.",
      revenueLoss: "Average revenue loss: €12,400 / year / rep",
      drainLabel: "Estimated Financial Drain",
      perYearRep: "/ year / rep",
      drainNote: "Based on current average sales performance loss.",
    },
    features: {
      title1: "Everything You Need.",
      title2: "Nothing You Don't.",
      subtitle: "We've stripped away the noise to build the ultimate productivity engine for sales teams who move fast.",
      f1: { title: "Instant Processing", desc: "60-second updates. Not 10 minutes of manual typing between meetings." },
      f2: { title: "AI Precision", desc: "Our proprietary AI extracts deals, contacts, and next steps with 98% accuracy." },
      f3: { title: "Native Mobile", desc: "A seamless mobile experience designed for the road. Record, sync, and get back to selling." },
      f4: { title: "CRM Sync", desc: "Real-time synchronization with Salesforce, HubSpot, and Pipedrive." },
      f5: { title: "Global Reach", desc: "Full support for English, Spanish, French, German, Italian, and Portuguese." },
      f6: { title: "Bank-Grade Security", desc: "GDPR compliant and end-to-end encrypted. Your data is safe and sovereign." },
    },
    solution: {
      title1: "From Voice to",
      title2: "CRM Data",
      title3: "in 60 Seconds.",
      subtitle: "A frictionless workflow that keeps your pipeline updated without opening your laptop.",
      s1: { title: "RECORD", time: "30s", desc: "Walk to your car. Tap record. Talk naturally:" },
      s2: { title: "EXTRACT", time: "20s", desc: "AI extracts structured data instantly:" },
      s3: { title: "SYNC", time: "10s", desc: "CRM updated automatically. Drive to your next meeting." },
      badge: "Zero manual entry required.",
      example1: "Just met Sarah at Acme Corp. She's interested in Enterprise. Budget is €50K. Decision by Q1. She wants demo next Tuesday. Also mentioned competitor DataCo.",
      label1: "Contact",
      label2: "Company",
      label3: "Deal Value",
      label4: "Next Step",
    },
    comparison: {
      title1: "Why Vocify vs.",
      title2: "Everything Else.",
      method: "Method",
      vocify: "Vocify",
      traditional: "Traditional CRM",
      voiceMemos: "Voice Memos",
      f1: "Speed",
      v1: "60 seconds",
      t1: "10+ minutes",
      m1: "5 min (typing required)",
      f2: "Data Accuracy",
      v2: "AI-extracted (90%)",
      t2: "Manual entry (High errors)",
      m2: "Human transcription",
      f3: "Opportunity Cost",
      v3: "€25/month",
      t3: "€1,200/year (Time lost)",
      m3: "€1,200/year (Time lost)",
      f4: "Native CRM Integration",
      f5: "Mobile App Access",
      f6: "Multi-Language (6+)",
    },
    useCases: {
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
    pricing: {
      title1: "Simple Pricing.",
      title2: "Massive Time Savings.",
      subtitle: "Choose the plan that fits your sales team's speed and scale.",
      popular: "Most Popular",
      badge1: "All plans include 14-day free trial.",
      badge2: "No credit card required.",
      p1: { 
        name: "SOLO", 
        price: "€25", 
        desc: "Perfect for individual reps",
        period: "/month",
        features: ["200 voice memos/month", "HubSpot + Pipedrive", "Mobile app", "Email support", "GDPR compliant"],
        cta: "Start Free Trial"
      },
      p2: { 
        name: "TEAM", 
        price: "€20", 
        desc: "For sales teams (3 users min)",
        period: "/month per user",
        features: ["Unlimited voice memos", "All CRM integrations", "Team analytics", "Shared terminology", "Priority support", "Manager dashboard"],
        cta: "Start Free Trial"
      },
      p3: { 
        name: "ENTERPRISE", 
        price: "Custom", 
        desc: "For larger organizations",
        period: " pricing",
        features: ["Everything in Team", "SSO & SAML", "Dedicated manager", "Custom integrations", "SLA guarantee", "Onboarding & training"],
        cta: "Book a Demo"
      },
    },
    socialProof: {
      title1: "Elite Sales Teams",
      title2: "Trust Vocify.",
      q1: "I used to spend 45 minutes at end of day doing CRM. Now it takes 5 minutes.",
      q2: "My team's CRM compliance went from 60% to 95% in two weeks. It's a game changer.",
      q3: "I log deals while walking between meetings. My manager thinks I'm a CRM machine.",
      q4: "Finally, a tool that actually saves time instead of creating more work.",
    },
    roi: {
      title1: "Stop Burning Time.",
      title2: "Calculate Your ROI.",
      subtitle: "See exactly how much your sales team could save by switching to voice-first CRM updates.",
      label1: "Sales Reps",
      label2: "Avg. Salary (€)",
      note1: "Est. 5 hours wasted / rep / week",
      note2: "Vocify costs just €25 / rep / month",
      saved: "Total Hours Saved",
      perYear: "/ year",
      potential: "Potential ROI",
      yearly: "Total Yearly Savings",
      equivalent: "That's equivalent to hiring",
      additional: "additional full-time reps",
      byEliminating: "just by eliminating data entry.",
      cta: "Reclaim Your Time Now",
    },
    faq: {
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
      title1: "Stop Wasting Time on CRM.",
      title2: "Start Selling More.",
      subtitle: "Join 500+ elite sales professionals who have reclaimed their time and focus.",
      onboarding: "The Onboarding Path",
      trial: "14-Day Free Trial",
      noCredit: "No credit card required. Cancel anytime.",
      claim: "Claim Your 14-Day Trial",
      watch: "Watch Demo",
      questions: "Questions? Reach out to our founders at",
      responseTime: "Response time: Under 2 hours (M-F)",
      steps: [
        "Start your 14-day free trial (no credit card)",
        "Connect your CRM in 2 minutes",
        "Record your first voice memo",
        "Watch it update automatically",
        "Save 5+ hours this week"
      ]
    }
  },
  ES: {
    nav: {
      features: "Funciones",
      pricing: "Precios",
      about: "Nosotros",
      login: "Acceder",
      getStarted: "Empezar",
    },
    hero: {
      title1: "Deja de escribir notas en el CRM.",
      title2: "Empieza a hablar.",
      subtitle1: "Notas de voz que actualizan automáticamente tu CRM en 60 segundos.",
      subtitle2: "Ahorra más de 5 horas a la semana.",
      subtitle3: "Vuelve a vender.",
      cta1: "Prueba gratuita",
      cta2: "Ver demo de 60s",
      scroll: "Desliza para explorar",
      trust1: "Sincronización multi-CRM",
      trust2: "Cumple con GDPR",
      trust3: "Sin tarjeta de crédito",
    },
    integrations: {
      text1: "Se integra",
      text2: "perfectamente",
      text3: "con tus herramientas",
    },
    problem: {
      title1: "Estás perdiendo",
      title2: "más de 5 horas semanales",
      title3: "en esto:",
      p1: "Sentado en el coche tras las reuniones, escribiendo notas antes de que se te olviden",
      p2: "Poniéndote al día con el CRM al final del día cuando solo quieres irte a casa",
      p3: 'Registros incompletos porque "se te olvidó anotarlo"',
      p4: '"¿Por qué no está actualizado tu CRM?" — Tu jefe',
      p5: "Tratos perdidos por olvidar un seguimiento que nunca anotaste",
      bottomLine: "Conclusión:",
      result1: "Tu jefe piensa que no estás trabajando. Tu pipeline es un desastre. Y estás perdiendo",
      result2: "tiempo de venta",
      result3: "haciendo trabajo administrativo.",
      revenueLoss: "Pérdida media de ingresos: 12.400€ / año / comercial",
      drainLabel: "Drenaje Financiero Estimado",
      perYearRep: "/ año / rep",
      drainNote: "Basado en la pérdida media actual de rendimiento.",
    },
    features: {
      title1: "Todo lo que necesitas.",
      title2: "Nada de lo que no.",
      subtitle: "Hemos eliminado el ruido para crear el motor de productividad definitivo para equipos de ventas que se mueven rápido.",
      f1: { title: "Procesamiento Instantáneo", desc: "Actualizaciones en 60 segundos. No 10 minutos de escritura manual entre reuniones." },
      f2: { title: "Precisión de IA", desc: "Nuestra IA propietaria extrae tratos, contactos y próximos pasos con un 98% de precisión." },
      f3: { title: "Móvil Nativo", desc: "Una experiencia móvil fluida diseñada para la calle. Graba, sincroniza y vuelve a vender." },
      f4: { title: "Sincronización CRM", desc: "Sincronización en tiempo real con Salesforce, HubSpot y Pipedrive." },
      f5: { title: "Alcance Global", desc: "Soporte completo para inglés, español, francés, alemán, italiano y portugués." },
      f6: { title: "Seguridad Bancaria", desc: "Cumple con GDPR y cifrado de extremo a extremo. Tus datos están seguros y son tuyos." },
    },
    solution: {
      title1: "De voz a",
      title2: "datos CRM",
      title3: "en 60 segundos.",
      subtitle: "Un flujo de trabajo sin fricciones que mantiene tu pipeline actualizado sin abrir el portátil.",
      s1: { title: "GRABAR", time: "30s", desc: "Ve al coche. Pulsa grabar. Habla con naturalidad:" },
      s2: { title: "EXTRAER", time: "20s", desc: "La IA extrae datos estructurados al instante:" },
      s3: { title: "SINCRONIZAR", time: "10s", desc: "CRM actualizado automáticamente. Ve a tu próxima reunión." },
      badge: "Cero entrada manual requerida.",
      example1: "Acabo de ver a Sarah en Acme Corp. Le interesa Enterprise. Presupuesto 50k€. Decisión en Q1. Quiere demo el próximo martes. También mencionó a DataCo.",
      label1: "Contacto",
      label2: "Empresa",
      label3: "Valor del Trato",
      label4: "Siguiente Paso",
    },
    comparison: {
      title1: "¿Por qué Vocify vs.",
      title2: "el resto?",
      method: "Método",
      vocify: "Vocify",
      traditional: "CRM Tradicional",
      voiceMemos: "Notas de Voz",
      f1: "Velocidad",
      v1: "60 segundos",
      t1: "10+ minutos",
      m1: "5 min (requiere escribir)",
      f2: "Precisión de Datos",
      v2: "Extraído por IA (90%)",
      t2: "Entrada manual (Muchos errores)",
      m2: "Transcripción humana",
      f3: "Coste de Oportunidad",
      v3: "25€/mes",
      t3: "1.200€/año (Tiempo perdido)",
      m3: "1.200€/año (Tiempo perdido)",
      f4: "Integración CRM Nativa",
      f5: "Acceso App Móvil",
      f6: "Multi-idioma (6+)",
    },
    useCases: {
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
    pricing: {
      title1: "Precios simples.",
      title2: "Ahorro masivo de tiempo.",
      subtitle: "Elige el plan que mejor se adapte a la velocidad y escala de tu equipo de ventas.",
      popular: "Más Popular",
      badge1: "Todos los planes incluyen 14 días de prueba.",
      badge2: "Sin tarjeta de crédito.",
      p1: { 
        name: "SOLO", 
        price: "25€", 
        desc: "Perfecto para comerciales individuales",
        period: "/mes",
        features: ["200 notas de voz/mes", "HubSpot + Pipedrive", "App móvil", "Soporte por email", "Cumple con GDPR"],
        cta: "Prueba Gratis"
      },
      p2: { 
        name: "TEAM", 
        price: "20€", 
        desc: "Para equipos de ventas (mín. 3 usuarios)",
        period: "/mes por usuario",
        features: ["Notas de voz ilimitadas", "Todas las integraciones CRM", "Analítica de equipo", "Terminología compartida", "Soporte prioritario", "Panel de director"],
        cta: "Prueba Gratis"
      },
      p3: { 
        name: "ENTERPRISE", 
        price: "Personalizado", 
        desc: "Para grandes organizaciones",
        period: " precio",
        features: ["Todo en Team", "SSO y SAML", "Gestor dedicado", "Integraciones a medida", "Garantía SLA", "Onboarding y formación"],
        cta: "Reservar Demo"
      },
    },
    socialProof: {
      title1: "Equipos de Elite",
      title2: "Confían en Vocify.",
      q1: "Solía pasar 45 minutos al final del día con el CRM. Ahora me lleva 5 minutos.",
      q2: "El cumplimiento del CRM de mi equipo pasó del 60% al 95% en dos semanas.",
      q3: "Registro tratos mientras camino entre reuniones. Mi jefe cree que soy una máquina.",
      q4: "Finalmente, una herramienta que ahorra tiempo en lugar de crear más trabajo.",
    },
    roi: {
      title1: "Deja de quemar tiempo.",
      title2: "Calcula tu ROI.",
      subtitle: "Mira cuánto podría ahorrar tu equipo de ventas al pasar a actualizaciones de CRM por voz.",
      label1: "Comerciales",
      label2: "Salario Medio (€)",
      note1: "Est. 5 horas perdidas / rep / semana",
      note2: "Vocify cuesta solo 25€ / rep / mes",
      saved: "Horas Totales Ahorradas",
      perYear: "/ año",
      potential: "ROI Potencial",
      yearly: "Ahorro Total Anual",
      equivalent: "Eso equivale a contratar",
      additional: "comerciales adicionales",
      byEliminating: "solo eliminando la entrada de datos.",
      cta: "Recupera tu tiempo ahora",
    },
    faq: {
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
      title1: "Deja de perder tiempo en el CRM.",
      title2: "Empieza a vender más.",
      subtitle: "Únete a más de 500 profesionales de ventas que han recuperado su tiempo y enfoque.",
      onboarding: "El camino de inicio",
      trial: "14 días de prueba gratis",
      noCredit: "Sin tarjeta de crédito. Cancela cuando quieras.",
      claim: "Reclama tus 14 días gratis",
      watch: "Ver Demo",
      questions: "¿Preguntas? Escribe a nuestros fundadores en",
      responseTime: "Respuesta: Menos de 2 horas (L-V)",
      steps: [
        "Inicia tu prueba gratis de 14 días (sin tarjeta)",
        "Conecta tu CRM en 2 minutos",
        "Graba tu primera nota de voz",
        "Mira cómo se actualiza solo",
        "Ahorra más de 5 horas esta semana"
      ]
    }
  }
};

const LanguageContext = createContext<LanguageContextType | undefined>(undefined);

export const LanguageProvider: React.FC<{ children: ReactNode }> = ({ children }) => {
  const [language, setLanguage] = useState<Language>('EN');

  // Detect language from URL on mount
  useEffect(() => {
    const path = window.location.pathname;
    if (path.startsWith('/es')) {
      setLanguage('ES');
    } else {
      setLanguage('EN');
    }
  }, []);

  const t = translations[language];

  const handleSetLanguage = (lang: Language) => {
    setLanguage(lang);
    // Update URL without full refresh
    const newPath = lang === 'ES' ? '/es' : '/';
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
