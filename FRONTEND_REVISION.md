# Frontend Revision Plan



> **Current State Analysis + Required Changes to do**

---

## Overview

The frontend has good UI foundations but is entirely static with hardcoded data. This document outlines what exists, what needs to change, and the priority order.

---

## Current State

### ✅ Good (Keep As-Is)

| Component | Location | Notes |
|-----------|----------|-------|
| Landing page | `pages/Index.tsx` | Complete, well-designed |
| Landing sections | `components/landing/*` | 15 sections, polished |
| Dashboard layout | `components/dashboard/DashboardLayout.tsx` | Good sidebar, responsive |
| UI components | `components/ui/*` | shadcn components, solid |
| Routing | `App.tsx` | Clean route structure |
| Design system | `index.css` + Tailwind | Good color scheme |

### ⚠️ Needs Revision (Hardcoded Data)

| Component | Location | Issue |
|-----------|----------|-------|
| DashboardHome | `pages/dashboard/DashboardHome.tsx` | Hardcoded memos, stats |
| MemosPage | `pages/dashboard/MemosPage.tsx` | Hardcoded memo list |
| MemoDetail | `pages/dashboard/MemoDetail.tsx` | Hardcoded transcript, extraction |
| RecordPage | `pages/dashboard/RecordPage.tsx` | Fake recording (no MediaRecorder) |
| IntegrationsPage | `pages/dashboard/IntegrationsPage.tsx` | Fake connect/disconnect |

### ❌ Missing

| Feature | Priority |
|---------|----------|
| Auth pages (login/signup) | P0 |
| Real audio recording | P0 |
| API integration | P0 |
| Loading states | P0 |
| Error states | P0 |
| AuthGuard for protected routes | P0 |
| Real CRM OAuth flow | P1 |

---

## Revision Priority

### Phase 1: Core Flow (This Week)

#### 1. RecordPage → Real Recording

**Current:** Fake timer, no actual audio capture

**Needed:**
```
pages/dashboard/record.tsx
├── Uses useMediaRecorder hook ✓ (already created)
├── Real waveform from analyser data
├── Audio preview with playback
├── Upload to backend on complete
└── Navigate to memo detail when done
```

**Changes:**
```diff
- const [state, setState] = useState<RecordingState>("idle");
- const [seconds, setSeconds] = useState(0);
+ import { useMediaRecorder, useAudioUpload } from '@/features/recording';
+ const { state, duration, audio, start, stop, reset } = useMediaRecorder();
+ const { upload, progress, isUploading } = useAudioUpload();
```

#### 2. MemosPage → Real Data

**Current:** Hardcoded array of 6 memos

**Needed:**
```
pages/dashboard/memos/index.tsx
├── Uses useMemos hook
├── Loading skeleton while fetching
├── Empty state when no memos
├── Error state on failure
└── Proper status badges from MemoStatus type
```

**Changes:**
```diff
- const memos = [ /* hardcoded */ ];
+ import { useMemos, MemoCardSkeleton, EmptyState } from '@/features/memos';
+ const { data: memos, isLoading, error } = useMemos();
+ if (isLoading) return <MemosListSkeleton />;
+ if (error) return <ErrorState onRetry={refetch} />;
```

#### 3. MemoDetail → Real Data + Approval

**Current:** Hardcoded transcript and extraction

**Needed:**
```
pages/dashboard/memos/[id].tsx
├── Uses useMemo(id) hook
├── Polls for status updates while processing
├── Real transcript display
├── Editable extraction form
├── Approve/Reject with mutations
└── Success state after approval
```

**Changes:**
```diff
- const memoData = { /* hardcoded */ };
+ import { useMemo, useApproveMemo, useRejectMemo } from '@/features/memos';
+ const { data: memo, isLoading } = useMemo(id);
+ const approveMutation = useApproveMemo();
```

#### 4. DashboardHome → Real Stats

**Current:** Hardcoded stats and recent memos

**Needed:**
```
pages/dashboard/index.tsx
├── Real recent memos (limit 5)
├── Real stats from usage API
├── Welcome message with actual user name
└── Loading states
```

---

### Phase 2: Auth & Protection

#### 5. Add Auth Pages

**Create:**
```
pages/auth/login.tsx
pages/auth/signup.tsx
pages/auth/forgot-password.tsx (later)
```

