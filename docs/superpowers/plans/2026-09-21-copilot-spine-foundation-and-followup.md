# Copilot Spine — Foundation + Follow-up Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship the shared UI foundation (one token source, one component kit for web, extension and desktop) and the first spine feature on top of it: a follow-up email drafted automatically after every real conversation, ready on the review screen of all three surfaces, handed off with one button.

**Spec:** `docs/superpowers/specs/2026-09-21-copilot-spine-design.md` (read §2–§4 first).

**Architecture:**
- `shared/tokens/tokens.json` → `scripts/build-tokens.mjs` → one generated CSS file per surface. Each file carries the surface's legacy names plus a shared `--v-*` namespace.
- `shared/ui/`: light-DOM custom elements. The render functions are pure; `.data` goes in and one `v-action` event comes out. The host owns every side effect. `scripts/sync-shared.mjs` copies the kit into the extension and the desktop; the web imports it through a Vite alias.
- The backend drafts the follow-up in the background right after extraction completes. It holds a single-flight lease that mirrors `pipeline_lease.py` and never blocks or fails the memo pipeline. `GET /api/v1/memos/{id}/followup` serves the view and is the safety net; `POST` records the hand-off.

**Tech Stack:** FastAPI + Supabase (PostgREST) + OpenRouter via `LLMClient`; React 18 + Vite + TanStack Query (web); vanilla ES modules (Chrome MV3 side panel, Electron renderer); `node --test`, `unittest`/pytest.

## Global Constraints
- Apply `/senior-code` standards: minimal surgical changes, zero duplication, no TODOs left behind.
- **Do not touch the in-progress work present at plan time**: `backend/app/services/deepgram_batch.py`, `backend/app/services/stt_batch.py`, `backend/test_stt_languages.py`, `backend/tests/test_deepgram_batch.py`, `.reticle/*`, and the untracked files listed by `git status` at HEAD `8aef9ec`. Stage files by name, never with `git add -A`.
- Generated files (the `tokens.css` outputs and the shared copies) are committed and guarded by `--check`. Never edit them by hand.
- Every task ends green: `make test`, `make test-js`, and `npm run build` wherever web files changed.
- Web UI changes are verified with Reticle per `CLAUDE.md`, before the task is reported done.

## Pre-flight (verified 2026-09-21 against getvocify `8aef9ec`, and getvocify-desktop `5f3730e` plus its uncommitted work)
- **Code validation.** Everything was checked against the code blocks of this document, not a separate copy.
  - The code of Tasks 2–5, 7 and 8 was run as written: 24 JS tests and 15 Python tests, all green.
  - The backend edits of Tasks 8–10 were applied to a scratch copy of `backend/`. Every anchor matched exactly once, the app loads with the new router (both operations appear in `app.openapi()`), and the full suite passes: 525 tests, 510 existing plus 15 new.
  - The extension, desktop and web glue (Tasks 11–13) was checked line by line against the files below but not executed. Each of those tasks ends with a smoke test or a Reticle verdict.
- **Extraction writers.** Three code paths complete an extraction:
  - `backend/app/api/memos.py:288–295`: pipeline, `update_memo_row(... extraction_complete_update(...))`.
  - `backend/app/api/memos.py:1998–2004`: re-extract, followed by `schedule_transcript_polish(...)` at `:2011`.
  - `backend/app/services/whatsapp/processor.py:2193`: voice-note insert. The new id is `memo_id = r.data[0]["id"]` at `:2216`, followed by `schedule_transcript_polish(...)`.

  `backend/app/services/telephony/call_processor.py:328` is the voicemail / no-conversation path. It writes a non-empty summary (*"Buzon de voz detectado…"*), so eligibility has to filter on `screening_outcome`, which migration 027 constrains to `connected | voicemail | no_response`.
- **Background-task precedent.** `schedule_transcript_polish` (`backend/app/services/transcript_sanitize.py:1027`) already uses the pattern `schedule_followup` copies: `get_running_loop` → `create_task` → a module-level task set.
- **Lease pattern.** `backend/app/services/pipeline_lease.py` guards `or_` with `hasattr` (`:97`) and confirms ownership by primary key, because PostgREST re-applies the PATCH filter to RETURNING (`:44`).
- **LLM.** `LLMClient.chat_json(messages, *, model, temperature, provider, timeout, max_retries) -> dict` (`backend/app/services/llm/client.py:51`), exported from `app.services.llm`. `model=None` falls back to the default model.
- **Memo visibility.** `_require_readable_memo(supabase, memo_id, user_id)` (`memos.py:59`) returns the row or raises 404. Other modules already import private helpers from `app.api.memos` (`services/recovery.py:93`).
- **Data.** Extraction keys are camelCase (`summary`, `nextSteps`, `contactName`, `contactEmail`, `contactPhone`; `app/models/memo.py:60`). `user_profiles` is keyed by `id` and has `full_name`. `app.deps` provides `get_supabase` and `get_user_id`; `backend/app/config.py` already imports `Optional`.
- **Migrations.** The latest file on disk is `036_crm_updates_upsert_deal.sql`, untracked at plan time (in-progress work).
- **Extension.** Runs as a side panel; `popup.js` is an ES module. `api.get(endpoint)` and `api.post(endpoint, body)` (`lib/api.js:219–220`) are already used by `popup.js` (`:3940`, `:4205`), and URLs open with `chrome.tabs.create`. No clipboard precedent. Hook points: `isCurrentReviewMemo` (`popup.js:236`), `clearReviewPreviewUi` (`:318`), `handleReviewState` (`:1731`).
- **Desktop.** `renderer/app.js` loads as a module (`index.html:121`). `request(path, { method, body, token })` (`app.js:190`) serializes an object body; the token comes from `localStorage.getItem(STORAGE.token)`. `openReview` (`:491`) sets `reviewContext` and ends with `renderReview()` (`:525`). The bridge is `window.vocifyDesktop.shell.openExternal` (`preload.cjs:27`). No clipboard precedent.
  - **Blocker found:** `shell:open-external` only opens `https?://` (`electron-main.mjs:334`) and returns `{ok:true}` even when it drops the URL. A `mailto:` would silently do nothing. Task 12 fixes it.
- **Web.** React 18.3 with `@types/react` 18.3.23 (a global `JSX` augmentation still merges into `React.JSX`), TanStack Query 5.83 (`refetchInterval` receives the query), Tailwind 3.4. `API_BASE` already ends in `/api/v1` (`src/shared/lib/api-client.ts:17`). `memosApi` methods are arrow properties with a JSDoc line. Hooks use kebab-case files (`src/hooks/use-mobile.tsx`), and ambient types live next to `src/vite-env.d.ts`. `MemoDetail` gates its right column on `canSeeReview` (`:294`). The Vite alias block is at `vite.config.ts:15`.
- **UI language.** All three surfaces declare `<html lang="en">` and their UI is in English. `<v-followup>` follows the host's `lang`, so today it renders its English strings (*"Writing the follow-up…"*, *"Opened in your mail app."*). The draft itself is written in the conversation's language.
- **FastAPI.** Included routers resolve lazily, so `app.routes` does not list them: check routes through `app.openapi()["paths"]`.
- **Runtime.** `test-js` in the `Makefile` already runs `cd desktop && node --test lib/*.test.js`, so the monorepo layout was already intended. The root `package.json` is `"type": "module"`, so `shared/` and `scripts/` run as ESM under Node 22.

---

### Task 1: Bring the desktop companion into the monorepo

**Gate:** founder go-ahead (spec §3.6). If declined, skip this task and export `VOCIFY_DESKTOP_DIR=../getvocify-desktop` for Tasks 2, 5 and 12. Paths below then read `../getvocify-desktop/...` instead of `desktop/...`.

**Files:**
- Delete: `desktop/README.md` (pointer)
- Create: `desktop/**` (imported with history)
- Create: `.github/workflows/desktop-*.yml` (moved from `desktop/.github/workflows/`)
- Modify: `README.md`

- [ ] **Step 1: Make sure nothing lives only on one machine**

The desktop has finished, uncommitted work, and the running app already depends on it: `renderer/app.js` imports `lib/permissions.js` and `lib/mic-devices.js`, and `renderer/index.html` links `renderer/theme.css`. In total:
- 17 modified tracked files, among them `electron-main.mjs`, `preload.cjs`, `package.json`, `renderer/*` and several `lib/*` modules with their tests.
- New files: `lib/{permissions,mic-devices,memo-review,extraction-omit}.js` with their tests, `native/`, `scripts/build-macos-tap.mjs`, `docs/` and `renderer/theme.css`.

Its owner commits and pushes all of it.

`../getvocify-desktop/getvocify-desktop/` is a second clone at the same commit (`5f3730e`) with no local changes. It is untracked and not ignored, so a `git add -A` would commit it as an embedded repository. Its owner removes it before committing.

Run: `git -C ../getvocify-desktop status --short`
Expected: empty output.

- [ ] **Step 2: Clean working tree in getvocify**

`git subtree` refuses to run with local modifications. Ask whoever owns the in-progress files (Global Constraints) to commit or stash them. Do not stash someone else's work yourself.

- [ ] **Step 3: Import with history**

```bash
git rm desktop/README.md
git commit -m "chore(desktop): remove pointer README before importing the companion"
git subtree add --prefix=desktop ../getvocify-desktop main
```
Expected: `Added dir 'desktop'`.

- [ ] **Step 4: Move CI and fix docs**

`git mv desktop/.github/workflows/dmg.yml .github/workflows/desktop-dmg.yml` (it is the only workflow; GitHub ignores workflows outside the root). A `working-directory` default only affects `run` steps, so three edits are needed:
- Under `jobs.dmg`, add `defaults: { run: { working-directory: desktop } }`.
- On `actions/setup-node`, add `cache-dependency-path: desktop/package-lock.json`. Otherwise `cache: npm` keys on the web app's root lockfile.
- On `actions/upload-artifact`, prefix both paths: `desktop/dist/*.dmg` and `desktop/dist/*.zip`.

Also add `paths: ['desktop/**', '.github/workflows/desktop-dmg.yml']` under `push`, so web-only pushes do not build a DMG.

In `README.md`, change the `desktop/` row (line 12) to `Electron companion (meetings, system audio)`. Replace the sibling-clone instructions under *Desktop companion* with `cd desktop && npm install && npm start`.

- [ ] **Step 5: Verify**

Run: `make test-js`
Expected: the extension, web and desktop lib tests all PASS. The desktop line of the `Makefile` now finds its tests.

- [ ] **Step 6: Commit**

```bash
git add .github/workflows README.md
git commit -m "chore(desktop): run companion CI from the monorepo"
```

---

### Task 2: Canonical tokens — one source, one file per surface

**Files:**
- Create: `shared/tokens/tokens.json`, `scripts/build-tokens.mjs`, `scripts/build-tokens.test.mjs`
- Generate: `src/styles/tokens.css`, `chrome-extension/popup/tokens.css`, `desktop/renderer/tokens.css`
- Modify: `src/index.css`, `chrome-extension/popup/index.html`, `chrome-extension/popup/styles.css`, `desktop/renderer/index.html`, `desktop/renderer/theme.css`, `Makefile`

**Interfaces:**
- Produces: the `--v-*` variables on `:root` in every surface (consumed by Task 4). Legacy variable names keep working unchanged.
- Visible change, on purpose (`PLAN_INTEGRACION.md` §2.3):
  - **Web:** muted text goes from `30 6% 46%` to `30 6% 42%` (4.18:1 → 4.86:1 on cream), and success goes from `142 76% 36%` to `125 32% 30%` (3.35:1 → 6.85:1).
  - **Extension:** text becomes `30 10% 14%` and the border `38 20% 85%`, the web values.

- [ ] **Step 1: Write the failing test** — `scripts/build-tokens.test.mjs`

