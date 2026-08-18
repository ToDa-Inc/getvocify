/**
 * Shared product tokens. Glass is for floating chrome only
 * (nav, sticky bars, overlays). Content sits on paper.
 */
export const THEME_TOKENS = {
  typography: {
    pageTitle: "text-[1.75rem] md:text-[2rem] font-semibold tracking-tight text-foreground leading-tight",
    sectionTitle: "text-lg font-semibold tracking-tight text-foreground",
    accentTitle: "text-beige font-semibold",
    editorialHeader: "font-serif italic font-normal",
    capsLabel: "text-xs font-medium text-muted-foreground",
    body: "text-[15px] leading-relaxed text-muted-foreground",
  },

  radius: {
    card: "rounded-xl",
    pill: "rounded-full",
    container: "rounded-2xl",
  },

  cards: {
    base: "bg-card border border-border",
    premium: "glass-panel",
    hover: "hover:border-beige/25 transition-colors duration-150",
  },

  colors: {
    brand: "text-beige bg-beige",
    highlight: "bg-beige/10 text-beige",
    success: "text-success bg-success/10",
    warning: "text-warning bg-warning/10",
    foreground: "text-foreground",
    muted: "text-muted-foreground",
  },

  motion: {
    fadeIn: "animate-fade-in",
    tapScale: "active:scale-[0.98] transition-transform duration-150",
  },
};

export const V_PATTERNS = {
  dashboardHeader: "mb-8 space-y-1.5",
  focusBox: "p-10 text-center relative overflow-hidden",
  listItem: "block p-5 transition-colors duration-150",
};
