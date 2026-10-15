import type { Language } from './i18n';

export interface DownloadCopy {
  title: string;
  accent: string;
  subtitle: string;
  forYou: string;
  windows: { name: string; req: string; cta: string; note: string };
  mac: { name: string; req: string; cta: string; note: string };
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
      req: 'macOS 14.2 or later',
      cta: 'Coming soon',
      note: 'The Mac download is not published yet.',
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
      req: 'macOS 14.2 o posterior',
      cta: 'Próximamente',
      note: 'La descarga para Mac aún no está publicada.',
    },
    help: '¿Ayuda para instalarla? Escribe a',
  },
};
