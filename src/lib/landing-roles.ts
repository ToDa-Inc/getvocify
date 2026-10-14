import type { Object3DVariant } from '@/components/landing/Object3D';
import type { Language } from './i18n';

export type RoleKey = 'sdr' | 'ae' | 'manager' | 'field' | 'revops';

export const ROLE_PATHS: Record<RoleKey, string> = {
  sdr: '/teams/sdrs',
  ae: '/teams/account-executives',
  manager: '/teams/sales-managers',
  field: '/teams/field-reps',
  revops: '/teams/revops',
};

/** The 3D object that introduces each role. */
export const ROLE_OBJECT: Record<RoleKey, Object3DVariant> = {
  sdr: 'handset',
  ae: 'briefcase',
  manager: 'clipboard',
  field: 'whatsapp',
  revops: 'database',
};

export type RoleMock =
  | { kind: 'prep'; title: string; meta: string; blocks: { label: string; text?: string; items?: string[] }[] }
  | { kind: 'live'; said: string; tag: string; answerTitle: string; answer: string }
  | { kind: 'playbook'; title: string; items: { label: string; done: boolean }[]; note: string }
  | { kind: 'done'; title: string; items: string[] }
  | { kind: 'metrics'; title: string; rows: { label: string; value: number }[] }
  | { kind: 'whatsapp'; title: string; sent: string; reply: string }
  | { kind: 'stack'; title: string; names: string[]; more: string }
  | { kind: 'fields'; title: string; rows: { label: string; from?: string; to: string }[] }
  | { kind: 'timeline'; title: string; phases: string[]; marked: number; moment: string; fix: string }
  | { kind: 'feedback'; title: string; score: number; goodTitle: string; good: string; nextTitle: string; next: string; tryIt: string };

export interface RoleSection {
  step: string;
  title: string;
  desc: string;
  mock: RoleMock;
}

export interface RoleCopy {
  eyebrow: string;
  title: string;
  accent: string;
  subtitle: string;
  sections: RoleSection[];
  closingTitle: string;
  closingAccent: string;
}

export interface RolesUiCopy {
  sample: string;
  demo: string;
  seeHow: string;
  closingCta: string;
}

export const rolesUi: Record<Language, RolesUiCopy> = {
  EN: { sample: 'Illustrative example', demo: 'Book a demo', seeHow: 'See how it works', closingCta: 'Book a demo' },
  ES: { sample: 'Ejemplo ilustrativo', demo: 'Reservar demo', seeHow: 'Ver cómo funciona', closingCta: 'Reservar demo' },
};

const crmFieldsEs: RoleMock = {
  kind: 'fields',
  title: 'Grupo Ibérica · Laura Méndez',
  rows: [
    { label: 'Etapa', from: 'Descubrimiento', to: 'Propuesta' },
    { label: 'Importe', to: '48.000 €' },
    { label: 'Próximo paso', to: 'Demo técnica · jueves' },
    { label: 'Dolor', to: '6 h/semana en Excel' },
  ],
};
const crmFieldsEn: RoleMock = {
  kind: 'fields',
  title: 'Grupo Ibérica · Laura Méndez',
  rows: [
    { label: 'Stage', from: 'Discovery', to: 'Proposal' },
    { label: 'Amount', to: '€48,000' },
    { label: 'Next step', to: 'Technical demo · Thursday' },
    { label: 'Pain', to: '6 h/week in Excel' },
  ],
};

