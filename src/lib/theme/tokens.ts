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
    danger: "text-destructive bg-destructive/10",
    neutral: "text-muted-foreground bg-muted",
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
    /** The one hover for anything in a list: a row, a clickable line, a quiet control. */
    rowHover: "transition-colors duration-150 hover:bg-secondary/60 motion-reduce:transition-none",
    /** A text-only action inside a block ("Ver todo", "Cancelar"). Prefer `<Button variant="quiet" size="text">`. */
    quietAction: "text-[13px] text-muted-foreground transition-colors duration-150 hover:text-foreground motion-reduce:transition-none",
    pageLoad: "flex min-h-[280px] items-center justify-center",
    navPill: "rounded-full px-3.5 py-1.5 text-[13px] transition-colors",
    navPillActive: "glass-nav text-foreground",
    navPillIdle: "text-muted-foreground hover:bg-white/25 hover:text-foreground dark:hover:bg-white/5",
    /** Kit `Tabs` as a compact pill row (TabsList / TabsTrigger): Interacciones, Equipo, Coaching. */
    segmentList: "h-auto max-w-full flex-wrap justify-start rounded-full border border-border/50 bg-secondary/30 p-1",
    /** The active tab takes the nav pill's glass (materials.css .glass-segment), not a solid fill. */
    segmentTab:
      "glass-segment rounded-full border border-transparent px-3.5 py-1 text-xs font-normal text-muted-foreground transition-colors duration-150 hover:text-foreground motion-reduce:transition-none data-[state=active]:font-medium data-[state=active]:text-foreground data-[state=active]:shadow-none data-[state=on]:font-medium data-[state=on]:text-foreground data-[state=on]:shadow-none",
    /** A filter or choice that opens a menu ("Todas ▾", "SDR ▾"): a glass pill. */
    menuChip:
      "glass-nav inline-flex h-8 items-center gap-1.5 rounded-full px-3 text-[13px] text-foreground transition-colors duration-150 hover:bg-white/40 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring motion-reduce:transition-none disabled:opacity-60 dark:hover:bg-white/10",
  },
};

/**
 * Every floating list (DropdownMenu, Select, ContextMenu, Menubar) reads these, so a menu looks and
 * hovers the same wherever it opens. Highlight is a warm tint, never a solid fill; the selected
 * option carries a check on the right, never a bullet.
 */
export const MENU_TOKENS = {
  surface:
    "glass-menu z-50 min-w-[10rem] overflow-hidden rounded-xl p-1 text-foreground data-[state=open]:animate-in data-[state=closed]:animate-out data-[state=closed]:fade-out-0 data-[state=open]:fade-in-0 data-[state=closed]:zoom-out-95 data-[state=open]:zoom-in-95 data-[side=bottom]:slide-in-from-top-2 data-[side=left]:slide-in-from-right-2 data-[side=right]:slide-in-from-left-2 data-[side=top]:slide-in-from-bottom-2",
  item:
    "relative flex w-full cursor-default select-none items-center gap-2.5 rounded-lg px-2.5 py-2 text-[13px] text-foreground outline-none transition-colors duration-150 data-[highlighted]:bg-secondary/70 data-[disabled]:pointer-events-none data-[disabled]:opacity-50 motion-reduce:transition-none [&_svg]:size-4 [&_svg]:shrink-0 [&_svg]:text-muted-foreground data-[highlighted]:[&_svg]:text-foreground",
  itemDanger:
    "text-destructive data-[highlighted]:bg-destructive/10 data-[highlighted]:text-destructive [&_svg]:text-destructive data-[highlighted]:[&_svg]:text-destructive",
  /** The selected option: room on the right for the check. */
  itemSelectable: "pr-8",
  check: "absolute right-2.5 flex h-4 w-4 items-center justify-center text-beige [&_svg]:text-beige",
  label: "px-2.5 pb-1 pt-2 text-xs font-normal text-muted-foreground",
  separator: "-mx-1 my-1 h-px bg-border/70",
};

export const V_PATTERNS = {
  dashboardHeader: "mb-8 space-y-1.5",
  focusBox: "p-10 text-center relative overflow-hidden",
  listItem: "block p-5 transition-colors duration-150",
};
