import type { Language } from './i18n';

export interface McpCopy {
  eyebrow: string;
  badge: string;
  title: string;
  accent: string;
  subtitle: string;
  cta: string;
  tools: { name: string; desc: string }[];
  more: { name: string; desc: string };
  stepsTitle: string;
  steps: { title: string; desc: string }[];
  promptsTitle: string;
  promptsBadge: string;
  prompts: string[];
  closingTitle: string;
  closingAccent: string;
}

export const mcpCopy: Record<Language, McpCopy> = {
  ES: {
    eyebrow: 'MCP',
    badge: 'Acceso anticipado',
    title: 'Vocify, dentro de',
    accent: 'tu IA.',
    subtitle:
      'Conecta Vocify a Claude, Cursor y ChatGPT y pregunta por tus conversaciones, tus cuentas y tu CRM sin salir de la herramienta que ya usas.',
    cta: 'Pedir acceso',
    tools: [
      { name: 'Claude', desc: 'Pregunta a Claude por tus llamadas y cuentas.' },
      { name: 'Cursor', desc: 'Lleva el contexto de tus clientes a tu editor.' },
      { name: 'ChatGPT', desc: 'Consulta tu actividad comercial desde ChatGPT.' },
    ],
    more: { name: 'Y cualquier herramienta MCP', desc: 'Una conexión que podrás reutilizar con lo que llegue después.' },
    stepsTitle: 'Conectar es rápido',
    steps: [
      { title: 'Elige tu herramienta', desc: 'Claude, Cursor, ChatGPT u otra compatible con MCP.' },
      { title: 'Conecta tu cuenta de Vocify', desc: 'Una sola conexión para tu espacio de trabajo.' },
      { title: 'Pregunta', desc: 'Tus llamadas, cuentas y CRM, a una pregunta de distancia.' },
    ],
    promptsTitle: 'Qué podrás preguntar',
    promptsBadge: 'Ejemplos',
    prompts: [
      '¿Qué objeciones se repitieron esta semana en el equipo?',
      'Prepárame la llamada de las 11:30 con Acme.',
      '¿Qué le prometí a Marta en la última conversación?',
    ],
    closingTitle: 'Tu equipo ya habla con Vocify.',
    closingAccent: 'Ahora tu IA también.',
  },
  EN: {
    eyebrow: 'MCP',
    badge: 'Early access',
    title: 'Vocify, inside',
    accent: 'your AI.',
    subtitle:
      'Connect Vocify to Claude, Cursor and ChatGPT and ask about your conversations, your accounts and your CRM without leaving the tool you already use.',
    cta: 'Request access',
    tools: [
      { name: 'Claude', desc: 'Ask Claude about your calls and accounts.' },
      { name: 'Cursor', desc: 'Bring your customers’ context into your editor.' },
      { name: 'ChatGPT', desc: 'Check your sales activity from ChatGPT.' },
    ],
    more: { name: 'And any MCP tool', desc: 'One connection you will be able to reuse with whatever comes next.' },
    stepsTitle: 'Connecting is quick',
    steps: [
      { title: 'Pick your tool', desc: 'Claude, Cursor, ChatGPT or any other MCP-compatible tool.' },
      { title: 'Connect your Vocify account', desc: 'One connection for your workspace.' },
      { title: 'Ask', desc: 'Your calls, accounts and CRM, one question away.' },
    ],
    promptsTitle: 'What you will be able to ask',
    promptsBadge: 'Examples',
    prompts: [
      'Which objections came up most this week across the team?',
      'Prep me for the 11:30 call with Acme.',
      'What did I promise Marta in our last conversation?',
    ],
    closingTitle: 'Your team already talks to Vocify.',
    closingAccent: 'Now your AI does too.',
  },
};
