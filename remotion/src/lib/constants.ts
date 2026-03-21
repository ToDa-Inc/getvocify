export const COMP_WIDTH = 1920;
export const COMP_HEIGHT = 1080;
export const COMP_FPS = 30;

// Total target: ~40 seconds
export const SCENE_DUR = {
  intro:        6 * COMP_FPS,   // 6s — gives breathing room for word reveal
  problem:      5 * COMP_FPS,   // 5s
  solution:     6 * COMP_FPS,   // 6s
  whatsapp:     6 * COMP_FPS,   // 6s
  chrome:       6 * COMP_FPS,   // 6s
  integrations: 5 * COMP_FPS,   // 5s
  cta:          6 * COMP_FPS,   // 6s
  // Total: 39s
};

export const TOTAL_DURATION_FRAMES = Object.values(SCENE_DUR).reduce((a, b) => a + b, 0);

// Exact colors from the Vocify design system
export const COLORS = {
  cream:         'hsl(40, 33%, 96%)',
  creamDark:     'hsl(38, 25%, 88%)',
  creamDarker:   'hsl(35, 20%, 82%)',
  beige:         'hsl(35, 25%, 35%)',
  beigeLight:    'hsl(35, 20%, 50%)',
  beigeDark:     'hsl(35, 30%, 25%)',
  foreground:    'hsl(0, 0%, 4%)',
  muted:         'hsl(0, 0%, 40%)',
  white:         '#FFFFFF',
  border:        'hsl(38, 20%, 85%)',
  successBg:     '#dcfce7',
  successBorder: '#bbf7d0',
  successText:   '#16a34a',
  waBg:          '#ECE5DD',
  waHeader:      '#075E54',
  waGreen:       '#DCF8C6',
};
