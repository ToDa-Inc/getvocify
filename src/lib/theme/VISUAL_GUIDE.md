# Vocify visual system

One recipe per element. If a control already exists below, use it; if it does not fit, add a token
or a variant here, never an inline one-off. `npm run lint:ui` fails on the drift this guide prevents.

## Where things live

| What | Where |
|---|---|
| Base colors, radii (all three apps) | `shared/tokens/tokens.json` → `node scripts/build-tokens.mjs` |
| Dashboard theme, dark mode | `src/index.css` |
| Glass, shadows, motion (wins over `index.css`) | `src/lib/theme/materials.css` |
| Element recipes | `src/lib/theme/tokens.ts` (`THEME_TOKENS`, `MENU_TOKENS`) |
| Components | `src/components/ui/` |
| Shared across web / extension / desktop | `shared/ui/` → `node scripts/sync-shared.mjs` |

## Surfaces

- **Paper** (`bg-card` + hairline): content. Cards, lists, forms.
- **Glass** (`glass-panel`, `glass-nav`, `glass-menu`, `glass-segment`): floating chrome only, nav,
  menus, popovers, the selected pill. Never a content card.
- **Shadows**: `shadow-soft` (rest), `shadow-medium` (raised), `shadow-large` (floating). Tailwind's
  `sm/md/lg/xl/2xl` are mapped onto the same three. No arbitrary `shadow-[...]`.

## Controls

| Need | Use |
|---|---|
| Main action of a block | `<Button>` (default, one per block) |
| Secondary | `<Button variant="outline">` (glass) |
| Quiet text action | `<Button variant="quiet" size="text">` |
| Red text action / filled red | `variant="dangerGhost"` / `variant="destructive"` |
| Icon-only action | `<IconAction label>` (tooltip + pending). `tone="primary"` for the filled one, `pressed` for toggles |
| Pick one of 2–4 values of a setting | `<Segmented>` |
| Switch views of one page | `Tabs` (+ `segmentList` / `segmentTab` for the pill look) |
| On/off choice, several allowed | `<Toggle variant="chip">` |
| Pick from a list | `<Select>` (`variant="field"` in forms, `"chip"` for filters) |
| Menu of actions | `DropdownMenu` (`tone="danger"` for delete / sign out) |
| 2–4 values inside a menu | `DropdownMenuSegmented` (theme, language) |
| Loading | `VocifySpinner` (`tone="onFill"` on a beige button), `VocifyLoader` for a page |
| Row hover | `hover:bg-secondary/60` (`interaction.rowHover`) |

## Rules

- Status colors are tokens: `text-destructive`, `text-success`, `text-warning`, `text-beige`,
  `text-muted-foreground` (`THEME_TOKENS.colors.*`). No Tailwind palette, no hex, no `bg-white`.
- A selected option in a list carries a check on the right, never a bullet.
- One icon set: `lucide-react`, `strokeWidth` 1.5 for the thin look. Icons that move on a state
  change are `AnimIcon`.
- Hover, focus and pending always exist; menus and glass respect `prefers-reduced-motion` and
  `prefers-reduced-transparency`.
- The marketing site (`src/components/landing`) has its own palette and is outside the guard.
