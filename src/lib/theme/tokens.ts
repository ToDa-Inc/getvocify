/**
 * Shared product tokens. Glass is for floating chrome only
 * (nav, sticky bars, overlays). Content sits on paper.
 */
export const THEME_TOKENS = {
  typography: {
    pageTitle: "text-[1.75rem] md:text-[2.125rem] font-normal tracking-tight text-foreground leading-[1.15]",
    /** A block's name. Medium weight: titles have to read as titles, not as one more line. */
    sectionTitle: "text-[17px] font-medium tracking-tight text-foreground",
    /** The name of what is open in a detail panel ("Llamada en frío"). */
    panelTitle: "text-[22px] font-semibold tracking-[-0.015em] text-foreground",
    /** A group inside a block ("Pasos", "Competidores"): smaller than a title, still bold. */
    groupTitle: "text-sm font-semibold text-foreground",
    /**
     * One item in a list of settings (a step, an objection, a competitor): a bold name and one
     * plain line under it. The whole pattern is these two roles; nothing else carries weight.
     */
    itemTitle: "text-[15px] font-semibold tracking-[-0.005em] text-foreground",
    itemBody: "text-sm leading-relaxed text-foreground/80",
    /** The name of a field above its value. Never the same style as the value or as a hint. */
    fieldLabel: "text-xs font-medium text-muted-foreground",
    accentTitle: "text-beige font-normal",
    editorialHeader: "font-serif italic font-normal",
    /** Status and metadata ("Guardado", "3 pasos"). Not for headings: use groupTitle. */
    capsLabel: "text-[13px] font-normal text-muted-foreground",
    sectionRail: "text-[15px] font-normal tracking-tight text-foreground",
    body: "text-[15px] leading-relaxed text-muted-foreground",
  },

  radius: {
    card: "rounded-xl",
    /** Fields, list items and anything interactive inside a card. */
    control: "rounded-lg",
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
    navPillIdle: "text-muted-foreground hover:bg-white/25 hover:text-foreground dark:hover:bg-white/5",
    /** Kit `Tabs` as a compact pill row (TabsList / TabsTrigger): Interacciones, Equipo, Coaching. */
    segmentList: "h-auto max-w-full flex-wrap justify-start rounded-full border border-border/50 bg-secondary/30 p-1",
    /** The active tab takes the nav pill's glass (materials.css .glass-segment), not a solid fill. */
    segmentTab:
      "glass-segment rounded-full border border-transparent px-3.5 py-1 text-xs font-normal text-muted-foreground transition-colors duration-150 hover:text-foreground motion-reduce:transition-none data-[state=active]:font-medium data-[state=active]:text-foreground data-[state=active]:shadow-none",
    /** A filter or choice that opens a menu ("Todas ▾", "SDR ▾"): a glass pill. */
    menuChip:
      "glass-nav inline-flex h-8 items-center gap-1.5 rounded-full px-3 text-[13px] text-foreground transition-colors duration-150 hover:bg-white/40 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring motion-reduce:transition-none disabled:opacity-60 dark:hover:bg-white/10",
  },
};

export const V_PATTERNS = {
  dashboardHeader: "mb-8 space-y-1.5",
  focusBox: "p-10 text-center relative overflow-hidden",
  listItem: "block p-5 transition-colors duration-150",
};