```js
import test from 'node:test';
import assert from 'node:assert/strict';
import { cpSync, mkdtempSync, mkdirSync, readFileSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join, resolve, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';
import { buildAll, renderTarget } from './build-tokens.mjs';

const here = dirname(fileURLToPath(import.meta.url));
const tokens = JSON.parse(readFileSync(resolve(here, '../shared/tokens/tokens.json'), 'utf8'));

function sandbox({ withDesktop }) {
  const root = mkdtempSync(join(tmpdir(), 'tokens-'));
  cpSync(resolve(here, '../shared/tokens'), join(root, 'shared/tokens'), { recursive: true });
  if (withDesktop) mkdirSync(join(root, 'desktop/renderer'), { recursive: true });
  return root;
}

test('web gets triplets under canonical names (Tailwind consumes hsl(var(--x)))', () => {
  const css = renderTarget(tokens, tokens.targets.web);
  assert.match(css, /--muted-foreground: 30 6% 42%;/);
  assert.match(css, /--muted: 38 20% 90%;/);
  assert.match(css, /--radius-pill: 999px;/);
});

test('extension keeps its own names and full colors, so styles.css needs no rewrite', () => {
  const css = renderTarget(tokens, tokens.targets.extension);
  assert.match(css, /--muted: hsl\(30 6% 42%\);/, 'extension --muted is text color, not the web surface');
  assert.match(css, /--secondary: hsl\(38 25% 88%\);/);
  assert.doesNotMatch(css, /  --muted-foreground:/);
});

test('every surface gets the same --v-* namespace for the shared kit', () => {
  for (const key of ['web', 'desktop', 'extension']) {
    const css = renderTarget(tokens, tokens.targets[key]);
    assert.match(css, /--v-beige: hsl\(35 25% 35%\);/, key);
    assert.match(css, /--v-muted-foreground: hsl\(30 6% 42%\);/, key);
    assert.match(css, /--v-radius-container: 18px;/, key);
  }
});

test('unknown token in a target name map fails loudly', () => {
  assert.throws(() => renderTarget(tokens, { format: 'color', names: { x: 'nope' } }), /Unknown color token "nope"/);
});

test('build writes present targets, skips an absent optional desktop, and --check passes after', () => {
  const root = sandbox({ withDesktop: false });
  const first = buildAll({ root, env: {} });
  assert.deepEqual(first.written.sort(), ['extension', 'web']);
  assert.deepEqual(first.skipped, ['desktop']);
  assert.deepEqual(buildAll({ root, check: true, env: {} }).stale, []);
});

test('--check flags a hand-edited generated file', () => {
  const root = sandbox({ withDesktop: true });
  buildAll({ root, env: {} });
  writeFileSync(join(root, 'src/styles/tokens.css'), '/* edited */');
  assert.deepEqual(buildAll({ root, check: true, env: {} }).stale, ['web']);
});

test('VOCIFY_DESKTOP_DIR points the desktop output at a sibling repo', () => {
  const root = sandbox({ withDesktop: false });
  const sibling = mkdtempSync(join(tmpdir(), 'desktop-'));
  mkdirSync(join(sibling, 'renderer'), { recursive: true });
  const report = buildAll({ root, env: { VOCIFY_DESKTOP_DIR: sibling } });
  assert.ok(report.written.includes('desktop'));
  assert.match(readFileSync(join(sibling, 'renderer/tokens.css'), 'utf8'), /--beige: 35 25% 35%;/);
});
```

- [ ] **Step 2: Run it to see it fail**

Run: `node --test scripts/build-tokens.test.mjs`
Expected: FAIL — `Cannot find module .../build-tokens.mjs`.

- [ ] **Step 3: Create `shared/tokens/tokens.json`**

```json
{
  "color": {
    "background": "40 33% 96%",
    "foreground": "30 10% 14%",
    "card": "0 0% 100%",
    "muted": "38 20% 90%",
    "muted-foreground": "30 6% 42%",
    "border": "38 20% 85%",
    "cream": "40 33% 96%",
    "cream-dark": "38 25% 88%",
    "beige": "35 25% 35%",
    "beige-light": "35 20% 50%",
    "beige-dark": "35 30% 25%",
    "success": "125 32% 30%",
    "destructive": "0 72% 51%",
    "ink": "30 15% 8%"
  },
  "radius": {
    "card": "12px",
    "container": "18px",
    "pill": "999px"
  },
  "targets": {
    "web": { "file": "src/styles/tokens.css", "format": "triplet" },
    "desktop": { "file": "desktop/renderer/tokens.css", "format": "triplet", "optional": true },
    "extension": {
      "file": "chrome-extension/popup/tokens.css",
      "format": "color",
      "names": {
        "beige": "beige",
        "beige-light": "beige-light",
        "beige-dark": "beige-dark",
        "cream": "cream",
        "foreground": "foreground",
        "muted": "muted-foreground",
        "border": "border",
        "secondary": "cream-dark",
        "success": "success"
      }
    }
  }
}
```

- [ ] **Step 4: Create `scripts/build-tokens.mjs`**

```js
#!/usr/bin/env node
// One source (shared/tokens/tokens.json), one output per surface.
// Every output carries two layers:
//   1. the surface's own legacy names, in the format it already consumes
//        web, desktop → HSL triplets, used as hsl(var(--x))   (Tailwind/shadcn)
//        extension    → full colors under its own names, used as var(--x)
//   2. the shared --v-* namespace (full colors), the only thing shared/ui/vocify-ui.css reads
// Usage: node scripts/build-tokens.mjs [--check]
//   --check exits 1 when a generated file is missing or stale (CI).
// VOCIFY_DESKTOP_DIR overrides where the desktop app lives (sibling repo).
import { existsSync, mkdirSync, readFileSync, writeFileSync } from 'node:fs';
import { dirname, join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

const HEADER = '/* Generated by scripts/build-tokens.mjs from shared/tokens/tokens.json. Do not edit by hand. */\n';

export function renderTarget(tokens, target) {
  const lines = [];
  if (target.format === 'color') {
    for (const [name, key] of Object.entries(target.names)) {
      const value = tokens.color[key];
      if (value == null) throw new Error(`Unknown color token "${key}" for --${name}`);
      lines.push(`  --${name}: hsl(${value});`);
    }
  } else {
    for (const [name, value] of Object.entries(tokens.color)) lines.push(`  --${name}: ${value};`);
    for (const [name, value] of Object.entries(tokens.radius ?? {})) lines.push(`  --radius-${name}: ${value};`);
  }
  for (const [name, value] of Object.entries(tokens.color)) lines.push(`  --v-${name}: hsl(${value});`);
  for (const [name, value] of Object.entries(tokens.radius ?? {})) lines.push(`  --v-radius-${name}: ${value};`);
  return `${HEADER}:root {\n${lines.join('\n')}\n}\n`;
}

function resolveTargetPath(root, key, target, env) {
  if (key === 'desktop' && env.VOCIFY_DESKTOP_DIR) return join(resolve(root, env.VOCIFY_DESKTOP_DIR), 'renderer/tokens.css');
  return join(root, target.file);
}

export function buildAll({ root, check = false, env = process.env }) {
  const tokens = JSON.parse(readFileSync(join(root, 'shared/tokens/tokens.json'), 'utf8'));
  const report = { written: [], stale: [], skipped: [] };
  for (const [key, target] of Object.entries(tokens.targets)) {
    const file = resolveTargetPath(root, key, target, env);
    if (target.optional && !existsSync(dirname(file))) {
      report.skipped.push(key);
      continue;
    }
    const css = renderTarget(tokens, target);
    const current = existsSync(file) ? readFileSync(file, 'utf8') : null;
    if (current === css) continue;
    if (check) {
      report.stale.push(key);
      continue;
    }
    mkdirSync(dirname(file), { recursive: true });
    writeFileSync(file, css);
    report.written.push(key);
  }
  return report;
}

if (process.argv[1] === fileURLToPath(import.meta.url)) {
  const root = resolve(dirname(fileURLToPath(import.meta.url)), '..');
  const check = process.argv.includes('--check');
  const report = buildAll({ root, check });
  for (const key of report.skipped) console.warn(`tokens: skipped ${key} (target folder not found)`);
  if (check && report.stale.length) {
    console.error(`tokens: stale → ${report.stale.join(', ')}. Run: node scripts/build-tokens.mjs`);
    process.exit(1);
  }
  if (!check) console.log(report.written.length ? `tokens: wrote ${report.written.join(', ')}` : 'tokens: up to date');
}
```

- [ ] **Step 5: Run the tests**

Run: `node --test scripts/build-tokens.test.mjs`
Expected: 7 tests PASS.

- [ ] **Step 6: Generate**

Run: `node scripts/build-tokens.mjs`
Expected: `tokens: wrote web, desktop, extension`.

- [ ] **Step 7: Wire the web**

In `src/index.css`, add `@import "./styles/tokens.css";` directly after the Google Fonts `@import` on line 1. Every `@import` must come before `@font-face`.

Then delete from its `:root` block only the variables the generated file now owns:

```
--background --foreground --card --muted --muted-foreground --border --destructive
--cream --cream-dark --beige --beige-light --beige-dark --success --ink
```

Keep everything else, including `--primary`, `--secondary`, `--accent`, `--popover`, `--input`, `--ring`, `--radius`, `--sidebar-*`, `--cream-darker`, `--warning`, `--processing`, the shadows and the whole `.dark` block.

- [ ] **Step 8: Wire the extension**

In `chrome-extension/popup/index.html`, add `<link rel="stylesheet" href="tokens.css">` as the first stylesheet, before `styles.css`.

In `chrome-extension/popup/styles.css` `:root`, delete `--beige`, `--beige-light`, `--beige-dark`, `--cream`, `--foreground`, `--muted`, `--border`, `--secondary` and `--success`. Keep `--hairline`, `--hover-fill`, `--radius`, the shadows and `--glass*`.

- [ ] **Step 9: Wire the desktop**

In `desktop/renderer/index.html`, add `<link rel="stylesheet" href="./tokens.css" />` before `./theme.css`.

In `desktop/renderer/theme.css` `:root`, delete the color variables the generated file owns and `--radius-card`, `--radius-container` and `--radius-pill`. Keep `--hairline`, `--font-*`, the shadows, `--space-*`, `--type-*`, `--z-*` and `--motion-fast`.

- [ ] **Step 10: Wire the checks**

In the `Makefile`, add to `test-js`:
```make
	node --test scripts/*.test.mjs
```
Add a new target:
```make
check-generated:
	node scripts/build-tokens.mjs --check
```

- [ ] **Step 11: Verify**

Run: `make test-js && npm run build && make check-generated`
Expected: PASS, 0 errors, no stale output.

Reticle (web), intent *"Muted text meets AA contrast on cream"*: drive to `/dashboard` and `reticle_assert` that an element rendered with `text-muted-foreground` has computed color `rgb(114, 107, 101)`.

Extension and desktop: reload each and confirm the review screen reads the same as before, with slightly darker secondary text.

- [ ] **Step 12: Commit**

```bash
git add shared/tokens scripts/build-tokens.mjs scripts/build-tokens.test.mjs src/styles/tokens.css src/index.css \
  chrome-extension/popup/tokens.css chrome-extension/popup/index.html chrome-extension/popup/styles.css \
  desktop/renderer/tokens.css desktop/renderer/index.html desktop/renderer/theme.css Makefile
git commit -m "feat(design): one token source for web, extension and desktop"
```

---

### Task 3: Shared UI kernel

**Files:**
- Create: `shared/ui/html.js`, `shared/ui/v-element.js`, `shared/ui/i18n.js`, `shared/ui/compose.js`, `shared/ui/ui.test.js`
- Modify: `Makefile`

**Interfaces:**
- Produces:
  - `html\`\``, `raw()` and `renderToString()` — escaping by construction.
  - `VElement` and `define(tag, Class)` — `.data` in, `v-action` `{action, value, element}` out, `shouldRepaint(prev, next)` to override.
  - `strings(lang)` — the shared chrome strings.
  - `composeTarget(draft) → {ok, url} | {ok:false, reason, fallback?}`.

- [ ] **Step 1: Write the failing test** — `shared/ui/ui.test.js`

```js
import test from 'node:test';
import assert from 'node:assert/strict';
import { html, raw, renderToString, escapeHtml } from './html.js';
import { composeTarget } from './compose.js';

// ---------- html ----------
test('html escapes every interpolation', () => {
  const out = renderToString(html`<p title="${'"x"'}">${'<script>alert(1)</script>'}</p>`);
  assert.equal(out, '<p title="&quot;x&quot;">&lt;script&gt;alert(1)&lt;/script&gt;</p>');
});

test('nested fragments are not double-escaped; arrays join; false/null render nothing', () => {
  const items = ['a&b', 'c'].map((x) => html`<li>${x}</li>`);
  const out = renderToString(html`<ul>${items}${false}${null}${raw('<hr>')}</ul>`);
  assert.equal(out, '<ul><li>a&amp;b</li><li>c</li><hr></ul>');
});

test('escapeHtml handles null and numbers', () => {
  assert.equal(escapeHtml(null), '');
  assert.equal(escapeHtml(42), '42');
});

// ---------- compose ----------
test('mailto encodes subject and body', () => {
  const r = composeTarget({ channel: 'email', to: 'marina@tenes.io', subject: 'Hola & más', body: 'a b\nc' });
  assert.deepEqual(r, { ok: true, url: 'mailto:marina@tenes.io?subject=Hola%20%26%20m%C3%A1s&body=a%20b%0Ac' });
});

test('long mailto falls back to subject-only draft', () => {
  const r = composeTarget({ channel: 'email', to: 'a@b.co', subject: 'S', body: 'x'.repeat(3000) });
  assert.equal(r.ok, false);
  assert.equal(r.reason, 'too_long');
  assert.equal(r.fallback, 'mailto:a@b.co?subject=S');
});

test('gmail and outlook compose URLs', () => {
  assert.match(composeTarget({ channel: 'email', to: 'a@b.co', subject: 'S', body: 'B', mailClient: 'gmail' }).url,
    /^https:\/\/mail\.google\.com\/mail\/\?view=cm&fs=1&to=a%40b\.co&su=S&body=B$/);
  assert.match(composeTarget({ channel: 'email', to: 'a@b.co', subject: 'S', body: 'B', mailClient: 'outlook' }).url,
    /^https:\/\/outlook\.office\.com\/mail\/deeplink\/compose\?to=a%40b\.co&subject=S&body=B$/);
});

test('whatsapp strips formatting; rejects missing numbers and bad emails', () => {
  assert.equal(composeTarget({ channel: 'whatsapp', phone: '+34 600 111 222', body: 'Hola' }).url, 'https://wa.me/34600111222?text=Hola');
  assert.deepEqual(composeTarget({ channel: 'whatsapp', phone: '' }), { ok: false, reason: 'no_phone' });
  assert.deepEqual(composeTarget({ channel: 'email', to: 'not-an-email' }), { ok: false, reason: 'no_email' });
});
```