**Components needed:**
```
features/auth/components/
├── LoginForm.tsx
├── SignupForm.tsx
└── AuthLayout.tsx
```

#### 6. Add AuthGuard

**Create:**
```typescript
// features/auth/components/AuthGuard.tsx
export function AuthGuard({ children }) {
  const { isAuthenticated, isLoading } = useAuth();
  
  if (isLoading) return <LoadingScreen />;
  if (!isAuthenticated) return <Navigate to="/auth/login" />;
  
  return children;
}
```

**Update App.tsx:**
```diff
<Route path="/dashboard" element={
+  <AuthGuard>
    <DashboardLayout />
+  </AuthGuard>
}>
```

---

### Phase 3: Integrations

#### 7. IntegrationsPage → Real OAuth

**Current:** Fake connect/disconnect with toast

**Needed:**
```
pages/dashboard/integrations.tsx
├── Uses useIntegrations hook
├── Real OAuth redirect on connect
├── Real disconnect mutation
├── Test connection button works
└── Shows actual connection details from API
```

---

## Component Extraction Plan

### Extract from pages into features

| Current Location | Move To | Why |
|-----------------|---------|-----|
| `getStatusBadge()` in MemosPage | `features/memos/components/StatusBadge.tsx` | Used in 3+ places |
| Memo card JSX in MemosPage | `features/memos/components/MemoCard.tsx` | Reusable |
| Stats display in DashboardHome | `features/memos/components/QuickStats.tsx` | Standalone |
| Record button/card | `features/recording/components/RecordCard.tsx` | Used on home + record page |

---

## File Moves Needed

### Move to new structure:

```
# Dashboard layout stays (it's a layout, not a feature)
components/dashboard/DashboardLayout.tsx → layouts/DashboardLayout.tsx

# Logo is shared
components/Logo.tsx → shared/components/Logo.tsx

# Landing stays (it's self-contained)
components/landing/* → (keep as-is for now)

# Pages get thinner
pages/dashboard/DashboardHome.tsx → Refactor to use features
pages/dashboard/MemosPage.tsx → pages/dashboard/memos/index.tsx
pages/dashboard/MemoDetail.tsx → pages/dashboard/memos/[id].tsx
```

---

## Quick Wins (Do First)

1. **Wire up RecordPage** with real `useMediaRecorder` - User can actually record
2. **Add loading skeletons** - Better UX immediately
3. **Add AuthProvider** to App.tsx - Foundation for auth
4. **Extract StatusBadge** - Remove duplication

---

## Code Quality Issues to Fix

### 1. Duplicate getStatusBadge function

**Found in:** `DashboardHome.tsx`, `MemosPage.tsx`

**Solution:** Create `features/memos/components/StatusBadge.tsx`

### 2. Hardcoded user name

**Found in:** `DashboardHome.tsx` line 89: `"Welcome back, John"`

**Solution:** Use `useAuth().user.fullName`

### 3. Mixed import paths

**Found in:** Some files use `@/components/ui/`, others use relative

**Solution:** Standardize to `@/components/ui/` for design system

### 4. Unused imports

**Found in:** `IntegrationsPage.tsx` imports `X` but doesn't use it

**Solution:** Run `eslint --fix`

---

## Testing Checklist (After Revision)

- [ ] Can record audio and see waveform
- [ ] Recording uploads to backend
- [ ] Memos list loads from API
- [ ] Memo detail loads real data
- [ ] Can edit extraction fields
- [ ] Approve updates CRM (once backend ready)
- [ ] Loading states show correctly
- [ ] Error states show with retry
- [ ] Empty states show call-to-action
- [ ] Auth redirects work
- [ ] Mobile responsive

---

## Estimated Effort

| Task | Hours | Priority |
|------|-------|----------|
| Wire RecordPage with useMediaRecorder | 2-3 | P0 |
| Connect MemosPage to useMemos | 1-2 | P0 |
| Connect MemoDetail to useMemo | 2-3 | P0 |
| Add loading/error states | 1-2 | P0 |
| Create auth pages | 2-3 | P0 |
| Add AuthGuard | 1 | P0 |
| Extract StatusBadge | 0.5 | P1 |
| Real integrations page | 2-3 | P1 |
| **Total** | **~15 hours** | |

---

> **Priority:** Get RecordPage working first. That's the core product.


