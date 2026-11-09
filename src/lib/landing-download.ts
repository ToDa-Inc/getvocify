import type { Language } from './i18n';

export interface DownloadCopy {
  title: string;
  accent: string;
  subtitle: string;
  forYou: string;
  windows: { name: string; req: string; cta: string; note: string };
  mac: { name: string; req: string; cta: string; note: string };
  /** Shown once the Mac download starts: how to get past macOS's one-time block. */
  macSteps: {
    title: string;
    wink: string;
    steps: { title: string; body: string; alt: string }[];
    /** Where step 2 happens in System Settings, as the menus read. */
    path: string[];
    /** Opens System Settings on Privacy & Security. */
    openSettings: string;
    after: string;
  };
  help: string;
}

export const downloadCopy: Record<Language, DownloadCopy> = {
  EN: {
    title: 'Vocify for',
    accent: 'desktop.',
    subtitle: 'The call island and call capture, on your computer. Pick your system.',
    forYou: 'Your computer',
    windows: {
      name: 'Windows',
      req: 'Windows 10 or 11, 64-bit',
      cta: 'Download for Windows',
      note: 'Windows may show "Windows protected your PC". Click More info, then Run anyway.',
    },
    mac: {
      name: 'Mac',
      req: 'macOS 14.2 or later, Apple Silicon or Intel',
      cta: 'Download for Mac',
      note: 'Drag Vocify to Applications and open it. If macOS says it can\'t verify it, click Done, then System Settings › Privacy & Security › Open Anyway.',
    },
    macSteps: {
      title: 'Your download has started. Two clicks and you\'re in.',
      wink: 'We\'re not on Apple\'s guest list yet, so the first time macOS asks you to vouch for us. Once, never again.',
      steps: [
        {
          title: 'Open Vocify and click Done',
          body: 'Drag Vocify to Applications and open it. macOS says "Vocify" Not Opened. Click Done, not Move to Trash.',
          alt: 'macOS dialog: "Vocify" Not Opened, with the buttons Done and Move to Trash',
        },
        {
          title: 'Click Open Anyway',
          body: 'Open System Settings › Privacy & Security and scroll down to Security. Next to "Vocify" was blocked, click Open Anyway and confirm with your password or Touch ID.',
          alt: 'System Settings, Privacy & Security: "Vocify" was blocked to protect your Mac, with the Open Anyway button',
        },
      ],
      path: ['System Settings', 'Privacy & Security', 'Security'],
      openSettings: 'Open Privacy & Security',
      after: 'Vocify opens. Allow the microphone and the call audio, and from then on it opens normally and updates itself.',
    },
    help: 'Need help installing it? Write to',
  },
  ES: {
    title: 'Vocify para',
    accent: 'escritorio.',
    subtitle: 'La isla de llamadas y la captura de llamadas, en tu ordenador. Elige tu sistema.',
    forYou: 'Tu ordenador',
    windows: {
      name: 'Windows',
      req: 'Windows 10 u 11, 64 bits',
      cta: 'Descargar para Windows',
      note: 'Windows puede mostrar "Windows protegió su PC". Pulsa Más información y luego Ejecutar de todas formas.',
    },
    mac: {
      name: 'Mac',
      req: 'macOS 14.2 o posterior, Apple Silicon o Intel',
      cta: 'Descargar para Mac',
      note: 'Arrastra Vocify a Aplicaciones y ábrela. Si macOS dice que no puede verificarla, cierra el aviso y ve a Ajustes del Sistema › Privacidad y seguridad › Abrir igualmente.',
    },
    macSteps: {
      title: 'La descarga ha empezado. Dos clics y listo.',
      wink: 'Aún no estamos en la lista de invitados de Apple, así que la primera vez macOS te pide que respondas por nosotros. Una vez y nunca más.',
      steps: [
        {
          title: 'Abre Vocify y cierra el aviso',
          body: 'Arrastra Vocify a Aplicaciones y ábrela. macOS dice que no ha abierto "Vocify". Cierra el aviso sin moverla a la papelera.',
          alt: 'Aviso de macOS: "Vocify" no se ha abierto, con los botones para cerrar o mover a la papelera',
        },
        {
          title: 'Pulsa Abrir igualmente',
          body: 'Abre Ajustes del Sistema › Privacidad y seguridad y baja hasta Seguridad. Junto a "Vocify" se ha bloqueado, pulsa Abrir igualmente y confirma con tu contraseña o Touch ID.',
          alt: 'Ajustes del Sistema, Privacidad y seguridad: "Vocify" se ha bloqueado, con el botón Abrir igualmente',
        },
      ],
      path: ['Ajustes del Sistema', 'Privacidad y seguridad', 'Seguridad'],
      openSettings: 'Abrir Privacidad y seguridad',
      after: 'Vocify se abre. Permite el micrófono y el audio de la llamada, y a partir de ahí se abre sola y se actualiza sola.',
    },
    help: '¿Ayuda para instalarla? Escribe a',
  },
};