- [ ] **Step 2: Run it to see it fail**

Run: `node --test shared/ui/ui.test.js`
Expected: FAIL — module not found.

- [ ] **Step 3: Create `shared/ui/html.js`**

```js
// Every interpolation is escaped unless it is itself an html`` fragment or raw().
// Transcripts are user-controlled text; this is the only way markup gets built.
const ESCAPES = { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' };
const RAW = Symbol('vocify.raw');

export function escapeHtml(value) {
  return String(value ?? '').replace(/[&<>"']/g, (ch) => ESCAPES[ch]);
}

export function raw(markup) {
  return { [RAW]: String(markup ?? '') };
}

function serialize(value) {
  if (value == null || value === false || value === true) return '';
  if (Array.isArray(value)) return value.map(serialize).join('');
  if (typeof value === 'object' && RAW in value) return value[RAW];
  return escapeHtml(value);
}

export function html(strings, ...values) {
  let out = strings[0];
  for (let i = 0; i < values.length; i += 1) out += serialize(values[i]) + strings[i + 1];
  return raw(out);
}

export function renderToString(fragment) {
  return serialize(fragment);
}
```

- [ ] **Step 4: Create `shared/ui/v-element.js`**

```js
import { renderToString } from './html.js';

// Light-DOM custom element: data in through `.data`, intent out through one
// bubbling `v-action` event. Components never fetch and never navigate; the
// host surface (extension, desktop, web) owns effects.
export class VElement extends HTMLElement {
  #data = null;
  editing = false;

  connectedCallback() {
    if (!this.dataset.vBound) {
      this.dataset.vBound = '1';
      this.addEventListener('click', (event) => this.#onClick(event));
      this.addEventListener('input', () => {
        this.editing = true;
      });
    }
    this.#paint();
  }

  get data() {
    return this.#data;
  }

  set data(next) {
    const prev = this.#data;
    this.#data = next;
    if (this.isConnected && this.shouldRepaint(prev, next)) this.#paint();
  }

  // Override to protect in-progress edits from background refetches.
  shouldRepaint() {
    return true;
  }

  #paint() {
    this.innerHTML = this.#data == null ? '' : renderToString(this.constructor.render(this.#data, this));
  }

  #onClick(event) {
    const target = event.target.closest('[data-action]');
    if (!target || !this.contains(target)) return;
    this.dispatchEvent(
      new CustomEvent('v-action', {
        bubbles: true,
        detail: { action: target.dataset.action, value: target.dataset.value ?? null, element: this },
      }),
    );
  }

  static render() {
    return '';
  }
}

export function define(tag, ElementClass) {
  if (!customElements.get(tag)) customElements.define(tag, ElementClass);
}
```

- [ ] **Step 5: Create `shared/ui/i18n.js`**

```js
// Chrome strings for shared components only. Content strings (reasons, due
// labels, the draft itself) arrive already written from the server.
const STRINGS = {
  es: {
    followupFor: (name) => `Seguimiento para ${name}`,
    followupFallback: 'Seguimiento',
    writing: 'Escribiendo el seguimiento…',
    send: 'Enviar',
    whatsapp: 'WhatsApp',
    copy: 'Copiar',
    addEmail: 'Sin email del contacto: cópialo o envíalo por WhatsApp.',
    // Honest wording: without mail OAuth we only know it was opened, not delivered.
    openedMail: 'Abierto en tu correo.',
    openedWhatsapp: 'Abierto en WhatsApp.',
  },
  en: {
    followupFor: (name) => `Follow-up for ${name}`,
    followupFallback: 'Follow-up',
    writing: 'Writing the follow-up…',
    send: 'Send',
    whatsapp: 'WhatsApp',
    copy: 'Copy',
    addEmail: 'No email for this contact: copy it or send it on WhatsApp.',
    openedMail: 'Opened in your mail app.',
    openedWhatsapp: 'Opened in WhatsApp.',
  },
};

export function strings(lang) {
  return STRINGS[String(lang || '').slice(0, 2).toLowerCase()] || STRINGS.es;
}
```

- [ ] **Step 6: Create `shared/ui/compose.js`**

```js
// Where "Enviar" goes. Pure: the host surface performs the navigation.
const MAILTO_MAX = 1800; // conservative: some mail clients truncate longer mailto URLs
const EMAIL = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

function query(params) {
  return Object.entries(params)
    .filter(([, value]) => value != null && value !== '')
    .map(([key, value]) => `${key}=${encodeURIComponent(value)}`)
    .join('&');
}

/**
 * @param {{channel:'email'|'whatsapp', to?:string, phone?:string, subject?:string,
 *          body?:string, mailClient?:'default'|'gmail'|'outlook'}} draft
 * @returns {{ok:true, url:string} | {ok:false, reason:'no_email'|'no_phone'|'too_long', fallback?:string}}
 */
export function composeTarget({ channel, to = '', phone = '', subject = '', body = '', mailClient = 'default' }) {
  if (channel === 'whatsapp') {
    const digits = String(phone).replace(/\D/g, '');
    if (digits.length < 8) return { ok: false, reason: 'no_phone' };
    return { ok: true, url: `https://wa.me/${digits}?${query({ text: body })}` };
  }

  const address = String(to).trim();
  if (!EMAIL.test(address)) return { ok: false, reason: 'no_email' };

  if (mailClient === 'gmail') {
    return { ok: true, url: `https://mail.google.com/mail/?${query({ view: 'cm', fs: '1', to: address, su: subject, body })}` };
  }
  if (mailClient === 'outlook') {
    return { ok: true, url: `https://outlook.office.com/mail/deeplink/compose?${query({ to: address, subject, body })}` };
  }

  const url = `mailto:${address}?${query({ subject, body })}`;
  if (url.length > MAILTO_MAX) {
    // Host copies the body to the clipboard and opens the subject-only draft.
    return { ok: false, reason: 'too_long', fallback: `mailto:${address}?${query({ subject })}` };
  }
  return { ok: true, url };
}
```

- [ ] **Step 7: Run the tests**

Run: `node --test shared/ui/ui.test.js`
Expected: 7 tests PASS.

- [ ] **Step 8: Add the kit to `make test-js`**

```make
	node --test shared/ui/*.test.js
```

- [ ] **Step 9: Commit**

```bash
git add shared/ui/html.js shared/ui/v-element.js shared/ui/i18n.js shared/ui/compose.js shared/ui/ui.test.js Makefile
git commit -m "feat(ui): shared light-DOM element kit with escaping by construction"
```

---

### Task 4: The follow-up component and the shared stylesheet

**Files:**
- Create: `shared/ui/components/followup.js`, `shared/ui/components/v-followup.js`, `shared/ui/vocify-ui.css`
- Modify: `shared/ui/ui.test.js`

**Interfaces:**
- Consumes: Task 3. The `--v-*` variables come from Task 2.
- Produces:
  - `<v-followup>`: `.data = FollowupView`; emits `v-action` with `action` `send` (value `email` or `whatsapp`) or `copy`.
  - A `.value` getter returning `{subject, body}` with the rep's edits included.
  - `FollowupView = {status: 'generating'|'ready'|'sent'|'unavailable', recipientName?, to?, phone?, subject?, body?, channel?}`. It is the exact shape `GET /api/v1/memos/{id}/followup` returns (Task 10).
  - `followupNeedsRepaint(prev, next, editing)`: the pure rule behind "edits are sacred". Hosts assign `.data` for the same memo (polling) and for a different memo (desktop and web reuse the element), so comparing status alone would leave memo A's edited draft on screen for memo B.

- [ ] **Step 1: Add the failing tests** — append to `shared/ui/ui.test.js`

Add the import at the top:
```js
import { followupNeedsRepaint, renderFollowup } from './components/followup.js';
```

Append:
```js
// ---------- follow-up ----------
const ready = {
  status: 'ready',
  recipientName: 'Marina',
  to: 'marina@tenes.io',
  phone: '+34600111222',
  subject: 'Caso de logística',
  body: 'Hola Marina,\ngracias por el rato de hoy.',
};

test('generating state is busy, announces itself, and reserves space', () => {
  const out = renderToString(renderFollowup({ status: 'generating', recipientName: 'Marina' }, 'es'));
  assert.match(out, /aria-busy="true"/);
  assert.match(out, /role="status">Escribiendo el seguimiento…/);
  assert.match(out, /v-followup__skeleton/);
});

test('ready state: email is primary, WhatsApp is ghost, copy always present', () => {
  const out = renderToString(renderFollowup(ready, 'es'));
  assert.match(out, /class="v-pill v-pill--primary" data-action="send" data-value="email">Enviar</);
  assert.match(out, /class="v-pill v-pill--ghost" data-action="send" data-value="whatsapp">WhatsApp</);
  assert.match(out, /data-action="copy">Copiar</);
  assert.doesNotMatch(out, /v-followup__hint/);
});

test('no email: no send button, hint shown, WhatsApp becomes primary', () => {
  const out = renderToString(renderFollowup({ ...ready, to: '' }, 'es'));
  assert.doesNotMatch(out, /data-value="email"/);
  assert.match(out, /v-followup__hint/);
  assert.match(out, /v-pill--primary" data-action="send" data-value="whatsapp"/);
});

test('draft text from a transcript cannot inject markup', () => {
  const out = renderToString(renderFollowup({ ...ready, body: '<img src=x onerror=alert(1)>' }, 'es'));
  assert.doesNotMatch(out, /<img/);
  assert.match(out, /&lt;img src=x onerror=alert\(1\)&gt;/);
});

test('sent state says what we know: it was opened, not that it was delivered', () => {
  const mail = renderToString(renderFollowup({ status: 'sent', channel: 'email', recipientName: 'Marina' }, 'es'));
  assert.match(mail, /is-sent/);
  assert.match(mail, /role="status">Abierto en tu correo\./);
  const wa = renderToString(renderFollowup({ status: 'sent', channel: 'whatsapp' }, 'es'));
  assert.match(wa, /Abierto en WhatsApp\./);
});

test('unavailable renders nothing; English labels switch with lang', () => {
  assert.equal(renderToString(renderFollowup({ status: 'unavailable' }, 'es')), '');
  assert.match(renderToString(renderFollowup(ready, 'en-GB')), /Follow-up for Marina/);
});

test('a refetch of the same draft keeps the edits; a new status or another draft repaints', () => {
  assert.equal(followupNeedsRepaint(ready, { ...ready }, false), true);
  assert.equal(followupNeedsRepaint(ready, { ...ready }, true), false, 'polling must not wipe what the rep types');
  assert.equal(followupNeedsRepaint(ready, { status: 'sent', channel: 'email' }, true), true);
  assert.equal(followupNeedsRepaint(ready, { ...ready, body: 'Hola Pedro,' }, true), true, 'another memo never shows stale edits');
});
```

- [ ] **Step 2: Run to see them fail**

Run: `node --test shared/ui/ui.test.js`
Expected: FAIL — `./components/followup.js` not found.

- [ ] **Step 3: Create `shared/ui/components/followup.js`**

```js
import { html } from '../html.js';
import { strings } from '../i18n.js';

/**
 * @typedef {Object} FollowupView   Shape returned by GET /api/v1/memos/{id}/followup
 * @property {'generating'|'ready'|'sent'|'unavailable'} status
 * @property {string} [recipientName]
 * @property {string} [to]       email, when known
 * @property {string} [phone]    E.164 only (WhatsApp needs the country code)
 * @property {string} [subject]
 * @property {string} [body]
 * @property {'email'|'whatsapp'} [channel]   set once status is 'sent'
 */

/** Pure: view in, markup out. Node-testable, no DOM. */
export function renderFollowup(view, lang) {
  const t = strings(lang);
  const title = view.recipientName ? t.followupFor(view.recipientName) : t.followupFallback;

  if (view.status === 'generating') {
    return html`<section class="v-paper v-followup" aria-busy="true">
  <p class="v-followup__title">${title}</p>
  <p class="v-followup__pending" role="status">${t.writing}</p>
  <div class="v-followup__skeleton" aria-hidden="true"><span></span><span></span><span></span></div>
</section>`;
  }

  if (view.status === 'sent') {
    return html`<section class="v-paper v-followup is-sent">
  <p class="v-followup__title">${title}</p>
  <p class="v-followup__done" role="status">${view.channel === 'whatsapp' ? t.openedWhatsapp : t.openedMail}</p>
</section>`;
  }

  if (view.status !== 'ready') return html``;

  const primary = view.to ? 'email' : view.phone ? 'whatsapp' : null;
  const pill = (channel) => (primary === channel ? 'v-pill v-pill--primary' : 'v-pill v-pill--ghost');

  return html`<section class="v-paper v-followup">
  <header class="v-followup__head">
    <p class="v-followup__title">${title}</p>
    ${view.to ? html`<span class="v-chip">${view.to}</span>` : ''}
  </header>
  <p class="v-followup__subject" data-role="subject" contenteditable="plaintext-only" spellcheck="true">${view.subject}</p>
  <div class="v-followup__body" data-role="body" contenteditable="plaintext-only" spellcheck="true">${view.body}</div>
  ${view.to ? '' : html`<p class="v-followup__hint">${t.addEmail}</p>`}
  <footer class="v-followup__actions">
    ${view.to ? html`<button type="button" class="${pill('email')}" data-action="send" data-value="email">${t.send}</button>` : ''}
    ${view.phone ? html`<button type="button" class="${pill('whatsapp')}" data-action="send" data-value="whatsapp">${t.whatsapp}</button>` : ''}
    <button type="button" class="v-text-action" data-action="copy">${t.copy}</button>
  </footer>
</section>`;
}

