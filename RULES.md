# Vocify Development Rules

> **Read before writing any code.** These rules ensure consistency and maintainability.

---

## File Structure Rules

| Rule | Description |
|------|-------------|
| **Features are isolated** | Each feature folder contains all its own components, hooks, api, types |
| **No cross-feature imports** | Features don't import from other features directly |
| **Shared is truly shared** | Only code used by 3+ features goes in `shared/` |
| **Pages are thin** | Pages compose features, max 50 lines of code |
| **UI is design system only** | No business logic in `ui/` components |

---

## File Size Limits

| Type | Max Lines | Action When Exceeded |
|------|-----------|---------------------|
| Component | 200 | Split into smaller components |
| Hook | 150 | Extract helpers or split logic |
| API file | 100 | Split by resource type |
| Types file | 200 | Split by domain |
| Utility | 100 | Split by category |

**When a file exceeds limits, create a folder with the same name and split into multiple files.**

---

## Naming Conventions

```
# Files & Folders
feature-name/           # kebab-case for folders
ComponentName.tsx       # PascalCase for components
useHookName.ts         # camelCase with 'use' prefix
api.ts                 # lowercase for modules
types.ts               # lowercase for type files

# Code
const variableName     # camelCase
function functionName  # camelCase
const CONSTANT_VALUE   # SCREAMING_SNAKE
interface TypeName     # PascalCase
type StatusType        # PascalCase

# React
const ComponentName    # PascalCase
const useHookName      # camelCase with 'use'
const handleEventName  # 'handle' prefix for handlers
const onEventName      # 'on' prefix for callback props
```

---

## Import Order

```typescript
// 1. React
import { useState, useEffect } from 'react';

// 2. External libraries
import { useQuery } from '@tanstack/react-query';
import { useNavigate } from 'react-router-dom';

// 3. Internal - absolute imports (@/)
import { Button } from '@/components/ui/button';
import { api } from '@/shared/lib/api-client';

// 4. Internal - relative imports (same feature)
import { useMemos } from '../hooks/useMemos';
import type { Memo } from '../types';

// 5. Styles (if any)
import './styles.css';
```

---

## TypeScript Rules

```typescript
// ✅ DO: Explicit return types for public functions
export function formatDuration(seconds: number): string { }

// ✅ DO: interface for objects, type for unions
interface User { id: string; name: string; }
type Status = 'pending' | 'approved' | 'rejected';

// ✅ DO: const assertions for literal types
const STATUSES = ['pending', 'approved'] as const;
type Status = typeof STATUSES[number];

// ❌ DON'T: Use `any` - use `unknown` and narrow
const data: any = response;  // BAD
const data: unknown = response;  // GOOD

// ❌ DON'T: Non-null assertion unless certain
const value = maybeNull!;  // BAD
const value = maybeNull ?? defaultValue;  // GOOD
```

---

## Component Structure

```typescript
// 1. Imports (in order above)
import { useState } from 'react';
import { Button } from '@/components/ui/button';
import type { Memo } from '../types';

// 2. Types (if component-specific)
interface MemoCardProps {
  memo: Memo;
  onSelect: (id: string) => void;
}

// 3. Component
export function MemoCard({ memo, onSelect }: MemoCardProps) {
  // 3a. Hooks first
  const [isExpanded, setIsExpanded] = useState(false);
  
  // 3b. Derived state
  const isRecent = isWithinDays(memo.createdAt, 1);
  
  // 3c. Handlers
  const handleClick = () => onSelect(memo.id);
  
  // 3d. Early returns
  if (!memo) return null;
  
  // 3e. Render
  return <div onClick={handleClick}>...</div>;
}
```

---

## Component Rules

| Rule | Description |
|------|-------------|
| **Single Responsibility** | One component = one job |
| **Props over Context** | Pass props for 1-2 levels, then context |
| **Composition** | Prefer children/slots over config props |
| **No inline functions in JSX** | Extract handlers above return |
| **Semantic HTML** | Use proper elements (button, nav, article) |

---

## State Management

| Category | Solution | Example |
|----------|----------|---------|
| **Server State** | TanStack Query | Memos, user data, CRM |
| **Global UI State** | React Context | Auth, theme |
| **Local UI State** | useState/useReducer | Forms, modals |
| **URL State** | React Router | Filters, current page |

---

## API Patterns

```typescript
// Always use the api client
import { api } from '@/shared/lib/api-client';

// Define query keys as constants
export const memoKeys = {
  all: ['memos'] as const,
  list: (filters?: Filters) => [...memoKeys.all, 'list', filters] as const,
  detail: (id: string) => [...memoKeys.all, 'detail', id] as const,
};

// Wrap in typed functions
export const memosApi = {
  list: (filters?: Filters) => api.get<Memo[]>('/memos'),
  get: (id: string) => api.get<Memo>(`/memos/${id}`),
};
```

---

## Loading/Error States Pattern

```typescript
function MemosList() {
  const { data, isLoading, error, refetch } = useMemos();
  
  if (isLoading) return <MemosListSkeleton />;
  if (error) return <ErrorState message="Failed to load" onRetry={refetch} />;
  if (!data?.length) return <EmptyState message="No memos" action={<RecordButton />} />;
  
  return <ul>{data.map(m => <MemoCard key={m.id} memo={m} />)}</ul>;
}
```

---

## What We DON'T Do

| Don't | Instead |
|-------|---------|
| Abstract before needed | Write specific code, refactor when pattern emerges |
| Create utils "just in case" | Only extract when used 3+ times |
| Add error handling for impossible cases | Trust internal code |
| Build for scale Day 1 | Build for clarity, optimize when needed |
| Comment obvious code | Write self-documenting code |
| Use `console.log` in production | Use proper error handling |
| Commit commented-out code | Delete it, git has history |
| Create empty files "for later" | Create when needed |

---

## Git Commit Messages

```
feat: add voice recording with waveform visualization
fix: correct audio upload progress calculation
refactor: extract memo card into separate component
chore: update dependencies
docs: add API documentation
```

---

## Before Submitting PR

- [ ] No lint errors
- [ ] No TypeScript errors
- [ ] No console.log statements
- [ ] No commented-out code
- [ ] File size limits respected
- [ ] Import order correct
- [ ] Component structure followed
- [ ] Loading/error states handled

---

> **When in doubt:** Simpler is better. If you're not sure, ask.


