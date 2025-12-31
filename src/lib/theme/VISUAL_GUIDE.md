# Vocify Visual Theme Engine 🎨

This system is built using **Design Tokens**. Instead of hardcoding colors and shadows in every file, we use a centralized "Brain" (`src/lib/theme/tokens.ts`). 

### Why this matters:
1.  **Instant Global Updates**: Change the `premium` card style in the token file, and every "Record" box, "Billing" box, and "Sidebar" card updates automatically across the entire app.
2.  **Consistency**: Ensures the exact same beige, corner radius, and shadow is used everywhere.
3.  **Clean Code**: Components read like a story (e.g., `THEME_TOKENS.cards.premium`) rather than a mess of CSS classes.

---

## 🏗️ Core Tokens (`THEME_TOKENS`)

### 1. Typography
*   `pageTitle`: Clean, black-weight Inter. No italics.
*   `accentTitle`: Used for the second word in headers (The "Beige" word).
*   `capsLabel`: Small, uppercase, tracked-out labels for metadata.

### 2. The "Premium Light" Card (`cards.premium`)
This is our signature style. It combines:
*   **Glassmorphism**: `white/40` background with `backdrop-blur-xl`.
*   **Inner Shadow (Lighting)**: Subtle highlight on top-left, depth on bottom-right.
*   **Tactile Feel**: High-quality shadows that make boxes feel like physical objects.

### 3. Radius
*   `card`: 2rem (32px) for list items.
*   `container`: 3rem to 4rem (48px-64px) for major sections like the "Record" card.

---

## 🧩 Reusable Patterns (`V_PATTERNS`)

*   `dashboardHeader`: Standard spacing for page titles.
*   `focusBox`: The layout for high-impact action areas.
*   `listItem`: Standard padding and transitions for clickable list items.

---

## 🎨 Palette Reference
*   **Primary**: `Beige` (hsl(35 25% 35%))
*   **Background**: `Creme/White` (hsl(40 33% 96%))
*   **Text**: `Foreground/Black` (hsl(0 0% 4%))

---

### How to use in code:
```tsx
import { THEME_TOKENS } from "@/lib/theme/tokens";

<div className={THEME_TOKENS.cards.premium}>
  <h1 className={THEME_TOKENS.typography.pageTitle}>Hello</h1>
</div>
```