/** While the rep is editing, repaint only when the server says something new: another
 *  status (e.g. sent) or another draft (the host moved on to another memo). */
export function followupNeedsRepaint(prev, next, editing) {
  if (!editing) return true;
  return prev?.status !== next?.status || prev?.subject !== next?.subject || prev?.body !== next?.body;
}
```

- [ ] **Step 4: Create `shared/ui/components/v-followup.js`**

```js
import { VElement, define } from '../v-element.js';
import { followupNeedsRepaint, renderFollowup } from './followup.js';

class VFollowup extends VElement {
  static render(view, element) {
    return renderFollowup(view, element.lang || document.documentElement.lang);
  }

  // A background refetch must never wipe what the rep is typing.
  shouldRepaint(prev, next) {
    return followupNeedsRepaint(prev, next, this.editing);
  }

  /** What the rep will actually send, edits included. */
  get value() {
    return {
      subject: this.querySelector('[data-role="subject"]')?.textContent?.trim() ?? '',
      body: this.querySelector('[data-role="body"]')?.innerText?.trim() ?? '',
    };
  }
}

define('v-followup', VFollowup);
```

- [ ] **Step 5: Create `shared/ui/vocify-ui.css`**

```css
/*
  Shared components (seguimiento, tarjeta de Hoy, brief…) for web, extension and desktop.
  Depends only on the --v-* namespace emitted by scripts/build-tokens.mjs into every
  surface, so it never collides with a surface's own legacy variable names.
  Paper for content, glass only for what floats (the pill lives elsewhere).
*/

/* Custom elements are inline by default; an author display rule would also beat
   the UA's [hidden] { display: none }, so restate it. */
v-followup { display: block; }
v-followup[hidden] { display: none; }

.v-paper {
  background: var(--v-card);
  border: 1px solid var(--v-border);
  border-radius: var(--v-radius-container);
  padding: 16px 18px;
}

.v-followup {
  display: grid;
  gap: 10px;
  color: var(--v-foreground);
}

/* Reserve the ready card's footprint from the first paint: nothing jumps. */
.v-followup:not(.is-sent) {
  min-height: 208px;
  align-content: start;
}

.v-followup__head {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: 12px;
}

.v-followup__title,
.v-followup__hint,
.v-followup__pending,
.v-followup__done {
  margin: 0;
  font-size: 13px;
  color: var(--v-muted-foreground);
}

.v-followup__subject {
  margin: 0;
  font-size: 15px;
  font-weight: 450;
}

.v-followup__body {
  font-size: 14px;
  line-height: 1.55;
  white-space: pre-wrap;
}

.v-followup__subject,
.v-followup__body {
  outline: none;
  border-radius: 6px;
}

.v-followup__subject:focus-visible,
.v-followup__body:focus-visible {
  box-shadow: 0 0 0 2px var(--v-card), 0 0 0 4px color-mix(in srgb, var(--v-beige) 45%, transparent);
}

.v-followup__actions {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 8px;
  margin-top: 4px;
}

.v-chip {
  font-size: 12px;
  color: var(--v-muted-foreground);
  background: var(--v-cream);
  border: 1px solid var(--v-border);
  border-radius: var(--v-radius-pill);
  padding: 2px 10px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  max-width: 60%;
}

.v-pill {
  min-height: 36px;
  padding: 0 16px;
  border: 1px solid transparent;
  border-radius: var(--v-radius-pill);
  font: inherit;
  font-size: 14px;
  cursor: pointer;
  transition: transform 150ms cubic-bezier(0.32, 0.72, 0, 1), background-color 150ms ease;
}

.v-pill:active { transform: scale(0.98); }
.v-pill--primary { background: var(--v-beige); color: var(--v-cream); }
.v-pill--primary:hover { background: var(--v-beige-dark); }
.v-pill--ghost { background: transparent; color: var(--v-foreground); border-color: var(--v-border); }

.v-text-action {
  padding: 8px 4px;
  border: 0;
  background: none;
  font: inherit;
  font-size: 13px;
  color: var(--v-muted-foreground);
  cursor: pointer;
}

.v-text-action:hover { color: var(--v-foreground); }

.v-pill:focus-visible,
.v-text-action:focus-visible {
  outline: 2px solid var(--v-beige);
  outline-offset: 2px;
}

.v-followup__skeleton {
  display: grid;
  gap: 8px;
  margin-top: 6px;
}

.v-followup__skeleton span {
  height: 12px;
  border-radius: 6px;
  background: var(--v-muted);
}

.v-followup__skeleton span:nth-child(2) { width: 88%; }
.v-followup__skeleton span:nth-child(3) { width: 64%; }

@media (prefers-reduced-motion: no-preference) {
  .v-followup__skeleton span { animation: v-breathe 1.6s ease-in-out infinite; }
}

@media (prefers-reduced-motion: reduce) {
  .v-pill { transition: none; }
}

