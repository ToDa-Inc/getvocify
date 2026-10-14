import type { Language } from './i18n';

export interface IslandStep {
  label: string;
  title: string;
  desc: string;
}

export interface IslandCopy {
  stage: { before: string; join: string; after: string; afterMeta: string };
  chips: { during: string; after: string };
  steps: [IslandStep, IslandStep, IslandStep];
  before: { contact: string; record: string; brief: { kind: 'task' | 'meeting' | 'chat'; text: string; when: string }[] };
  during: {
    callType: string;
    stop: string;
    liveHelp: string;
    helpEmpty: string;
    turns: { you: boolean; label: string | null; text: string }[];
    helpHeading: string;
    helpBridge: string;
    helpSay: string;
  };
  after: {
    title: string;
    tabCrm: string;
    tabNotes: string;
    tabEmail: string;
    email: { to: string; subject: string; preview: string; send: string; sent: string };
    groups: { label: string; rows: { label: string; value: string; was?: string }[] }[];
    apply: string;
    applied: string;
  };
}

export const islandCopy: Record<Language, IslandCopy> = {
  ES: {
    stage: { before: 'La llamada empieza en 2 min', join: 'Unirse', after: 'Llamada finalizada', afterMeta: 'Duración' },
    chips: { during: 'Playbook 3/5', after: '4 cambios en el CRM' },
    steps: [
      { label: 'Antes', title: 'Llegas con la historia completa', desc: 'Faltan 2 minutos. Vocify te muestra quién es, qué pasó la última vez y qué falta por hacer.' },
      { label: 'Durante', title: 'Te ayuda mientras hablas', desc: 'Escucha la conversación, la transcribe y te sugiere qué responder cuando surge una objeción.' },
      { label: 'Después', title: 'Cuelgas y está hecho', desc: 'La llamada ha terminado. Vocify prepara los cambios del CRM y el email para que los revises.' },
    ],
    before: {
      contact: 'Marta Ruiz · Acme Logistics',
      record: 'Grabar',
      brief: [
        { kind: 'task', text: 'Propuesta pendiente de enviar', when: 'en 2 d' },
        { kind: 'meeting', text: 'Demo con operaciones; pidió precio para 12 puestos', when: 'hace 1 d' },
        { kind: 'chat', text: 'Presupuesto del Q4 confirmado', when: 'hace 9 d' },
      ],
    },
    during: {
      callType: 'Descubrimiento',
      stop: 'Parar',
      liveHelp: 'Ayuda en vivo',
      helpEmpty: 'Las respuestas aparecen aquí cuando preguntan o ponen una objeción.',
      turns: [
        { you: false, label: 'Marta Ruiz', text: 'Ocupada, la verdad. Aún decidimos si movemos a todo el equipo del CRM actual antes del verano.' },
        { you: true, label: null, text: 'Justo de eso quería hablar. ¿Cuál es el principal bloqueo hoy?' },
        { you: false, label: 'Marta Ruiz', text: 'Sobre todo el precio. Y nos preocupa la migración de los datos.' },
        { you: true, label: null, text: 'Entendido. Podemos encargarnos de la migración.' },
        { you: false, label: 'Marta Ruiz', text: '¿Y cuánto tardaría?' },
      ],
      helpHeading: 'Objeción de precio',
      helpBridge: '«Es una preocupación justa, déjame ponerla en contexto.»',
      helpSay: 'La mayoría de equipos recuperan el coste en el primer trimestre porque dejan de actualizar el CRM a mano. ¿Te enseño los números para un equipo de tu tamaño?',
    },
    after: {
      title: 'Marta Ruiz',
      tabCrm: 'CRM',
      tabNotes: 'Notas',
      tabEmail: 'Email',
      email: { to: 'Para: marta@acmelogistics.com', subject: 'Siguiente paso: migración y propuesta', preview: 'Hola Marta, gracias por tu tiempo hoy. Como hablamos, nos encargamos de la migración de datos y te envío la propuesta para 12 puestos el jueves.', send: 'Enviar', sent: 'Enviado' },
      groups: [
        {
          label: 'Contacto',
          rows: [
            { label: 'Cargo', value: 'Director comercial', was: 'era Responsable' },
            { label: 'Intereses', value: 'CRM; Automatización de ventas' },
            { label: 'Poco claro', value: 'Aprobación de presupuesto pendiente' },
          ],
        },
        { label: 'Empresa', rows: [{ label: 'Sector', value: 'Software', was: 'era Industria' }] },
      ],
      apply: 'Aplicar 4 cambios',
      applied: 'CRM actualizado',
    },
  },
  EN: {
    stage: { before: 'The call starts in 2 min', join: 'Join', after: 'Call ended', afterMeta: 'Duration' },
    chips: { during: 'Playbook 3/5', after: '4 CRM changes' },
    steps: [
      { label: 'Before', title: 'Walk in with the full story', desc: 'Two minutes to go. Vocify shows who it is, what happened last time and what is still open.' },
      { label: 'During', title: 'Helps you while you talk', desc: 'It listens, transcribes and suggests what to say when an objection comes up.' },
      { label: 'After', title: 'You hang up, it is done', desc: 'The call is over. Vocify prepares the CRM changes and the email for you to review.' },
    ],
    before: {
      contact: 'Marta Ruiz · Acme Logistics',
      record: 'Record',
      brief: [
        { kind: 'task', text: 'Proposal still to send', when: 'in 2 d' },
        { kind: 'meeting', text: 'Demo with the ops team; asked for pricing for 12 seats', when: '1 d ago' },
        { kind: 'chat', text: 'Budget for Q4 confirmed', when: '9 d ago' },
      ],
    },
    during: {
      callType: 'Discovery call',
      stop: 'Stop',
      liveHelp: 'Live help',
      helpEmpty: 'Answers show up here when they ask or push back.',
      turns: [
        { you: false, label: 'Marta Ruiz', text: 'Busy, honestly. We are still deciding whether to move the whole team off the old CRM before the summer.' },
        { you: true, label: null, text: 'That is exactly what I wanted to dig into. What is the main blocker today?' },
        { you: false, label: 'Marta Ruiz', text: 'Mainly price. We also worry about the data migration.' },
        { you: true, label: null, text: 'Understood. We can cover the migration.' },
        { you: false, label: 'Marta Ruiz', text: 'And how long would that take?' },
      ],
      helpHeading: 'Price objection',
      helpBridge: '“That is a fair concern, let me put it in context.”',
      helpSay: 'Most teams recover the cost in the first quarter because reps stop doing manual CRM updates. Want me to show the numbers for a team your size?',
    },
    after: {
      title: 'Marta Ruiz',
      tabCrm: 'CRM',
      tabNotes: 'Notes',
      tabEmail: 'Email',
      email: { to: 'To: marta@acmelogistics.com', subject: 'Next step: migration and proposal', preview: 'Hi Marta, thanks for your time today. As we discussed, we will handle the data migration and I will send the proposal for 12 seats on Thursday.', send: 'Send', sent: 'Sent' },
      groups: [
        {
          label: 'Contact',
          rows: [
            { label: 'Title', value: 'Director of Sales', was: 'was Manager' },
            { label: 'Interests', value: 'CRM; Sales automation' },
            { label: 'Unclear', value: 'Budget approval pending' },
          ],
        },
        { label: 'Company', rows: [{ label: 'Industry', value: 'Software', was: 'was Manufacturing' }] },
      ],
      apply: 'Apply 4 changes',
      applied: 'CRM updated',
    },
  },
};
