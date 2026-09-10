/**
 * Shared product tokens. Glass is for floating chrome only
 * (nav, sticky bars, overlays). Content sits on paper.
 */
export const THEME_TOKENS = {
  typography: {
    pageTitle: "text-[1.75rem] md:text-[2.125rem] font-normal tracking-tight text-foreground leading-[1.15]",
    sectionTitle: "text-[17px] font-normal tracking-tight text-foreground",
    accentTitle: "text-beige font-normal",
    editorialHeader: "font-serif italic font-normal",
    capsLabel: "text-[13px] font-normal text-muted-foreground",
    sectionRail: "text-[15px] font-normal tracking-tight text-foreground",
    body: "text-[15px] leading-relaxed text-muted-foreground",
  },

  radius: {
    card: "rounded-xl",
    pill: "rounded-full",
    container: "rounded-2xl",
  },

  cards: {
    base: "bg-card border border-border/70",
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

  /**
   * Interactive chrome. Use IconAction for icon-only controls (tooltip + press + pending).
   * Use ConfirmAction before destructive work. Toasts land bottom-right via Sonner.
   */
  interaction: {
    iconButton:
      "inline-flex h-9 w-9 items-center justify-center rounded-full text-muted-foreground hover:bg-secondary/60 hover:text-foreground disabled:pointer-events-none disabled:opacity-40",
    iconDanger: "hover:bg-destructive/10 hover:text-destructive",
    pageLoad: "flex min-h-[280px] items-center justify-center",
    navPill: "rounded-full px-3.5 py-1.5 text-[13px] transition-colors",
    navPillActive: "glass-nav text-foreground",
    navPillIdle: "text-muted-foreground hover:bg-white/25 hover:text-foreground",
  },
};

export const V_PATTERNS = {
  dashboardHeader: "mb-8 space-y-1.5",
  focusBox: "p-10 text-center relative overflow-hidden",
  listItem: "block p-5 transition-colors duration-150",
};