@keyframes v-breathe {
  50% { opacity: 0.55; }
}
```

- [ ] **Step 6: Run the tests**

Run: `node --test shared/ui/ui.test.js`
Expected: 14 tests PASS.

- [ ] **Step 7: Commit**

```bash
git add shared/ui/components shared/ui/vocify-ui.css shared/ui/ui.test.js
git commit -m "feat(ui): <v-followup> — draft, hand-off and honest sent state"
```

---

### Task 5: Sync the kit into the vanilla surfaces

**Files:**
- Create: `scripts/sync-shared.mjs`, `scripts/sync-shared.test.mjs`
- Generate: `chrome-extension/shared/ui/**`, `desktop/renderer/shared/ui/**`
- Modify: `Makefile`

**Interfaces:**
- Produces: `chrome-extension/shared/ui/...`, imported from `popup/` as `../shared/ui/...`, and `desktop/renderer/shared/ui/...`, imported from `renderer/app.js` as `./shared/ui/...`.

- [ ] **Step 1: Write the failing test** — `scripts/sync-shared.test.mjs`

```js
import test from 'node:test';
import assert from 'node:assert/strict';
import { existsSync, mkdirSync, mkdtempSync, readFileSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { syncShared } from './sync-shared.mjs';

function sandbox({ desktop = true } = {}) {
  const root = mkdtempSync(join(tmpdir(), 'shared-'));
  mkdirSync(join(root, 'shared/ui/components'), { recursive: true });
  writeFileSync(join(root, 'shared/ui/html.js'), 'export const a = 1;\n');
  writeFileSync(join(root, 'shared/ui/components/followup.js'), 'export const b = 2;\n');
  writeFileSync(join(root, 'shared/ui/ui.test.js'), '// tests stay home\n');
  mkdirSync(join(root, 'chrome-extension'), { recursive: true });
  if (desktop) mkdirSync(join(root, 'desktop/renderer'), { recursive: true });
  return root;
}

test('copies shared/ui into both vanilla surfaces, without tests', () => {
  const root = sandbox();
  assert.deepEqual(syncShared({ root, env: {} }).synced, ['extension', 'desktop']);
  assert.equal(readFileSync(join(root, 'chrome-extension/shared/ui/components/followup.js'), 'utf8'), 'export const b = 2;\n');
  assert.ok(existsSync(join(root, 'desktop/renderer/shared/ui/html.js')));
  assert.ok(!existsSync(join(root, 'chrome-extension/shared/ui/ui.test.js')));
  assert.deepEqual(syncShared({ root, check: true, env: {} }).stale, []);
});

test('--check catches an edited copy and a stray file', () => {
  const root = sandbox();
  syncShared({ root, env: {} });
  writeFileSync(join(root, 'chrome-extension/shared/ui/html.js'), 'edited');
  writeFileSync(join(root, 'desktop/renderer/shared/ui/stray.js'), 'x');
  assert.deepEqual(syncShared({ root, check: true, env: {} }).stale, ['extension', 'desktop']);
  syncShared({ root, env: {} });
  assert.ok(!existsSync(join(root, 'desktop/renderer/shared/ui/stray.js')), 'resync removes strays');
});

test('a missing desktop is skipped; VOCIFY_DESKTOP_DIR points at a sibling repo', () => {
  const root = sandbox({ desktop: false });
  assert.deepEqual(syncShared({ root, env: {} }).skipped, ['desktop']);
  const sibling = mkdtempSync(join(tmpdir(), 'desktop-'));
  mkdirSync(join(sibling, 'renderer'), { recursive: true });
  assert.ok(syncShared({ root, env: { VOCIFY_DESKTOP_DIR: sibling } }).synced.includes('desktop'));
  assert.ok(existsSync(join(sibling, 'renderer/shared/ui/components/followup.js')));
});
```

- [ ] **Step 2: Run it to see it fail**

Run: `node --test scripts/sync-shared.test.mjs`
Expected: FAIL — module not found.

- [ ] **Step 3: Create `scripts/sync-shared.mjs`**

```js
#!/usr/bin/env node
// A Chrome extension cannot load files outside its own folder, and the desktop
// renderer ships as its own bundle, so shared/ui is copied into both vanilla
// surfaces. Copies are committed; --check fails CI when they drift.
// The web app imports shared/ui directly through a Vite alias and needs no copy.
// Usage: node scripts/sync-shared.mjs [--check]   (VOCIFY_DESKTOP_DIR for a sibling repo)
import { existsSync, mkdirSync, readdirSync, readFileSync, rmSync, statSync, writeFileSync } from 'node:fs';
import { dirname, join, relative, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

const SOURCE = 'shared/ui';

function listFiles(dir) {
  if (!existsSync(dir)) return [];
  const out = [];
  const walk = (current) => {
    for (const name of readdirSync(current)) {
      const full = join(current, name);
      if (statSync(full).isDirectory()) walk(full);
      else out.push(relative(dir, full));
    }
  };
  walk(dir);
  return out.sort();
}

export function destinations(root, env = process.env) {
  const desktop = env.VOCIFY_DESKTOP_DIR ? resolve(root, env.VOCIFY_DESKTOP_DIR) : join(root, 'desktop');
  return [
    { key: 'extension', dir: join(root, 'chrome-extension/shared/ui'), anchor: join(root, 'chrome-extension') },
    { key: 'desktop', dir: join(desktop, 'renderer/shared/ui'), anchor: join(desktop, 'renderer') },
  ];
}

export function syncShared({ root, check = false, env = process.env }) {
  const src = join(root, SOURCE);
  const files = listFiles(src).filter((f) => !f.endsWith('.test.js'));
  const report = { synced: [], stale: [], skipped: [] };
  for (const dest of destinations(root, env)) {
    if (!existsSync(dest.anchor)) {
      report.skipped.push(dest.key);
      continue;
    }
    const present = listFiles(dest.dir);
    const drift =
      present.join('\n') !== files.join('\n') ||
      files.some((f) => readFileSync(join(dest.dir, f), 'utf8') !== readFileSync(join(src, f), 'utf8'));
    if (!drift) continue;
    if (check) {
      report.stale.push(dest.key);
      continue;
    }
    rmSync(dest.dir, { recursive: true, force: true });
    for (const f of files) {
      mkdirSync(dirname(join(dest.dir, f)), { recursive: true });
      writeFileSync(join(dest.dir, f), readFileSync(join(src, f)));
    }
    report.synced.push(dest.key);
  }
  return report;
}

if (process.argv[1] === fileURLToPath(import.meta.url)) {
  const root = resolve(dirname(fileURLToPath(import.meta.url)), '..');
  const check = process.argv.includes('--check');
  const report = syncShared({ root, check });
  for (const key of report.skipped) console.warn(`shared: skipped ${key} (surface not found)`);
  if (check && report.stale.length) {
    console.error(`shared: stale → ${report.stale.join(', ')}. Run: node scripts/sync-shared.mjs`);
    process.exit(1);
  }
  if (!check) console.log(report.synced.length ? `shared: synced ${report.synced.join(', ')}` : 'shared: up to date');
}
```

- [ ] **Step 4: Run the tests and sync**

Run: `node --test scripts/sync-shared.test.mjs && node scripts/sync-shared.mjs`
Expected: 3 tests PASS, then `shared: synced extension, desktop`.

- [ ] **Step 5: Extend `check-generated`**

```make
check-generated:
	node scripts/build-tokens.mjs --check
	node scripts/sync-shared.mjs --check
```

- [ ] **Step 6: Commit**

```bash
git add scripts/sync-shared.mjs scripts/sync-shared.test.mjs chrome-extension/shared desktop/renderer/shared Makefile
git commit -m "build(ui): sync the shared kit into extension and desktop, guarded in CI"
```

---

### Task 6: Migration — follow-up draft and voice samples

**Files:**
- Create: `backend/migrations/037_memos_followup.sql` (use the next free number if 037 is taken, and update this plan's references)
- Modify: `backend/full_reset.sql`, `docs/DATABASE_SCHEMA.md`

- [ ] **Step 1: Write the migration**

```sql
-- Follow-up email draft per memo (copilot spine, slice 1) and the rep's voice samples.
ALTER TABLE memos
  ADD COLUMN IF NOT EXISTS followup JSONB,
  ADD COLUMN IF NOT EXISTS followup_run_started_at TIMESTAMPTZ;

COMMENT ON COLUMN memos.followup IS
  'Draft lifecycle {status: generating|ready|sent|unavailable, subject, body, final_subject, final_body, edit_ratio, no_edit, channel, run_id, prompt_version, ...}.';
COMMENT ON COLUMN memos.followup_run_started_at IS
  'Non-null while a follow-up generation holds the single-flight lease.';

ALTER TABLE user_profiles
  ADD COLUMN IF NOT EXISTS writing_samples JSONB NOT NULL DEFAULT '[]'::jsonb;

COMMENT ON COLUMN user_profiles.writing_samples IS
  'Last follow-ups the rep reshaped before sending (max 5): few-shot voice for drafts.';
```

- [ ] **Step 2: Mirror it in `backend/full_reset.sql`**

Add the three columns to the `memos` and `user_profiles` definitions. `docs/DATABASE_SCHEMA.md` states that both files describe the schema.

- [ ] **Step 3: Document it**

Add one line per column to `docs/DATABASE_SCHEMA.md`.

- [ ] **Step 4: Commit**

```bash
git add backend/migrations/037_memos_followup.sql backend/full_reset.sql docs/DATABASE_SCHEMA.md
git commit -m "feat(db): memos.followup lease + user_profiles.writing_samples"
```

**OUTSTANDING MANUAL STEP:** apply the migration to each database. Until it is applied, generation fails closed and every card renders nothing.

---

### Task 7: Follow-up logic (pure)

**Files:**
- Create: `backend/app/services/followup_logic.py`, `backend/tests/test_followup_logic.py`

**Interfaces:**
- Produces: `is_eligible`, `should_generate`, `build_messages`, `parse_draft`, `edit_ratio`, `is_no_edit`, `next_voice_samples`, `apply_action`, `followup_view` and `PROMPT_VERSION = "followup_v1"`.

- [ ] **Step 1: Write the failing test** — `backend/tests/test_followup_logic.py`

```python
import json
import unittest
from datetime import datetime, timedelta, timezone

from app.services.followup_logic import (
    apply_action,
    build_messages,
    edit_ratio,
    followup_view,
    is_eligible,
    is_no_edit,
    next_voice_samples,
    parse_draft,
    should_generate,
)

NOW = datetime(2026, 9, 21, 10, 0, tzinfo=timezone.utc)
EXTRACTION = {"summary": "Resumen", "contactName": "Marina", "contactEmail": "marina@tenes.io", "contactPhone": "+34 600 111 222"}


class Eligibility(unittest.TestCase):
    def test_real_conversations_only(self):
        memo = {"transcript": "Marina: hola", "extraction": EXTRACTION, "screening_outcome": None}
        self.assertTrue(is_eligible(memo))
        self.assertFalse(is_eligible({**memo, "screening_outcome": "voicemail"}))
        self.assertFalse(is_eligible({**memo, "transcript": "  "}))
        self.assertFalse(is_eligible({**memo, "extraction": {"summary": ""}}))

    def test_single_flight_decision(self):
        self.assertTrue(should_generate(None, NOW))
        fresh = {"status": "generating", "started_at": (NOW - timedelta(seconds=30)).isoformat()}
        stale = {"status": "generating", "started_at": (NOW - timedelta(minutes=5)).isoformat()}
        self.assertFalse(should_generate(fresh, NOW))
        self.assertTrue(should_generate(stale, NOW))
        for status in ("ready", "sent", "unavailable"):
            self.assertFalse(should_generate({"status": status}, NOW))


class Drafting(unittest.TestCase):
    def test_parse_draft(self):
        self.assertEqual(parse_draft({"subject": "  Caso   de logística ", "body": " Hola ", "language": "es"}),
                         {"subject": "Caso de logística", "body": "Hola", "language": "es"})
        self.assertIsNone(parse_draft({"subject": "x", "body": " "}))
        self.assertIsNone(parse_draft("not json"))
        self.assertEqual(len(parse_draft({"subject": "s" * 500, "body": "b"})["subject"]), 160)

    def test_messages_carry_context_and_last_three_samples(self):
        msgs = build_messages(system_prompt="SYS", transcript="Marina: hola", summary="Resumen", next_steps=["Enviar caso"],
                              contact_name="Marina", rep_name="Lucía", voice_samples=["1", "2", "3", "4"])
        self.assertEqual(msgs[0], {"role": "system", "content": "SYS"})
        ctx = json.loads(msgs[1]["content"])
        self.assertEqual(ctx["voice_samples"], ["2", "3", "4"])
        self.assertIn("Lucía", msgs[1]["content"], "accents survive (ensure_ascii=False)")


class Metrics(unittest.TestCase):
    def test_edit_ratio_and_no_edit(self):
        draft = "Hola Marina, gracias por el rato de hoy. Te paso el caso de logística."
        self.assertEqual(edit_ratio(draft, draft.replace(" ", "  ")), 0.0)
        self.assertTrue(is_no_edit(edit_ratio(draft, draft.replace("rato", "ratoo"))))
        self.assertGreater(edit_ratio(draft, "Marina, adjunto propuesta. Un saludo."), 0.5)

    def test_voice_samples_only_learn_from_real_edits(self):
        self.assertEqual(next_voice_samples(["a"], "body", 0.0), ["a"])
        self.assertEqual(next_voice_samples(["a"], " mine ", 0.3), ["a", "mine"])
        self.assertEqual(next_voice_samples([str(i) for i in range(5)], "new", 0.3), ["1", "2", "3", "4", "new"])

    def test_apply_action_records_hand_off_and_edit_ratio(self):
        current = {"status": "ready", "subject": "Caso", "body": "Hola Marina, te paso el caso."}
        sent = apply_action(current, action="sent", channel="email", subject="", body="Hola Marina, te paso el caso.", now=NOW)
        self.assertEqual((sent["status"], sent["channel"], sent["final_subject"], sent["no_edit"]), ("sent", "email", "Caso", True))
        copied = apply_action(current, action="copied", channel="email", subject="Caso", body="Otra cosa distinta.", now=NOW)
        self.assertEqual(copied["status"], "ready", "copying is not sending")
        self.assertFalse(copied["no_edit"])
        with self.assertRaises(ValueError):
            apply_action(current, action="deleted", channel="email", subject="", body="x", now=NOW)


class View(unittest.TestCase):
    def test_view_per_status(self):
        memo = {"extraction": EXTRACTION}
        self.assertEqual(followup_view(memo), {"status": "unavailable", "recipientName": "Marina"})
        self.assertEqual(followup_view(memo, scheduled=True)["status"], "generating")
        ready = followup_view({**memo, "followup": {"status": "ready", "subject": "S", "body": "B"}})
        self.assertEqual((ready["to"], ready["phone"], ready["subject"]), ("marina@tenes.io", "+34600111222", "S"))
        sent = followup_view({**memo, "followup": {"status": "sent", "subject": "S", "body": "B", "final_body": "B2", "channel": "whatsapp"}})
        self.assertEqual((sent["body"], sent["channel"]), ("B2", "whatsapp"))

    def test_phone_without_country_code_is_not_offered_for_whatsapp(self):
        view = followup_view({"extraction": {**EXTRACTION, "contactPhone": "600111222"}, "followup": {"status": "ready", "subject": "S", "body": "B"}})
        self.assertNotIn("phone", view)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run it to see it fail**

Run: `cd backend && python -m pytest tests/test_followup_logic.py -q`
Expected: FAIL — `ModuleNotFoundError: app.services.followup_logic`.

- [ ] **Step 3: Create `backend/app/services/followup_logic.py`**

```python
"""Pure pieces of the follow-up draft: decisions, parsing, metrics and the view. No I/O."""
from __future__ import annotations

import difflib
import json
from datetime import datetime, timedelta
from typing import Literal, Optional

PROMPT_VERSION = "followup_v1"
STALE_GENERATING = timedelta(minutes=2)
MAX_SUBJECT = 160
MAX_BODY = 4000
NO_EDIT_THRESHOLD = 0.02      # a fixed typo still counts as "sent as drafted"
VOICE_SAMPLE_MIN_EDIT = 0.05  # only bodies the rep actually reshaped teach us their voice
MAX_VOICE_SAMPLES = 5
SKIPPED_SCREENING = frozenset({"voicemail", "no_response"})


def is_eligible(memo: dict) -> bool:
    """A real conversation with an extraction. Voicemail and no-answer never get a draft."""
    if (memo.get("screening_outcome") or "") in SKIPPED_SCREENING:
        return False
    if not (memo.get("transcript") or "").strip():
        return False
    return bool(((memo.get("extraction") or {}).get("summary") or "").strip())


def should_generate(current: Optional[dict], now: datetime) -> bool:
    """Whether to try. The DB lease enforces single-flight; this avoids pointless writes."""
    if not current:
        return True
    if current.get("status") == "generating":
        started = current.get("started_at")
        return not started or now - datetime.fromisoformat(started) > STALE_GENERATING
    return False  # ready, sent, unavailable: never regenerate behind the rep's back


def build_messages(*, system_prompt: str, transcript: str, summary: str, next_steps: list[str],
                   contact_name: Optional[str], rep_name: Optional[str], voice_samples: list[str]) -> list[dict]:
    context = {
        "rep_name": rep_name or "",
        "contact_name": contact_name or "",
        "summary": summary or "",
        "next_steps": next_steps or [],
        "voice_samples": voice_samples[-3:],
        "transcript": transcript,
    }
    return [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": json.dumps(context, ensure_ascii=False)},
    ]


def parse_draft(payload: object) -> Optional[dict]:
    if not isinstance(payload, dict):
        return None
    subject = " ".join(str(payload.get("subject") or "").split())
    body = str(payload.get("body") or "").strip()
    if not subject or not body:
        return None
    language = str(payload.get("language") or "").strip()[:5] or None
    return {"subject": subject[:MAX_SUBJECT], "body": body[:MAX_BODY], "language": language}


def edit_ratio(draft: str, final: str) -> float:
    """0.0 = sent untouched, 1.0 = rewritten. Whitespace-insensitive."""
    a, b = " ".join((draft or "").split()), " ".join((final or "").split())
    if a == b:
        return 0.0
    return round(1 - difflib.SequenceMatcher(None, a, b).ratio(), 3)


def is_no_edit(ratio: float) -> bool:
    return ratio <= NO_EDIT_THRESHOLD


def next_voice_samples(samples: list[str], final_body: str, ratio: float) -> list[str]:
    """Unedited drafts are our voice, not theirs; only reshaped bodies are kept."""
    if ratio < VOICE_SAMPLE_MIN_EDIT or not final_body.strip():
        return samples
    return (samples + [final_body.strip()])[-MAX_VOICE_SAMPLES:]


def apply_action(current: dict, *, action: Literal["sent", "copied"], channel: str,
                 subject: str, body: str, now: datetime) -> dict:
    ratio = edit_ratio(current.get("body") or "", body)
    updated = {
        **current,
        "final_subject": subject.strip() or current.get("subject") or "",
        "final_body": body.strip(),
        "edit_ratio": ratio,
        "no_edit": is_no_edit(ratio),
    }
    if action == "sent":
        updated.update(status="sent", channel=channel, sent_at=now.isoformat())
    elif action == "copied":
        updated["copied_at"] = now.isoformat()
    else:
        raise ValueError(f"unknown follow-up action {action!r}")
    return updated


def followup_view(memo: dict, *, scheduled: bool = False) -> dict:
    """What every surface renders — the FollowupView of shared/ui/components/followup.js."""
    current = memo.get("followup") or {}
    extraction = memo.get("extraction") or {}
    status = current.get("status") or ("generating" if scheduled else "unavailable")
    view: dict = {"status": status, "recipientName": extraction.get("contactName") or None}
    if status in ("ready", "sent"):
        view["subject"] = current.get("final_subject") or current.get("subject") or ""
        view["body"] = current.get("final_body") or current.get("body") or ""
        email = (extraction.get("contactEmail") or "").strip()
        phone = (extraction.get("contactPhone") or "").replace(" ", "").strip()
        if "@" in email:
            view["to"] = email
        if phone.startswith("+"):
            view["phone"] = phone  # WhatsApp needs the country code; never guess it
    if status == "sent":
        view["channel"] = current.get("channel") or "email"
    return view
```

- [ ] **Step 4: Run the tests**

Run: `cd backend && python -m pytest tests/test_followup_logic.py -q`
Expected: 9 passed.

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/followup_logic.py backend/tests/test_followup_logic.py
git commit -m "feat(followup): pure draft logic — eligibility, parsing, edit ratio, view"
```

---

### Task 8: Follow-up service — prompt, lease, generation

**Files:**
- Create: `backend/app/prompts/followup_v1.md`, `backend/app/services/followup.py`, `backend/tests/test_followup_service.py`
- Modify: `backend/app/config.py`

**Interfaces:**
- Consumes: Task 7; `LLMClient.chat_json`; the Task 6 columns.
- Produces:
  - `async ensure_followup(supabase, memo_id, *, llm=None)`: idempotent, never raises.
  - `schedule_followup(supabase, memo_id, *, llm=None) -> bool`: fire-and-forget. It returns whether a run was started: never with the kill switch off, never without a running loop. Task 10's GET relies on that return value so it never promises a draft that will not come.

- [ ] **Step 1: Add the settings** — `backend/app/config.py`, next to the other feature flags in `Settings`

```python
    # Follow-up drafts (copilot spine, slice 1)
    FOLLOWUP_ENABLED: bool = True
    FOLLOWUP_MODEL: Optional[str] = None  # None = the LLM router's default model
```

- [ ] **Step 2: Write the prompt** — `backend/app/prompts/followup_v1.md`

```markdown
You write the follow-up email a sales rep sends right after a call or a meeting.

The user message is a JSON object with: rep_name, contact_name, summary, next_steps,
voice_samples and the full transcript.

Write as the rep, in first person, to the contact.

- Use the language of the conversation. For Spanish, write Spanish from Spain unless the
  transcript clearly shows another variety.
- Say only what was actually agreed: the concrete next steps, dates and materials that
  appear in the transcript or in next_steps. Nothing else.
- Never invent prices, dates, attachments, names, links or commitments that are not in
  the input. If a next step is vague in the input, keep it vague.
- 60 to 120 words. Short paragraphs. Use a list only when there are three or more next
  steps.
- No filler openers ("Espero que estés bien", "Como hablamos antes") and no closing
  clichés. Sign off with the rep's first name only.
- If voice_samples are present, match their greeting, sign-off, tone and formality
  (tú or usted). Never copy their content.
- Subject: under 60 characters, specific to this conversation, for example
  "Caso de logística y siguiente paso". Never "Follow-up" or "Seguimiento" alone.

Return only this JSON, nothing before or after it:
{"subject": "...", "body": "...", "language": "es"}
```

- [ ] **Step 3: Write the failing test** — `backend/tests/test_followup_service.py`

```python
import asyncio
import unittest
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

from app.config import settings
from app.services import followup as svc


class FakeQuery:
    """supabase-py chain with the filters this service uses, including PostgREST's quirk
    of re-applying PATCH filters to RETURNING (what forces the confirm-by-PK read)."""

    def __init__(self, rows: list[dict]):
        self.rows, self.filters, self.ors, self.patch, self.n = rows, [], None, None, None

    def select(self, *_a, **_k):
        return self

    def eq(self, column, value):
        self.filters.append((column, value))
        return self

    def or_(self, expression):
        self.ors = expression
        return self

    def limit(self, n, *_a, **_k):
        self.n = n
        return self

    def update(self, patch):
        self.patch = patch
        return self

    @staticmethod
    def _value(row, column):
        if "->>" in column:
            base, key = column.split("->>", 1)
            value = (row.get(base) or {}).get(key)
            return None if value is None else str(value)
        return row.get(column)

    def _condition(self, row, cond):
        column, op, value = cond.split(".", 2)
        current = self._value(row, column)
        if op == "is" and value == "null":
            return current is None
        if op == "lt":
            return current is not None and str(current) < value
        raise NotImplementedError(cond)

    def _match(self, row):
        if any(self._value(row, c) != v for c, v in self.filters):
            return False
        return not self.ors or any(self._condition(row, c) for c in self.ors.split(","))

    def execute(self):
        matched = [r for r in self.rows if self._match(r)]
        if self.patch is not None:
            for row in matched:
                row.update(self.patch)
            return SimpleNamespace(data=[dict(r) for r in matched if self._match(r)])
        return SimpleNamespace(data=[dict(r) for r in matched[: self.n or None]])


class FakeClient:
    def __init__(self, tables):
        self.tables = tables

    def table(self, name):
        return FakeQuery(self.tables[name])


class FakeLLM:
    def __init__(self, payload=None, error=None):
        self.payload = payload or {"subject": "Caso de logística", "body": "Hola Marina, te paso el caso.", "language": "es"}
        self.error, self.calls = error, 0

    async def chat_json(self, messages, **kwargs):
        self.calls += 1
        self.messages, self.kwargs = messages, kwargs
        await asyncio.sleep(0)  # yield, so concurrent callers really overlap
        if self.error:
            raise self.error
        return self.payload


def memo_row(**overrides):
    return {
        "id": "m1", "user_id": "u1", "transcript": "Marina: me interesa el caso.",
        "extraction": {"summary": "Quiere el caso de logística", "nextSteps": ["Enviar caso"], "contactName": "Marina"},
        "screening_outcome": None, "followup": None, "followup_run_started_at": None, **overrides,
    }


def client_for(memo):
    return FakeClient({"memos": [memo], "user_profiles": [{"id": "u1", "full_name": "Lucía Pérez", "writing_samples": ["Hola X, te paso lo que hablamos."]}]})


class EnsureFollowup(unittest.TestCase):
    def setUp(self):
        settings.FOLLOWUP_ENABLED = True
        svc._live.clear()

    def tearDown(self):
        settings.FOLLOWUP_ENABLED = True  # never leak the kill switch into other test modules

    def test_drafts_once_and_releases_the_lease(self):
        memo, llm = memo_row(), FakeLLM()
        client = client_for(memo)
        asyncio.run(svc.ensure_followup(client, "m1", llm=llm))
        self.assertEqual((memo["followup"]["status"], memo["followup"]["subject"]), ("ready", "Caso de logística"))
        self.assertIsNone(memo["followup_run_started_at"])
        self.assertIn("Lucía Pérez", llm.messages[1]["content"])
        self.assertEqual(llm.kwargs["timeout"], svc.LLM_TIMEOUT_S)
        asyncio.run(svc.ensure_followup(client, "m1", llm=llm))
        self.assertEqual(llm.calls, 1, "a ready draft is never regenerated")

    def test_concurrent_calls_generate_once(self):
        memo, llm = memo_row(), FakeLLM()
        client = client_for(memo)

        async def both():
            await asyncio.gather(svc.ensure_followup(client, "m1", llm=llm), svc.ensure_followup(client, "m1", llm=llm))

        asyncio.run(both())
        self.assertEqual(llm.calls, 1)

    def test_respects_a_fresh_run_elsewhere_and_reclaims_a_stale_one(self):
        now = datetime.now(timezone.utc)
        fresh = (now - timedelta(seconds=20)).isoformat()
        llm = FakeLLM()
        busy = memo_row(followup={"status": "generating", "started_at": fresh, "run_id": "other"}, followup_run_started_at=fresh)
        asyncio.run(svc.ensure_followup(client_for(busy), "m1", llm=llm))
        self.assertEqual(llm.calls, 0)

        stale = (now - timedelta(minutes=5)).isoformat()
        dead = memo_row(followup={"status": "generating", "started_at": stale, "run_id": "dead"}, followup_run_started_at=stale)
        asyncio.run(svc.ensure_followup(client_for(dead), "m1", llm=llm))
        self.assertEqual((llm.calls, dead["followup"]["status"]), (1, "ready"))

    def test_voicemail_and_kill_switch_do_nothing(self):
        llm = FakeLLM()
        asyncio.run(svc.ensure_followup(client_for(memo_row(screening_outcome="voicemail")), "m1", llm=llm))
        settings.FOLLOWUP_ENABLED = False
        asyncio.run(svc.ensure_followup(client_for(memo_row()), "m1", llm=llm))

        async def schedule():
            return svc.schedule_followup(client_for(memo_row()), "m1", llm=llm)

        self.assertFalse(asyncio.run(schedule()), "switched off, the GET must not promise a draft")
        self.assertEqual(llm.calls, 0)

    def test_failures_mark_unavailable_and_never_raise(self):
        errored = memo_row()
        asyncio.run(svc.ensure_followup(client_for(errored), "m1", llm=FakeLLM(error=TimeoutError())))
        self.assertEqual((errored["followup"]["status"], errored["followup"]["reason"]), ("unavailable", "error"))
        empty = memo_row()
        asyncio.run(svc.ensure_followup(client_for(empty), "m1", llm=FakeLLM(payload={"subject": "", "body": ""})))
        self.assertEqual((empty["followup"]["status"], empty["followup"]["reason"]), ("unavailable", "empty_draft"))
        self.assertIsNone(empty["followup_run_started_at"])

    def test_schedule_is_a_noop_without_a_loop_and_completes_inside_one(self):
        memo, llm = memo_row(), FakeLLM()
        client = client_for(memo)
        self.assertFalse(svc.schedule_followup(client, "m1", llm=llm))  # no running loop: nothing started, no raise
        self.assertIsNone(memo["followup"])

        async def scheduled():
            self.assertTrue(svc.schedule_followup(client, "m1", llm=llm))
            await asyncio.gather(*list(svc._tasks))

        asyncio.run(scheduled())
        self.assertEqual(memo["followup"]["status"], "ready")


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 4: Run it to see it fail**

Run: `cd backend && python -m pytest tests/test_followup_service.py -q`
Expected: FAIL — `ModuleNotFoundError: app.services.followup`.

- [ ] **Step 5: Create `backend/app/services/followup.py`**

```python
"""Draft the follow-up email as soon as a memo's extraction is ready.

Runs in the background, once per memo, and never blocks or fails the memo pipeline.
Single-flight mirrors pipeline_lease.py: an in-process guard for same-instant bursts
plus a DB lease (followup_run_started_at) that survives restarts.
"""
from __future__ import annotations

import asyncio
import logging
import threading
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Optional

from app.config import settings
from app.services.followup_logic import (
    PROMPT_VERSION,
    build_messages,
    is_eligible,
    parse_draft,
    should_generate,
)

logger = logging.getLogger(__name__)

PROMPT_PATH = Path(__file__).resolve().parents[1] / "prompts" / f"{PROMPT_VERSION}.md"
LEASE = timedelta(minutes=2)
LLM_TIMEOUT_S = 25.0
MEMO_COLUMNS = "id,user_id,transcript,extraction,screening_outcome,followup"

_guard = threading.Lock()
_live: set[str] = set()
_tasks: set[asyncio.Task] = set()  # hold references so fire-and-forget tasks are not garbage-collected


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _first(result: Any) -> Optional[dict]:
    rows = getattr(result, "data", None) or []
    return rows[0] if rows and isinstance(rows[0], dict) else None


def _acquire(supabase: Any, memo_id: str, run_id: str, now: datetime) -> bool:
    started = now.isoformat()
    cutoff = (now - LEASE).isoformat()
    q = (
        supabase.table("memos")
        .update({
            "followup": {"status": "generating", "started_at": started, "run_id": run_id,
                         "prompt_version": PROMPT_VERSION},
            "followup_run_started_at": started,
        })
        .eq("id", memo_id)
    )
    if hasattr(q, "or_"):  # same guard as pipeline_lease.py; without it: in-process single-flight only
        q = q.or_(f"followup.is.null,followup_run_started_at.lt.{cutoff}")
    q.execute()
    # PostgREST re-applies the PATCH filter to RETURNING (see pipeline_lease.py), so an
    # empty result does not mean we lost. Confirm ownership by primary key.
    row = _first(supabase.table("memos").select("followup").eq("id", memo_id).limit(1).execute())
    return bool(row) and (row.get("followup") or {}).get("run_id") == run_id


def _finish(supabase: Any, memo_id: str, run_id: str, followup: dict) -> None:
    (
        supabase.table("memos")
        .update({"followup": followup, "followup_run_started_at": None})
        .eq("id", memo_id)
        .eq("followup->>run_id", run_id)  # a reclaimed lease is not ours to overwrite
        .execute()
    )


async def _draft(supabase: Any, memo: dict, llm: Any) -> Optional[dict]:
    profile = _first(
        supabase.table("user_profiles").select("full_name,writing_samples")
        .eq("id", memo["user_id"]).limit(1).execute()
    ) or {}
    extraction = memo.get("extraction") or {}
    messages = build_messages(
        system_prompt=PROMPT_PATH.read_text(encoding="utf-8"),
        transcript=memo.get("transcript") or "",
        summary=extraction.get("summary") or "",
        next_steps=list(extraction.get("nextSteps") or []),
        contact_name=extraction.get("contactName"),
        rep_name=profile.get("full_name"),
        voice_samples=list(profile.get("writing_samples") or []),
    )
    payload = await llm.chat_json(messages, model=settings.FOLLOWUP_MODEL, temperature=0.4, timeout=LLM_TIMEOUT_S)
    return parse_draft(payload)


async def ensure_followup(supabase: Any, memo_id: str, *, llm: Any = None) -> None:
    """Idempotent. Safe to call from every path that completes an extraction."""
    if not settings.FOLLOWUP_ENABLED:
        return
    memo_id = str(memo_id)
    with _guard:
        if memo_id in _live:
            return
        _live.add(memo_id)
    run_id = str(uuid.uuid4())
    acquired = False
    try:
        memo = _first(supabase.table("memos").select(MEMO_COLUMNS).eq("id", memo_id).limit(1).execute())
        now = _utc_now()
        if not memo or not is_eligible(memo) or not should_generate(memo.get("followup"), now):
            return
        acquired = _acquire(supabase, memo_id, run_id, now)
        if not acquired:
            return
        if llm is None:
            from app.services.llm import LLMClient

            llm = LLMClient()
        draft = await _draft(supabase, memo, llm)
        base = {"run_id": run_id, "prompt_version": PROMPT_VERSION, "started_at": now.isoformat()}
        if draft:
            _finish(supabase, memo_id, run_id, {**base, "status": "ready", "ready_at": _utc_now().isoformat(), **draft})
        else:
            _finish(supabase, memo_id, run_id, {**base, "status": "unavailable", "reason": "empty_draft"})
    except Exception:
        logger.exception("followup: generation failed for memo %s", memo_id)
        if acquired:
            try:
                _finish(supabase, memo_id, run_id, {"run_id": run_id, "prompt_version": PROMPT_VERSION,
                                                     "status": "unavailable", "reason": "error"})
            except Exception:
                logger.exception("followup: could not mark memo %s unavailable", memo_id)
    finally:
        with _guard:
            _live.discard(memo_id)


def schedule_followup(supabase: Any, memo_id: str, *, llm: Any = None) -> bool:
    """Fire-and-forget from any path that just completed an extraction. Same pattern as
    schedule_transcript_polish.

    Returns whether a run was started: never with the kill switch off, and never outside
    an event loop (GET /memos/{id}/followup is then the safety net).
    """
    if not settings.FOLLOWUP_ENABLED:
        return False
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        return False
    task = loop.create_task(ensure_followup(supabase, str(memo_id), llm=llm))
    _tasks.add(task)
    task.add_done_callback(_tasks.discard)
    return True
```

- [ ] **Step 6: Run the tests**

Run: `cd backend && python -m pytest tests/test_followup_service.py tests/test_followup_logic.py -q`
Expected: 15 passed. The intentional-failure test prints a `TimeoutError` traceback from `logger.exception`; that is expected output.

- [ ] **Step 7: Commit**

```bash
git add backend/app/config.py backend/app/prompts/followup_v1.md backend/app/services/followup.py backend/tests/test_followup_service.py
git commit -m "feat(followup): background draft with single-flight lease and versioned prompt"
```

---

### Task 9: Schedule the draft where extractions complete

**Files:**
- Modify: `backend/app/api/memos.py`, `backend/app/services/whatsapp/processor.py`

**Interfaces:**
- Consumes: `schedule_followup(supabase, memo_id)` (Task 8).

- [ ] **Step 1: Pipeline and re-extract** — `backend/app/api/memos.py`

Add the import next to the other module-level `from app.services…` imports. `app.services.followup` only imports `app.config` and `followup_logic`, so there is no cycle:
```python
from app.services.followup import schedule_followup
```

Right after the pipeline write (≈288–295). It must come after this write: `schedule_transcript_polish` at `:371` runs before extraction, so it is not the anchor here.
```python
        update_memo_row(
            supabase,
            memo_id,
            extraction_complete_update(
                extraction.model_dump(),
                datetime.utcnow().isoformat(),
            ),
        )
        schedule_followup(supabase, memo_id)
```

In the re-extract, next to the existing `schedule_transcript_polish(...)` that follows the write (≈2011):
```python
    schedule_transcript_polish(str(memo_id), user_id, transcript, supabase, memo_data=memo_data)
    schedule_followup(supabase, str(memo_id))
```

A draft that already exists is never regenerated by a re-extract: `should_generate` returns `False` for ready and sent drafts. This is intended.

- [ ] **Step 2: WhatsApp voice notes** — `backend/app/services/whatsapp/processor.py`

Add the same module-level import. After the insert, next to the existing scheduler (≈2220), where `memo_id = r.data[0]["id"]`:
```python
        schedule_transcript_polish(str(memo_id), user_id, transcript, supabase)
        schedule_followup(supabase, str(memo_id))
```

Do not schedule on the idempotent-race branch (≈2195–2212): the insert that won the race already did.

- [ ] **Step 3: Do not touch** `backend/app/services/telephony/call_processor.py:328`. It is the voicemail / no-conversation path.

- [ ] **Step 4: Verify**

Run: `grep -rn "schedule_followup(" backend/app | grep -v "def schedule_followup"`
Expected: exactly 3 call sites.

Run: `make test`
Expected: the full backend suite PASSES.

- [ ] **Step 5: Commit**

```bash
git add backend/app/api/memos.py backend/app/services/whatsapp/processor.py
git commit -m "feat(followup): draft after pipeline, re-extract and WhatsApp extractions"
```

---

### Task 10: API — read the draft, record the hand-off

**Files:**
- Create: `backend/app/models/followup.py`, `backend/app/api/followup.py`
- Modify: `backend/app/api/router.py`

**Interfaces:**
- Consumes: `_require_readable_memo` (`memos.py:59`); `schedule_followup(...) -> bool` (Task 8).
- Produces:
  - `GET /api/v1/memos/{memo_id}/followup` → `FollowupView`.
    - Anyone who can read the memo can read the draft, so a manager sees their reps' drafts.
    - When the memo is eligible and has no draft, the GET schedules one and answers `generating`.
    - With the kill switch off, it answers `unavailable`.
  - `POST /api/v1/memos/{memo_id}/followup` with `{action: 'sent'|'copied', channel: 'email'|'whatsapp', subject, body}` → `FollowupView`.
    - Only the memo's author may call it (403 otherwise): a manager never hands off a rep's email from their own mailbox.
    - It returns 409 unless the draft is ready or sent.

- [ ] **Step 1: Create `backend/app/models/followup.py`**

```python
"""Request model for follow-up hand-off actions."""
from typing import Literal

from pydantic import BaseModel, Field


class FollowupActionRequest(BaseModel):
    action: Literal["sent", "copied"]
    channel: Literal["email", "whatsapp"] = "email"
    subject: str = Field("", max_length=300)
    body: str = Field(..., min_length=1, max_length=8000)
```

- [ ] **Step 2: Create `backend/app/api/followup.py`**

Visibility reuses `_require_readable_memo` from `memos.py`, as `services/recovery.py` already does with that module's helpers. There is no second copy of the rule.

```python
"""Follow-up draft per memo: read (polled by every surface) and record the hand-off."""
from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from supabase import Client

from app.api.memos import _require_readable_memo
from app.deps import get_supabase, get_user_id
from app.models.followup import FollowupActionRequest
from app.services.followup import schedule_followup
from app.services.followup_logic import (
    apply_action,
    followup_view,
    is_eligible,
    next_voice_samples,
    should_generate,
)

router = APIRouter(prefix="/api/v1/memos", tags=["followup"])


@router.get("/{memo_id}/followup")
async def get_followup(
    memo_id: UUID,
    supabase: Client = Depends(get_supabase),
    user_id: str = Depends(get_user_id),
) -> dict:
    memo = _require_readable_memo(supabase, str(memo_id), user_id)
    # Safety net for any path that completed an extraction without scheduling.
    scheduled = (
        is_eligible(memo)
        and should_generate(memo.get("followup"), datetime.now(timezone.utc))
        and schedule_followup(supabase, str(memo_id))
    )
    return followup_view(memo, scheduled=scheduled)


@router.post("/{memo_id}/followup")
async def record_followup_action(
    memo_id: UUID,
    payload: FollowupActionRequest,
    supabase: Client = Depends(get_supabase),
    user_id: str = Depends(get_user_id),
) -> dict:
    memo = _require_readable_memo(supabase, str(memo_id), user_id)
    if str(memo.get("user_id") or "") != user_id:
        # Managers can read a rep's draft; only the rep sends it, from their own mailbox.
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Only the memo's author can send its follow-up")
    current = memo.get("followup") or {}
    if current.get("status") not in ("ready", "sent"):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Follow-up is not ready")
    updated = apply_action(
        current,
        action=payload.action,
        channel=payload.channel,
        subject=payload.subject,
        body=payload.body,
        now=datetime.now(timezone.utc),
    )
    supabase.table("memos").update({"followup": updated}).eq("id", str(memo_id)).execute()

    rows = supabase.table("user_profiles").select("writing_samples").eq("id", user_id).limit(1).execute().data
    samples = list(((rows or [{}])[0]).get("writing_samples") or [])
    learned = next_voice_samples(samples, payload.body, updated["edit_ratio"])
    if learned != samples:
        supabase.table("user_profiles").update({"writing_samples": learned}).eq("id", user_id).execute()

    return followup_view({**memo, "followup": updated})
```

- [ ] **Step 3: Register the router** — `backend/app/api/router.py`

Add `followup` to the `from app.api import (...)` list, and after `api_router.include_router(memos.router)` add:
```python
api_router.include_router(followup.router)
```

- [ ] **Step 4: Verify**

Run: `cd backend && python -c "from app.main import app; print([p for p in app.openapi()['paths'] if p.endswith('/followup')])"`
Expected: `['/api/v1/memos/{memo_id}/followup']`. Use `app.openapi()`, because this FastAPI version does not flatten included routers into `app.routes`.

Run: `make test`
Expected: PASS.

Route-level tests are not added, for the same reason as `.superpowers/sdd/2026-08-26-vocify-outbound-calling/progress.md` Task 3: `backend/tests` has no TestClient harness, and the logic lives in the tested pure functions.

- [ ] **Step 5: Commit**

```bash
git add backend/app/models/followup.py backend/app/api/followup.py backend/app/api/router.py
git commit -m "feat(followup): GET draft view (with safety net) and POST hand-off"
```

---

### Task 11: Extension — the draft on the review screen

**Files:**
- Modify: `chrome-extension/popup/index.html`, `chrome-extension/popup/popup.js`

**Interfaces:**
- Consumes: Task 10's endpoints through the existing `api.get` / `api.post` (`lib/api.js:219–220`, so no new API methods), and the `<v-followup>` from Task 5 (`../shared/ui/...`).

- [ ] **Step 1: Markup** — `chrome-extension/popup/index.html`

Add after the `work.css` link:
```html
  <link rel="stylesheet" href="../shared/ui/vocify-ui.css">
```

Add inside `#screen-review`, directly after the `.header-review` block (≈188), before `#review-loading-section`. The draft sits on top of the review and keeps writing while the preview loads:
```html
      <v-followup id="review-followup" hidden></v-followup>
```

- [ ] **Step 2: Wiring** — `chrome-extension/popup/popup.js`

Add with the other imports:
```js
import '../shared/ui/components/v-followup.js';
import { composeTarget } from '../shared/ui/compose.js';
```

Add near the other review helpers:
```js
const followupEl = document.getElementById('review-followup');
const FOLLOWUP_POLL_MS = 1500;
const FOLLOWUP_MAX_POLLS = 25;
let followupTimer = null;

function stopFollowup() {
  clearTimeout(followupTimer);
  followupTimer = null;
  followupEl.hidden = true;
  followupEl.data = null;
  delete followupEl.dataset.memoId;
}

async function loadFollowup(memoId, attempt = 0) {
  clearTimeout(followupTimer);
  if (!isCurrentReviewMemo(memoId)) return;
  let view;
  try {
    view = await api.get(`/memos/${memoId}/followup`);
  } catch {
    followupEl.hidden = true;
    return;
  }
  if (!isCurrentReviewMemo(memoId)) return;
  followupEl.dataset.memoId = memoId;
  followupEl.hidden = view.status === 'unavailable';
  followupEl.data = view;
  if (view.status === 'generating' && attempt < FOLLOWUP_MAX_POLLS) {
    followupTimer = setTimeout(() => loadFollowup(memoId, attempt + 1), FOLLOWUP_POLL_MS);
  }
}

// A mailto: hands off to the mail app and leaves the panel where it is; a new tab would stay blank.
function openFollowupTarget(url) {
  if (url.startsWith('mailto:')) window.location.href = url;
  else chrome.tabs.create({ url });
}

followupEl.addEventListener('v-action', async (event) => {
  const { action, value, element } = event.detail;
  const memoId = element.dataset.memoId;
  const view = element.data;
  if (!memoId || !view) return;
  const { subject, body } = element.value;
  const record = (payload) => api.post(`/memos/${memoId}/followup`, payload);
  try {
    if (action === 'copy') {
      await navigator.clipboard.writeText(body);
      await record({ action: 'copied', channel: 'email', subject, body }); // nothing to repaint
      return;
    }
    const channel = value === 'whatsapp' ? 'whatsapp' : 'email';
    const target = composeTarget({ channel, to: view.to, phone: view.phone, subject, body });
    const url = target.ok ? target.url : target.fallback;
    if (!url) return;
    if (!target.ok) await navigator.clipboard.writeText(body); // too long for mailto: the body goes to the clipboard
    openFollowupTarget(url);
    element.data = await record({ action: 'sent', channel, subject, body });
  } catch (err) {
    console.warn('[followup] action failed', err);
  }
});
```

Hook points:
- In `handleReviewState(memoId, context)` (`:1731`), right after `startSessionHeartbeat();`: `loadFollowup(memoId);` (not awaited).
- At the end of `clearReviewPreviewUi()` (`:318`): `stopFollowup();`

- [ ] **Step 3: Verify**

Run: `make test-js && make check-generated`
Expected: PASS.

Manual smoke (load unpacked, then reload the side panel):
1. Make a real call from HubSpot. On the review screen the card shows *"Writing the follow-up…"* and a draft within seconds.
2. Edit a word of the body, then *Send*: the mail client opens pre-filled with the edit, no blank tab is left behind, and the card reads *"Opened in your mail app."*
3. On another memo, *Copy*: the body is on the clipboard and the card is unchanged. The extension has no clipboard precedent; if this step fails, add `"clipboardWrite"` to the manifest permissions.
4. A voicemail call shows no card.

- [ ] **Step 4: Commit**

```bash
git add chrome-extension/popup/index.html chrome-extension/popup/popup.js
git commit -m "feat(extension): follow-up draft on the review screen"
```

---

### Task 12: Desktop — the draft after a meeting

**Files:**
- Modify: `desktop/electron-main.mjs`, `desktop/renderer/index.html`, `desktop/renderer/app.js`

**Interfaces:**
- Consumes: Task 10's endpoints, `<v-followup>` (`./shared/ui/...`), `window.vocifyDesktop.shell.openExternal`.

- [ ] **Step 1: Let the bridge open mail links** — `desktop/electron-main.mjs:333`

Today `mailto:` is silently dropped while `{ok:true}` is still returned. Replace the handler:
```js
ipcMain.handle('shell:open-external', (_event, url) => {
  if (typeof url !== 'string' || !/^(https?:\/\/|mailto:)/i.test(url)) return { ok: false };
  shell.openExternal(url);
  return { ok: true };
});
```

- [ ] **Step 2: Markup** — `desktop/renderer/index.html`

Add after `./styles.css`:
```html
    <link rel="stylesheet" href="./shared/ui/vocify-ui.css" />
```

Add as the first child of `<section id="review-panel" hidden>`:
```html
        <v-followup id="review-followup" hidden></v-followup>
```

- [ ] **Step 3: Wiring** — `desktop/renderer/app.js`

Add with the other imports:
```js
import './shared/ui/components/v-followup.js';
import { composeTarget } from './shared/ui/compose.js';
```

Add before `openReview`:
```js
const followupEl = document.getElementById('review-followup');
let followupTimer = null;

async function loadFollowup(memoId, token, attempt = 0) {
  clearTimeout(followupTimer);
  if (reviewContext?.memoId !== memoId) return;
  let view;
  try {
    view = await request(`/memos/${memoId}/followup`, { token });
  } catch {
    followupEl.hidden = true;
    return;
  }
  if (reviewContext?.memoId !== memoId) return;
  followupEl.hidden = view.status === 'unavailable';
  followupEl.data = view;
  if (view.status === 'generating' && attempt < 25) {
    followupTimer = setTimeout(() => loadFollowup(memoId, token, attempt + 1), 1500);
  }
}

followupEl.addEventListener('v-action', async (event) => {
  const { action, value, element } = event.detail;
  const memoId = reviewContext?.memoId;
  const view = element.data;
  if (!memoId || !view) return;
  const token = localStorage.getItem(STORAGE.token);
  const { subject, body } = element.value;
  const record = (payload) => request(`/memos/${memoId}/followup`, { method: 'POST', token, body: payload });
  try {
    if (action === 'copy') {
      await navigator.clipboard.writeText(body);
      await record({ action: 'copied', channel: 'email', subject, body }); // nothing to repaint
      return;
    }
    const channel = value === 'whatsapp' ? 'whatsapp' : 'email';
    const target = composeTarget({ channel, to: view.to, phone: view.phone, subject, body });
    const url = target.ok ? target.url : target.fallback;
    if (!url) return;
    if (!target.ok) await navigator.clipboard.writeText(body);
    const opened = await window.vocifyDesktop.shell.openExternal(url);
    if (!opened?.ok) return;
    element.data = await record({ action: 'sent', channel, subject, body });
  } catch (err) {
    showError(reviewError, err.message || 'Follow-up failed');
  }
});
```

In `openReview`, immediately before the final `renderReview();` (`:525`). Here `reviewContext.memoId` has just been set, and `token` is already in scope from `:495`:
```js
  loadFollowup(memoId, token);
```

- [ ] **Step 4: Verify**

Run: `make test-js && make check-generated`
Expected: PASS.

Manual smoke (`npm start` in `desktop/`):
1. Listen to a short meeting and Stop. The review opens with the draft card on top.
2. *Send* opens the mail app pre-filled, and the card reads *"Opened in your mail app."*
3. *WhatsApp* is offered only when the extracted phone has a `+` country code.
4. Open a second memo right after editing the first draft: the second memo's draft replaces it (Task 4's repaint rule).

- [ ] **Step 5: Commit**

```bash
git add desktop/electron-main.mjs desktop/renderer/index.html desktop/renderer/app.js
git commit -m "feat(desktop): follow-up draft after a meeting; allow mailto hand-off"
```

---

### Task 13: Web — the draft on the memo review

**Files:**
- Create: `src/shared-ui.d.ts` (next to `src/vite-env.d.ts`), `src/hooks/use-v-element.ts`, `src/components/dashboard/FollowupCard.tsx`
- Modify: `vite.config.ts`, `src/index.css`, `src/features/memos/types.ts`, `src/features/memos/api.ts`, `src/pages/dashboard/MemoDetail.tsx`

**Interfaces:**
- Consumes: `shared/ui` through the `@shared` alias, and Task 10's endpoints.

- [ ] **Step 1: Alias and stylesheet**

In `vite.config.ts`, inside `resolve.alias`:
```ts
      "@shared": path.resolve(__dirname, "./shared"),
```

In `src/index.css`, directly after the tokens `@import` from Task 2:
```css
@import "../shared/ui/vocify-ui.css";
```

- [ ] **Step 2: Types for the JS kit** — `src/shared-ui.d.ts`

This file has no imports on purpose. In a script file, `declare module "…"` declares a new ambient module. In a module file it would be an augmentation, and it would fail because TypeScript cannot resolve the Vite alias.

```ts
declare module "@shared/ui/components/v-followup.js";

declare module "@shared/ui/compose.js" {
  export type ComposeResult =
    | { ok: true; url: string }
    | { ok: false; reason: "no_email" | "no_phone" | "too_long"; fallback?: string };
  export function composeTarget(draft: {
    channel: "email" | "whatsapp";
    to?: string;
    phone?: string;
    subject?: string;
    body?: string;
    mailClient?: "default" | "gmail" | "outlook";
  }): ComposeResult;
}

declare namespace JSX {
  interface IntrinsicElements {
    "v-followup": React.DetailedHTMLProps<React.HTMLAttributes<HTMLElement>, HTMLElement>;
  }
}
```

- [ ] **Step 3: The bridge** — `src/hooks/use-v-element.ts`

```ts
import { useEffect, useState } from "react";

export type VAction = { action: string; value: string | null; element: HTMLElement };

/** Shared custom element in React: data in as a property, v-action out as a callback.
 *  Returns a callback ref. The element is held in state, not in useRef, so both effects
 *  re-run when it mounts: a component that renders null until its data arrives would
 *  otherwise never attach the listener. */