export const rolesCopy: Record<Language, Record<RoleKey, RoleCopy>> = {
  ES: {
    sdr: {
      eyebrow: 'Para SDRs',
      title: 'Dedica más tiempo a vender,',
      accent: 'y a vender bien.',
      subtitle:
        'Vocify te da el contexto antes de cada contacto, te ayuda cuando surge una objeción y deja el CRM al día al terminar, para que tu tiempo se vaya en vender.',
      sections: [
        {
          step: '01 · Prepara',
          title: 'Contexto antes del primer «hola»',
          desc: 'Quién es, qué hace su empresa y por qué merece la pena hablar con ellos hoy. Sin pestañas abiertas ni investigación a mano.',
          mock: {
            kind: 'prep',
            title: 'Jordan Pérez · Head of IT',
            meta: 'Agencia de marketing · 50 personas',
            blocks: [
              { label: 'Con quién hablas', text: 'Responsable de tecnología de una agencia que presta servicios digitales a sus clientes.' },
              { label: 'Empieza por', text: 'El motivo más relevante para su rol, no un pitch genérico.' },
              { label: 'Pregunta', items: ['¿Cómo gestionáis hoy este proceso?', '¿Qué proyectos lo necesitan más?'] },
            ],
          },
        },
        {
          step: '02 · Resuelve',
          title: 'Objeciones resueltas sin perder el ritmo',
          desc: 'Cuando llega un «ahora no es prioridad» o un «ya tenemos proveedor», Vocify te sugiere cómo responder y qué paso del playbook toca.',
          mock: {
            kind: 'live',
            said: 'Ahora mismo no es una prioridad para nosotros.',
            tag: 'Objeción · prioridad',
            answerTitle: 'Respuesta sugerida',
            answer: 'Reconoce el momento, conecta con el coste de esperar y propón quince minutos para ver un caso concreto.',
          },
        },
        {
          step: '03 · Automatiza',
          title: 'Termina y marca el siguiente',
          desc: 'Campos del CRM, notas, emails de seguimiento y tareas se hacen solos. Tu tiempo se queda para el siguiente contacto.',
          mock: {
            kind: 'done',
            title: 'Hecho al terminar',
            items: ['Resultado registrado', 'Campos del CRM actualizados', 'Email de seguimiento', 'Tarea para el siguiente intento'],
          },
        },
        {
          step: '04 · Mejora',
          title: 'Aprende de cada conversación',
          desc: 'Vocify mide la adherencia al playbook en cada conversación. Revisa qué podrías hacer mejor en vez de rellenar campos.',
          mock: {
            kind: 'metrics',
            title: 'Adherencia al playbook · esta semana',
            rows: [
              { label: 'Presentación', value: 95 },
              { label: 'Descubrimiento', value: 70 },
              { label: 'Objeciones', value: 55 },
              { label: 'Siguiente paso', value: 80 },
            ],
          },
        },
      ],
      closingTitle: 'Que cada SDR dedique su tiempo',
      closingAccent: 'a vender, y a vender bien.',
    },
    ae: {
      eyebrow: 'Para Account Executives',
      title: 'Reuniones complejas,',
      accent: 'respuestas precisas.',
      subtitle:
        'Da una respuesta precisa cuando la conversación se vuelve técnica, resuelve la objeción mientras sigue viva y deja todo el admin hecho al terminar.',
      sections: [
        {
          step: '01 · Prepara',
          title: 'Llega con la historia completa de la cuenta',
          desc: 'Historial, decisores, puntos pendientes y las preguntas que aún no has hecho, para esta reunión concreta.',
          mock: {
            kind: 'prep',
            title: 'Acme Corp · Sarah Chen',
            meta: 'Segunda reunión · Propuesta enviada',
            blocks: [
              { label: 'Contexto', text: 'Interesada en Enterprise. Presupuesto y fecha de decisión aún abiertos.' },
              { label: 'Abre con', text: 'El punto pendiente de la última reunión, antes de hablar de precio.' },
              { label: 'Pregunta', items: ['¿Quién más participa en la decisión?', '¿Qué presupuesto hay reservado para el Q1?'] },
            ],
          },
        },
        {
          step: '02 · Responde',
          title: 'Profundidad de producto, justo cuando el cliente pregunta',
          desc: 'Vocify conoce tu producto y tu contexto, así que las respuestas técnicas salen de tu material, no de consejos genéricos.',
          mock: {
            kind: 'live',
            said: '¿Dónde se almacenan los datos de nuestros equipos europeos?',
            tag: 'Pregunta técnica',
            answerTitle: 'Respuesta lista',
            answer: 'Los datos se almacenan en la UE y se cifran en tránsito y en reposo.',
          },
        },
        {
          step: '03 · Descubre',
          title: 'Un descubrimiento sin huecos',
          desc: 'Agenda, dolor, presupuesto, decisor y siguiente paso, a la vista mientras hablas, para no salir de la reunión con preguntas sin hacer.',
          mock: {
            kind: 'playbook',
            title: 'Playbook de descubrimiento',
            items: [
              { label: 'Agenda acordada', done: true },
              { label: 'Dolor identificado', done: true },
              { label: 'Presupuesto confirmado', done: false },
              { label: 'Decisor identificado', done: false },
              { label: 'Siguiente paso', done: false },
            ],
            note: 'Faltan tres pasos del playbook antes de cerrar la reunión.',
          },
        },
        {
          step: '04 · Cierra el ciclo',
          title: 'Todo el admin, hecho al terminar',
          desc: 'Campos del CRM, notas, el email de seguimiento con los próximos pasos y las tareas con fecha, sin tocar nada.',
          mock: {
            kind: 'done',
            title: 'Hecho al terminar',
            items: ['Campos del CRM actualizados', 'Notas de la reunión', 'Email de seguimiento', 'Tareas con fecha', 'Siguiente reunión agendada'],
          },
        },
        {
          step: '05 · Mejora',
          title: 'Entiende dónde se enfría cada trato',
          desc: 'La adherencia al playbook es la métrica que impacta directamente en tu tasa de cierre. Revisa qué paso te saltas y cómo lo resuelven tus mejores comerciales.',
          mock: {
            kind: 'metrics',
            title: 'Adherencia al playbook · esta semana',
            rows: [
              { label: 'Agenda', value: 90 },
              { label: 'Descubrimiento', value: 72 },
              { label: 'Objeciones', value: 58 },
              { label: 'Siguiente paso', value: 85 },
            ],
          },
        },
      ],
      closingTitle: 'Da a cada AE la ventaja',
      closingAccent: 'de tu mejor comercial.',
    },
    manager: {
      eyebrow: 'Para directores comerciales',
      title: 'Entrena con datos,',
      accent: 'no con intuiciones.',
      subtitle:
        'Vocify mide la adherencia al playbook en cada conversación y te muestra en qué momento se enfría un trato y cómo lo resuelven tus mejores comerciales.',
      sections: [
        {
          step: '01 · Mide',
          title: 'La adherencia al playbook de cada comercial',
          desc: 'La métrica que impacta directamente en la tasa de cierre, medida en cada conversación y no solo en las que alguien revisa.',
          mock: {
            kind: 'metrics',
            title: 'Adherencia al playbook · por paso',
            rows: [
              { label: 'Agenda', value: 92 },
              { label: 'Descubrimiento', value: 74 },
              { label: 'Objeciones', value: 58 },
              { label: 'Siguiente paso', value: 81 },
            ],
          },
        },
        {
          step: '02 · Localiza',
          title: 'En qué momento se cae el trato',
          desc: 'Ve en qué punto de la conversación se pierde el hilo, por ejemplo una objeción de precio que nadie respondió.',
          mock: {
            kind: 'timeline',
            title: 'Línea de tiempo de la conversación',
            phases: ['Intro', 'Descubrimiento', 'Objeción', 'Cierre'],
            marked: 2,
            moment: 'Minuto 14 · Objeción de precio sin responder',
            fix: 'Tus mejores comerciales responden con valor antes que con precio.',
          },
        },
        {
          step: '03 · Entrena',
          title: 'Feedback de cada conversación, según tu playbook',
          desc: 'Qué hizo bien cada comercial y qué probar la próxima vez, sin que tengas que escuchar la llamada entera.',
          mock: {
            kind: 'feedback',
            title: 'Feedback · Llamada con Grupo Ibérica',
            score: 81,
            goodTitle: 'Bien hecho',
            good: 'Cuantificaste el dolor: 6 h por comercial.',
            nextTitle: 'La próxima vez',
            next: 'Aísla la objeción antes de responder.',
            tryIt: 'Prueba con: «Aparte del precio, ¿qué más os frena?»',
          },
        },
        {
          step: '04 · Visibilidad',
          title: 'Un pipeline al día, para todo el equipo',
          desc: 'Como cada conversación llega al CRM, el pipeline no depende de que cada comercial lo actualice.',
          mock: {
            kind: 'done',
            title: 'Cada conversación deja',
            items: ['Campos del CRM actualizados', 'Tareas con fecha', 'Seguimiento preparado', 'Feedback del playbook'],
          },
        },
      ],
      closingTitle: 'Convierte la forma de vender de tu mejor comercial',
      closingAccent: 'en la de todo el equipo.',
    },
    field: {
      eyebrow: 'Para comerciales de calle',
      title: 'Vende en la calle,',
      accent: 'actualiza por WhatsApp.',
      subtitle:
        'Al salir de la visita, mándale una actualización a Vocify por WhatsApp. Entiende lo que cuentas y deja el CRM al día, sin volver a la oficina.',
      sections: [
        {
          step: '01 · Envía',
          title: 'Una actualización por WhatsApp al salir de la visita',
          desc: 'Cuéntalo como se lo contarías a un compañero. Sin formularios y sin esperar a llegar al ordenador.',
          mock: {
            kind: 'whatsapp',
            title: 'Vocify · WhatsApp',
            sent: 'Laura quiere la demo técnica el jueves. Presupuesto de 48.000 €, decide ella.',
            reply: 'Entendido. Importe, próximo paso y tarea listos para que los revises.',
          },
        },
        {
          step: '02 · Entiende',
          title: 'Saca los datos de lo que cuentas',
          desc: 'Importe, próximo paso y quién decide salen de una charla normal, no de un formulario.',
          mock: crmFieldsEs,
        },
        {
          step: '03 · Automatiza',
          title: 'Tu CRM, sin salir de WhatsApp',
          desc: 'Tu equipo en ruta habla con su CRM por WhatsApp: manda actualizaciones y los datos se rellenan con un bot.',
          mock: {
            kind: 'done',
            title: 'Hecho al terminar',
            items: ['Campos del CRM actualizados', 'Tarea de seguimiento', 'Email de seguimiento', 'Notas de la visita'],
          },
        },
        {
          step: '04 · Revisa',
          title: 'Tú apruebas cada cambio',
          desc: 'Revisas y apruebas cada actualización antes de que llegue a tu CRM.',
          mock: {
            kind: 'done',
            title: 'Antes de entrar en el CRM',
            items: ['Revisas cada cambio', 'Editas lo que haga falta', 'Aplicas con un clic'],
          },
        },
      ],
      closingTitle: 'Menos tiempo en el ordenador,',
      closingAccent: 'más tiempo con clientes.',
    },
    revops: {
      eyebrow: 'Para RevOps',
      title: 'Datos de ventas',
      accent: 'en los que puedes confiar.',
      subtitle:
        'Vocify mantiene el CRM al día desde las conversaciones, con cada cambio revisado, para que tus informes se basen en lo que realmente se habló.',
      sections: [
        {
          step: '01 · Datos',
          title: 'Campos del CRM que se rellenan solos',
          desc: 'Etapa, importe, próximo paso y dolor salen de la conversación y llegan a tu CRM. Nadie persigue a nadie para que los rellene.',
          mock: crmFieldsEs,
        },
        {
          step: '02 · Control',
          title: 'Nada se escribe sin revisión',
          desc: 'Cada actualización se revisa y se aprueba antes de entrar en tu CRM, y puede editarse antes.',
          mock: {
            kind: 'done',
            title: 'Cómo entra un dato',
            items: ['Se extrae de la conversación', 'Lo revisa el comercial', 'Se edita si hace falta', 'Se aplica al CRM'],
          },
        },
        {
          step: '03 · Conexión',
          title: 'Funciona con tu CRM',
          desc: 'HubSpot, Salesforce, Pipedrive y más de 100 herramientas. Vocify no sustituye tu CRM: lo mantiene al día.',
          mock: { kind: 'stack', title: 'Compatible con', names: ['HubSpot', 'Salesforce', 'Pipedrive'], more: '+100 más' },
        },
        {
          step: '04 · Confianza',
          title: 'Datos en la UE, cifrados',
          desc: 'Cumple GDPR, con los datos alojados en la UE y cifrados en tránsito y en reposo.',
          mock: { kind: 'done', title: 'Seguridad y privacidad', items: ['Cumple GDPR', 'Datos alojados en la UE', 'Cifrado en tránsito y en reposo'] },
        },
        {
          step: '05 · Playbook',
          title: 'La metodología de tu equipo, medida',
          desc: 'Mide la adherencia al playbook en cada conversación para ver qué se cumple y qué no, en todo el equipo.',
          mock: {
            kind: 'metrics',
            title: 'Adherencia al playbook · equipo',
            rows: [
              { label: 'Agenda', value: 92 },
              { label: 'Descubrimiento', value: 74 },
              { label: 'Objeciones', value: 58 },
              { label: 'Siguiente paso', value: 81 },
            ],
          },
        },
      ],
      closingTitle: 'Deja de perseguir datos.',
      closingAccent: 'Empieza a confiar en ellos.',
    },
  },
  EN: {
    sdr: {
      eyebrow: 'For SDRs',
      title: 'Spend more time selling,',
      accent: 'and selling well.',
      subtitle:
        'Vocify gives you context before every contact, helps when an objection comes up and leaves the CRM up to date when you finish, so your time goes into selling.',
      sections: [
        {
          step: '01 · Prepare',
          title: 'Context before the first “hello”',
          desc: 'Who they are, what their company does and why it is worth talking to them today. No open tabs, no manual research.',
          mock: {
            kind: 'prep',
            title: 'Jordan Pérez · Head of IT',
            meta: 'Marketing agency · 50 people',
            blocks: [
              { label: 'Who you are talking to', text: 'Head of technology at an agency that delivers digital work for its clients.' },
              { label: 'Lead with', text: 'The reason most relevant to their role, not a generic pitch.' },
              { label: 'Ask', items: ['How do you handle this process today?', 'Which projects need it most?'] },
            ],
          },
        },
        {
          step: '02 · Respond',
          title: 'Objections handled without losing rhythm',
          desc: 'When “not a priority right now” or “we already have a vendor” comes up, Vocify suggests how to respond and which playbook step is next.',
          mock: {
            kind: 'live',
            said: 'This is not a priority for us right now.',
            tag: 'Objection · priority',
            answerTitle: 'Suggested answer',
            answer: 'Acknowledge the timing, connect with the cost of waiting and propose fifteen minutes to look at a concrete case.',
          },
        },
        {
          step: '03 · Automate',
          title: 'Finish and dial the next one',
          desc: 'CRM fields, notes, follow-up emails and tasks are done for you. Your time stays for the next contact.',
          mock: {
            kind: 'done',
            title: 'Done when you finish',
            items: ['Outcome logged', 'CRM fields updated', 'Follow-up email', 'Task for the next attempt'],
          },
        },
        {
          step: '04 · Improve',
          title: 'Learn from every conversation',
          desc: 'Vocify measures playbook adherence on every conversation. Review what you could do better instead of filling in fields.',
          mock: {
            kind: 'metrics',
            title: 'Playbook adherence · this week',
            rows: [
              { label: 'Opening', value: 95 },
              { label: 'Discovery', value: 70 },
              { label: 'Objections', value: 55 },
              { label: 'Next step', value: 80 },
            ],
          },
        },
      ],
      closingTitle: 'Let every SDR spend their time',
      closingAccent: 'selling, and selling well.',
    },
    ae: {
      eyebrow: 'For Account Executives',
      title: 'Complex meetings,',
      accent: 'precise answers.',
      subtitle:
        'Give a precise answer when the conversation turns technical, handle the objection while it is still live and leave all the admin done when you finish.',
      sections: [
        {
          step: '01 · Prepare',
          title: 'Walk in with the full account story',
          desc: 'History, decision makers, open items and the questions you have not asked yet, for this specific meeting.',
          mock: {
            kind: 'prep',
            title: 'Acme Corp · Sarah Chen',
            meta: 'Second meeting · Proposal sent',
            blocks: [
              { label: 'Context', text: 'Interested in Enterprise. Budget and decision date still open.' },
              { label: 'Open with', text: 'The open item from the last meeting, before talking price.' },
              { label: 'Ask', items: ['Who else is part of the decision?', 'What budget is set aside for Q1?'] },
            ],
          },
        },
        {
          step: '02 · Answer',
          title: 'Product depth, right when the buyer asks',
          desc: 'Vocify knows your product and your context, so technical answers come from your material, not generic advice.',
          mock: {
            kind: 'live',
            said: 'Where is the data for our European teams stored?',
            tag: 'Technical question',
            answerTitle: 'Answer ready',
            answer: 'Data is stored in the EU and encrypted in transit and at rest.',
          },
        },
        {
          step: '03 · Discover',
          title: 'Discovery without gaps',
          desc: 'Agenda, pain, budget, decision maker and next step in view while you talk, so you do not leave the meeting with unasked questions.',
          mock: {
            kind: 'playbook',
            title: 'Discovery playbook',
            items: [
              { label: 'Agenda agreed', done: true },
              { label: 'Pain identified', done: true },
              { label: 'Budget confirmed', done: false },
              { label: 'Decision maker identified', done: false },
              { label: 'Next step', done: false },
            ],
            note: 'Three playbook steps are still open before you close the meeting.',
          },
        },
        {
          step: '04 · Close the loop',
          title: 'All the admin, done when you finish',
          desc: 'CRM fields, notes, the follow-up email with next steps and tasks with dates, without touching a thing.',
          mock: {
            kind: 'done',
            title: 'Done when you finish',
            items: ['CRM fields updated', 'Meeting notes', 'Follow-up email', 'Tasks with dates', 'Next meeting scheduled'],
          },
        },
        {
          step: '05 · Improve',
          title: 'Understand where each deal cools',
          desc: 'Playbook adherence is the metric that moves your close rate directly. Review which step you skip and how your best reps handle it.',
          mock: {
            kind: 'metrics',
            title: 'Playbook adherence · this week',
            rows: [
              { label: 'Agenda', value: 90 },
              { label: 'Discovery', value: 72 },
              { label: 'Objections', value: 58 },
              { label: 'Next step', value: 85 },
            ],
          },
        },
      ],
      closingTitle: 'Give every AE the advantage',
      closingAccent: 'of your best rep.',
    },
    manager: {
      eyebrow: 'For sales managers',
      title: 'Coach with data,',
      accent: 'not hunches.',
      subtitle:
        'Vocify measures playbook adherence on every conversation and shows you where a deal cools and how your best reps handle it.',
      sections: [
        {
          step: '01 · Measure',
          title: 'Each rep’s playbook adherence',
          desc: 'The metric that moves your close rate directly, measured on every conversation, not only the ones someone reviews.',
          mock: {
            kind: 'metrics',
            title: 'Playbook adherence · by step',
            rows: [
              { label: 'Agenda', value: 92 },
              { label: 'Discovery', value: 74 },
              { label: 'Objections', value: 58 },
              { label: 'Next step', value: 81 },
            ],
          },
        },
        {
          step: '02 · Locate',
          title: 'Where the deal slips',
          desc: 'See at which point of the conversation the thread is lost, for example a price objection nobody answered.',
          mock: {
            kind: 'timeline',
            title: 'Conversation timeline',
            phases: ['Intro', 'Discovery', 'Objection', 'Close'],
            marked: 2,
            moment: 'Minute 14 · Price objection left unanswered',
            fix: 'Your best reps answer with value before price.',
          },
        },
        {
          step: '03 · Coach',
          title: 'Feedback on every conversation, against your playbook',
          desc: 'What each rep did well and what to try next time, without you listening to the whole call.',
          mock: {
            kind: 'feedback',
            title: 'Feedback · Call with Grupo Ibérica',
            score: 81,
            goodTitle: 'Well done',
            good: 'You quantified the pain: 6 h per rep.',
            nextTitle: 'Next time',
            next: 'Isolate the objection before answering.',
            tryIt: 'Try: “Apart from price, what else is holding you back?”',
          },
        },
        {
          step: '04 · Visibility',
          title: 'An up-to-date pipeline for the whole team',
          desc: 'Because every conversation reaches the CRM, the pipeline does not depend on each rep updating it.',
          mock: {
            kind: 'done',
            title: 'Every conversation leaves',
            items: ['CRM fields updated', 'Tasks with dates', 'Follow-up prepared', 'Playbook feedback'],
          },
        },
      ],
      closingTitle: 'Turn the way your best rep sells',
      closingAccent: 'into the way the whole team sells.',
    },
    field: {
      eyebrow: 'For field reps',
      title: 'Sell on the road,',
      accent: 'update over WhatsApp.',
      subtitle:
        'As you leave the visit, send Vocify an update over WhatsApp. It understands what you say and leaves the CRM up to date, without going back to the office.',
      sections: [
        {
          step: '01 · Send',
          title: 'An update over WhatsApp as you leave the visit',
          desc: 'Say it the way you would tell a colleague. No forms and no waiting to get to a computer.',
          mock: {
            kind: 'whatsapp',
            title: 'Vocify · WhatsApp',
            sent: 'Laura wants the technical demo on Thursday. Budget is €48,000, she decides.',
            reply: 'Got it. Amount, next step and task ready for you to review.',
          },
        },
        {
          step: '02 · Understand',
          title: 'Pull the data out of what you say',
          desc: 'Amount, next step and who decides come from a normal chat, not a form.',
          mock: crmFieldsEn,
        },
        {
          step: '03 · Automate',
          title: 'Your CRM, without leaving WhatsApp',
          desc: 'Your team on the road talks to its CRM over WhatsApp: it sends updates and a bot fills in the data.',
          mock: {
            kind: 'done',
            title: 'Done when you finish',
            items: ['CRM fields updated', 'Follow-up task', 'Follow-up email', 'Visit notes'],
          },
        },
        {
          step: '04 · Review',
          title: 'You approve every change',
          desc: 'You review and approve every update before it reaches your CRM.',
          mock: {
            kind: 'done',
            title: 'Before it enters the CRM',
            items: ['You review each change', 'You edit what you need', 'You apply with one click'],
          },
        },
      ],
      closingTitle: 'Less time at the computer,',
      closingAccent: 'more time with customers.',
    },
    revops: {
      eyebrow: 'For RevOps',
      title: 'Sales data',
      accent: 'you can trust.',
      subtitle:
        'Vocify keeps the CRM up to date from conversations, with every change reviewed, so your reports reflect what was actually said.',
      sections: [
        {
          step: '01 · Data',
          title: 'CRM fields that fill themselves',
          desc: 'Stage, amount, next step and pain come out of the conversation and reach your CRM. Nobody chases anyone to fill them in.',
          mock: crmFieldsEn,
        },
        {
          step: '02 · Control',
          title: 'Nothing is written without review',
          desc: 'Every update is reviewed and approved before it enters your CRM, and can be edited first.',
          mock: {
            kind: 'done',
            title: 'How a data point gets in',
            items: ['Extracted from the conversation', 'Reviewed by the rep', 'Edited if needed', 'Applied to the CRM'],
          },
        },
        {
          step: '03 · Connection',
          title: 'Works with your CRM',
          desc: 'HubSpot, Salesforce, Pipedrive and 100+ more tools. Vocify does not replace your CRM: it keeps it up to date.',
          mock: { kind: 'stack', title: 'Compatible with', names: ['HubSpot', 'Salesforce', 'Pipedrive'], more: '+100 more' },
        },
        {
          step: '04 · Trust',
          title: 'Data in the EU, encrypted',
          desc: 'GDPR compliant, with data hosted in the EU and encrypted in transit and at rest.',
          mock: { kind: 'done', title: 'Security and privacy', items: ['GDPR compliant', 'Data hosted in the EU', 'Encrypted in transit and at rest'] },
        },
        {
          step: '05 · Playbook',
          title: 'Your team’s methodology, measured',
          desc: 'Measure playbook adherence on every conversation to see what is followed and what is not, across the whole team.',
          mock: {
            kind: 'metrics',
            title: 'Playbook adherence · team',
            rows: [
              { label: 'Agenda', value: 92 },
              { label: 'Discovery', value: 74 },
              { label: 'Objections', value: 58 },
              { label: 'Next step', value: 81 },
            ],
          },
        },
      ],
      closingTitle: 'Stop chasing data.',
      closingAccent: 'Start trusting it.',
    },
  },
};
