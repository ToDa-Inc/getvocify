/**
 * VOCIFY THEME TOKENS
 * 
 * This file is the "Brain" of your UI. 
 * Changing a value here updates it across the entire platform.
 */

export const THEME_TOKENS = {
  // 1. TYPOGRAPHY
  // Bold, clean Inter for titles. No more italics.
  typography: {
    pageTitle: "text-3xl md:text-4xl font-black tracking-tighter text-foreground leading-tight",
    sectionTitle: "text-xl font-bold tracking-tight text-foreground",
    accentTitle: "text-beige font-black",
    capsLabel: "text-[10px] font-black uppercase tracking-[0.3em] text-muted-foreground/60",
    body: "text-base leading-relaxed text-muted-foreground",
  },

  // 2. RADIUS & SHAPES
  radius: {
    card: "rounded-[2rem]",
    pill: "rounded-full",
    container: "rounded-[3rem] md:rounded-[4rem]",
  },

  // 3. THE "PREMIUM LIGHT" CARD SYSTEM
  // This is the new glass + inner shadow concept
  cards: {
    base: "bg-card border border-border/50 shadow-soft",
    
    // The main "Focus" boxes (Record, Billing, etc.)
    premium: `
      bg-white/40 
      backdrop-blur-xl 
      border border-white/20 
      shadow-large 
      shadow-[inset_4px_4px_8px_rgba(255,255,255,0.8),inset_-4px_-4px_8px_rgba(0,0,0,0.02)]
    `.replace(/\s+/g, ' ').trim(),
    
    hover: "hover:shadow-medium hover:border-beige/20 transition-all duration-300 hover:-translate-y-1",
  },

  // 4. COLORS (Semantic)
  colors: {
    brand: "text-beige bg-beige",
    highlight: "bg-beige/10 text-beige",
    success: "text-success bg-success/10",
    warning: "text-warning bg-warning/10",
    foreground: "text-foreground",
    muted: "text-muted-foreground",
  },

  // 5. MOTION
  motion: {
    fadeIn: "animate-fade-in",
    tapScale: "active:scale-95 transition-transform",
  }
};

/**
 * REUSABLE UI PATTERNS
 * High-level building blocks
 */
export const V_PATTERNS = {
  // Use for "Welcome back, John" headers
  dashboardHeader: "mb-12 space-y-2",
  
  // The layout for the main record box
  focusBox: "p-12 text-center relative overflow-hidden group",
  
  // Standard list items (memos, etc.)
  listItem: "block p-6 transition-all duration-300",
};