export function useVElement<T>(data: T, onAction?: (detail: VAction) => void) {
  const [element, setElement] = useState<HTMLElement | null>(null);

  useEffect(() => {
    if (element) (element as HTMLElement & { data?: T }).data = data;
  }, [element, data]);

  useEffect(() => {
    if (!element || !onAction) return;
    const handler = (event: Event) => onAction((event as CustomEvent<VAction>).detail);
    element.addEventListener("v-action", handler);
    return () => element.removeEventListener("v-action", handler);
  }, [element, onAction]);

  return setElement;
}
```

- [ ] **Step 4: Types and API**

Add to `src/features/memos/types.ts`:
```ts
export type FollowupStatus = "generating" | "ready" | "sent" | "unavailable";

export interface FollowupView {
  status: FollowupStatus;
  recipientName?: string | null;
  to?: string;
  phone?: string;
  subject?: string;
  body?: string;
  channel?: "email" | "whatsapp";
}

export interface FollowupActionPayload {
  action: "sent" | "copied";
  channel: "email" | "whatsapp";
  subject: string;
  body: string;
}
```

In `src/features/memos/api.ts`, add both types to the existing `import type { … } from './types'`, and add to `memosApi` in its house style:
```ts
  /**
   * Follow-up draft for a memo (polled while it is being written)
   */
  getFollowup: (id: string): Promise<FollowupView> => {
    return api.get<FollowupView>(`/memos/${id}/followup`);
  },

  /**
   * Record the hand-off (sent or copied) with the rep's final text
   */
  followupAction: (id: string, payload: FollowupActionPayload): Promise<FollowupView> => {
    return api.post<FollowupView>(`/memos/${id}/followup`, payload);
  },
```

- [ ] **Step 5: The card** — `src/components/dashboard/FollowupCard.tsx`

```tsx
import "@shared/ui/components/v-followup.js";
import { useCallback } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { composeTarget } from "@shared/ui/compose.js";
import { memosApi } from "@/features/memos/api";
import type { FollowupView } from "@/features/memos/types";
import { useVElement, type VAction } from "@/hooks/use-v-element";

const POLL_MS = 1500;

type FollowupElement = HTMLElement & { value: { subject: string; body: string } };

function openTarget(url: string) {
  if (url.startsWith("mailto:")) window.location.href = url; // hands off to the mail app, page stays
  else window.open(url, "_blank", "noopener");
}

/** The follow-up draft on the memo review, for the memo's author (the hand-off POST is author-only). */
export function FollowupCard({ memoId }: { memoId: string }) {
  const queryClient = useQueryClient();
  const { data } = useQuery({
    queryKey: ["memo-followup", memoId],
    queryFn: () => memosApi.getFollowup(memoId),
    refetchInterval: (query) => (query.state.data?.status === "generating" ? POLL_MS : false),
  });

  const onAction = useCallback(
    async ({ action, value, element }: VAction) => {
      const view = queryClient.getQueryData<FollowupView>(["memo-followup", memoId]);
      if (!view) return;
      const { subject, body } = (element as FollowupElement).value;
      try {
        if (action === "copy") {
          await navigator.clipboard.writeText(body);
          toast.success("Follow-up copied");
          await memosApi.followupAction(memoId, { action: "copied", channel: "email", subject, body }); // nothing to repaint
          return;
        }
        const channel = value === "whatsapp" ? "whatsapp" : "email";
        const target = composeTarget({ channel, to: view.to, phone: view.phone, subject, body });
        const url = target.ok ? target.url : target.fallback;
        if (!url) return;
        if (!target.ok) {
          await navigator.clipboard.writeText(body);
          toast("Email body copied: paste it into the draft");
        }
        openTarget(url);
        const next = await memosApi.followupAction(memoId, { action: "sent", channel, subject, body });
        queryClient.setQueryData(["memo-followup", memoId], next);
      } catch {
        toast.error("Could not complete the follow-up");
      }
    },
    [memoId, queryClient],
  );

  const ref = useVElement(data, onAction);
  if (!data || data.status === "unavailable") return null;
  return (
    <div className="mb-4">
      <v-followup ref={ref} />
    </div>
  );
}
```

- [ ] **Step 6: Mount it** — `src/pages/dashboard/MemoDetail.tsx`

Inside the `canSeeReview` column (≈532), directly above the card `<div>` that wraps `<HubSpotSyncPreview` (≈544). `canSeeReview` already requires a finished extraction and read access, and the backend answers `unavailable` for anything ineligible. The only extra condition is authorship (`isOwnMemo`, `:288`):
```tsx
            {isOwnMemo && id ? <FollowupCard memoId={id} /> : null}
```
with `import { FollowupCard } from "@/components/dashboard/FollowupCard";`.

- [ ] **Step 7: Verify**

Run: `npm run build && make test-js`
Expected: PASS, 0 TypeScript errors.

Reticle, per `CLAUDE.md`. Save the flow with intent *"After a call, the rep finds the follow-up already written and hands it off in one click."*
1. Drive to `/dashboard/memos/<id>` of a `pending_review` memo with a ready draft.
2. `reticle_assert` that `v-followup` shows the draft subject.
3. `reticle_act_and_wait` on *Copy*, `until` the request `POST /api/v1/memos/<id>/followup` has completed with status 200.
4. Report the verdict. `unknown` and `no-fault` are not passes.

- [ ] **Step 8: Commit**

```bash
git add vite.config.ts src/index.css src/shared-ui.d.ts src/hooks/use-v-element.ts src/components/dashboard/FollowupCard.tsx \
  src/features/memos/types.ts src/features/memos/api.ts src/pages/dashboard/MemoDetail.tsx
git commit -m "feat(web): follow-up draft on the memo review"
```

---

### Task 14: End-to-end verification and docs

- [ ] **Step 1: Full suites**

Run: `make test && make test-js && npm run build && make check-generated`
Expected: all PASS.

- [ ] **Step 2: Real end-to-end, one per surface, with a real CRM contact**
- **Extension:** HubSpot call → draft → *Send*.
- **Desktop:** meeting → draft → *Send*.
- **WhatsApp:** voice note → the memo's review on the web shows the draft.
- **Manager:** opening a rep's memo on the web shows no card, and a direct `POST` answers 403.

For each, check:
- the draft cites what was actually agreed and invents nothing;
- `memos.followup.no_edit` is `true` when sent untouched;
- `user_profiles.writing_samples` grows only after a real edit.

- [ ] **Step 3: Docs**
In `docs/features/PLAN_INTEGRACION.md` §3.4, add one line: *"Superseded: non-blocking generation, see `docs/superpowers/specs/2026-09-21-copilot-spine-design.md` §4.2."*

- [ ] **Step 4: Commit**

```bash
git add docs/features/PLAN_INTEGRACION.md
git commit -m "docs: PLAN_INTEGRACION §3.4 superseded by non-blocking follow-up"
```

**Outstanding manual steps (carry to the SDD ledger):**
- Apply migration 037 to every database.
- Reload the unpacked extension and publish a new extension version.
- Build a new desktop `.dmg`.
- Read the three rollout numbers after two weeks: no-edit rate, ready-at-first-paint, hand-offs per review (spec §9).

**Not in this plan:**
- Logging the sent email to the CRM (slice 1b).
- Sending the draft back to field reps on WhatsApp.
- Gmail/Outlook OAuth.
- The Hoy engine (slice 2, spec §5).
- The grounded live pill (slice 5, spec §6.2).
