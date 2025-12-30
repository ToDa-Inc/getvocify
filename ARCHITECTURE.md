# Vocify Architecture & Development Rules

> **The first 5,000 lines of code define how the entire SaaS will be built.**
> This document is the source of truth for architectural decisions.

---

## Table of Contents

1. [Core Philosophy](#core-philosophy)
2. [Tech Stack](#tech-stack)
3. [Folder Structure](#folder-structure)
4. [Coding Rules](#coding-rules)
5. [Component Guidelines](#component-guidelines)
6. [State Management](#state-management)
7. [API Layer](#api-layer)
8. [Type System](#type-system)
9. [Database Schema](#database-schema)
10. [Backend Architecture](#backend-architecture)
11. [What We Don't Do](#what-we-dont-do)

---

## Core Philosophy

### Product Principles (from Product Overview)

1. **Speed First** - Everything should feel instant
2. **Trust Through Transparency** - Always show what will be updated
3. **Simple > Powerful** - One voice memo = one CRM update
4. **Fail Gracefully** - Never lose user's voice data
5. **European-First** - GDPR compliant, multi-language, EU data storage

### Engineering Principles

1. **YAGNI** - You Aren't Gonna Need It. Don't build for hypothetical futures.
2. **SOLID** - Single responsibility, Open/closed, Liskov substitution, Interface segregation, Dependency inversion.
3. **DRY** - Don't Repeat Yourself. But don't over-abstract either.
4. **Composition over Inheritance** - Prefer composing small pieces.
5. **Explicit over Implicit** - Code should be readable without magic.

---

## Tech Stack

### Frontend
| Technology | Purpose | Why |
|------------|---------|-----|
| **Vite** | Build tool | Fast, simple, no config needed |
| **React 18** | UI library | Industry standard, great ecosystem |
| **React Router 6** | Routing | Simple, declarative routing |
| **TanStack Query** | Server state | Caching, refetching, loading states |
| **Tailwind CSS** | Styling | Utility-first, consistent design |
| **shadcn/ui** | UI components | Accessible, customizable, not a dependency |
| **Zod** | Validation | Runtime type safety |
| **TypeScript** | Type safety | Catch errors at compile time |

### Backend
| Technology | Purpose | Why |
|------------|---------|-----|
| **Python 3.11+** | Language | AI/ML ecosystem, fast development |
| **FastAPI** | Framework | Async, automatic OpenAPI docs, Pydantic |
| **Supabase** | Database + Auth | Managed Postgres, built-in auth, RLS |
| **Deepgram** | Speech-to-Text | Best accuracy, fast, good pricing |
| **OpenAI GPT-5-mini** | Extraction | Structured outputs, reliable |

### What We Don't Use (MVP)
- ❌ Next.js (overkill for SPA)
- ❌ Docker (unnecessary complexity for MVP)
- ❌ Redis/Celery (no background jobs needed yet)
- ❌ LangChain (direct API calls are simpler)
- ❌ WebSocket streaming (batch processing is fine)

---

## Folder Structure

```
src/
├── app/                          # App shell & configuration
│   ├── App.tsx                   # Root component
│   ├── router.tsx                # Route definitions
│   └── providers.tsx             # Context providers wrapper
│
├── features/                     # Feature modules (THE CORE)
│   ├── auth/                     # Authentication
│   │   ├── components/
│   │   │   ├── LoginForm.tsx
│   │   │   ├── SignupForm.tsx
│   │   │   └── AuthGuard.tsx
│   │   ├── hooks/
│   │   │   └── useAuth.ts
│   │   ├── api.ts
│   │   ├── context.tsx
│   │   └── types.ts
│   │
│   ├── recording/                # Voice recording
│   │   ├── components/
│   │   │   ├── VoiceRecorder.tsx
│   │   │   ├── AudioWaveform.tsx
│   │   │   ├── RecordButton.tsx
│   │   │   └── UploadDropzone.tsx
│   │   ├── hooks/
│   │   │   ├── useMediaRecorder.ts
│   │   │   └── useAudioUpload.ts
│   │   ├── api.ts
│   │   └── types.ts
│   │
│   ├── memos/                    # Voice memos list & management
│   │   ├── components/
│   │   │   ├── MemoCard.tsx
│   │   │   ├── MemosList.tsx
│   │   │   └── MemosEmptyState.tsx
│   │   ├── hooks/
│   │   │   ├── useMemos.ts
│   │   │   └── useMemo.ts
│   │   ├── api.ts
│   │   └── types.ts
│   │
│   ├── approval/                 # Extraction review workflow
│   │   ├── components/
│   │   │   ├── ApprovalLayout.tsx
│   │   │   ├── TranscriptPanel.tsx
│   │   │   ├── ExtractionForm.tsx
│   │   │   ├── FieldEditor.tsx
│   │   │   ├── ConfidenceIndicator.tsx
│   │   │   └── ApprovalActions.tsx
│   │   ├── hooks/
│   │   │   └── useApproval.ts
│   │   └── types.ts
│   │
│   └── integrations/             # CRM connections
│       ├── components/
│       │   ├── IntegrationCard.tsx
│       │   ├── HubSpotConnect.tsx
│       │   └── ConnectionStatus.tsx
│       ├── hooks/
│       │   └── useIntegrations.ts
│       ├── api.ts
│       └── types.ts
│
├── shared/                       # Truly shared code
│   ├── components/
│   │   ├── Logo.tsx
│   │   ├── ErrorBoundary.tsx
│   │   ├── ErrorState.tsx
│   │   ├── EmptyState.tsx
│   │   └── LoadingSkeleton.tsx
│   ├── hooks/
│   │   ├── useDebounce.ts
│   │   └── useMobile.ts
│   ├── lib/
│   │   ├── api-client.ts         # API client singleton
│   │   ├── utils.ts              # cn(), formatters
│   │   └── constants.ts          # App-wide constants
│   └── types/
│       └── common.ts             # Shared types (ApiError, etc)
│
├── ui/                           # Design system (shadcn components)
│   ├── button.tsx
│   ├── input.tsx
│   ├── card.tsx
│   └── ...
│
├── layouts/                      # Page layouts
│   ├── DashboardLayout.tsx
│   ├── AuthLayout.tsx
│   └── LandingLayout.tsx
│
└── pages/                        # Route entry points (THIN)
    ├── index.tsx                 # Landing page
    ├── auth/
    │   ├── login.tsx
    │   └── signup.tsx
    └── dashboard/
        ├── index.tsx             # Dashboard home
        ├── record.tsx            # Record page
        ├── memos/
        │   ├── index.tsx         # Memos list
        │   └── [id].tsx          # Memo detail/approval
        ├── integrations.tsx
        ├── settings.tsx
        └── usage.tsx
```

### Folder Rules

| Rule | Description |
|------|-------------|
| **Features are isolated** | A feature folder contains everything for that feature |
| **No cross-feature imports** | Features don't import from other features directly |
| **Shared is truly shared** | Only code used by 3+ features goes in `shared/` |
| **Pages are thin** | Pages compose features, max 50 lines |
| **UI is design system only** | No business logic in `ui/` components |

---

## Coding Rules

### File Size Limits

| Type | Max Lines | Action When Exceeded |
|------|-----------|---------------------|
| Component | 200 | Split into smaller components |
| Hook | 150 | Extract helpers or split logic |
| API file | 100 | Split by resource type |
| Types file | 200 | Split by domain |
| Utility | 100 | Split by category |

### Naming Conventions

```typescript
// Files & Folders
feature-name/           // kebab-case for folders
ComponentName.tsx       // PascalCase for components
useHookName.ts         // camelCase with 'use' prefix for hooks
api.ts                 // lowercase for modules
types.ts               // lowercase for type files

// Code
const variableName     // camelCase for variables
function functionName  // camelCase for functions
const CONSTANT_VALUE   // SCREAMING_SNAKE for constants
interface TypeName     // PascalCase for types/interfaces
type StatusType        // PascalCase with descriptive suffix

// React
const ComponentName    // PascalCase
const useHookName      // camelCase with 'use' prefix
const handleEventName  // 'handle' prefix for handlers
const onEventName      // 'on' prefix for callback props
```

### Import Order

```typescript
// 1. React
import { useState, useEffect } from 'react';

// 2. External libraries
import { useQuery } from '@tanstack/react-query';
import { useNavigate } from 'react-router-dom';

// 3. Internal - absolute imports
import { Button } from '@/ui/button';
import { api } from '@/shared/lib/api-client';

// 4. Internal - relative imports (same feature)
import { useMemos } from '../hooks/useMemos';
import type { Memo } from '../types';

// 5. Styles (if any)
import './styles.css';
```

### TypeScript Rules

```typescript
// ✅ DO: Use explicit return types for public functions
export function formatDuration(seconds: number): string {
  // ...
}

// ✅ DO: Use interface for objects, type for unions/primitives
interface User {
  id: string;
  name: string;
}

type MemoStatus = 'pending' | 'approved' | 'rejected';

// ✅ DO: Use const assertions for literal types
const STATUSES = ['pending', 'approved', 'rejected'] as const;
type Status = typeof STATUSES[number];

// ❌ DON'T: Use `any`
const data: any = response;  // BAD

// ✅ DO: Use `unknown` and narrow
const data: unknown = response;
if (isValidResponse(data)) {
  // data is now typed
}

// ❌ DON'T: Use non-null assertion unless absolutely certain
const value = maybeNull!;  // BAD

// ✅ DO: Handle null cases explicitly
const value = maybeNull ?? defaultValue;
```

---

## Component Guidelines

### Component Structure

```typescript
// 1. Imports
import { useState } from 'react';
import { Button } from '@/ui/button';
import type { Memo } from '../types';

// 2. Types (if component-specific)
interface MemoCardProps {
  memo: Memo;
  onSelect: (id: string) => void;
}

// 3. Component
export function MemoCard({ memo, onSelect }: MemoCardProps) {
  // 3a. Hooks (in consistent order)
  const [isExpanded, setIsExpanded] = useState(false);
  
  // 3b. Derived state
  const isRecent = isWithinDays(memo.createdAt, 1);
  
  // 3c. Handlers
  const handleClick = () => {
    onSelect(memo.id);
  };
  
  // 3d. Early returns for edge cases
  if (!memo) return null;
  
  // 3e. Render
  return (
    <div onClick={handleClick}>
      {/* ... */}
    </div>
  );
}
```

### Component Rules

| Rule | Description |
|------|-------------|
| **Single Responsibility** | One component = one job |
| **Props over Context** | Pass props for 1-2 levels, then context |
| **Composition** | Prefer children/slots over config props |
| **No inline functions in JSX** | Extract handlers above return |
| **Semantic HTML** | Use proper elements (button, nav, article) |

### Component Patterns

```typescript
// ✅ Loading/Error/Empty states pattern
function MemosList() {
  const { data, isLoading, error } = useMemos();
  
  if (isLoading) return <MemosListSkeleton />;
  if (error) return <ErrorState message="Failed to load" />;
  if (!data?.length) return <EmptyState message="No memos" />;
  
  return <ul>{data.map(m => <MemoCard key={m.id} memo={m} />)}</ul>;
}

// ✅ Compound components pattern
<Dialog>
  <Dialog.Trigger>Open</Dialog.Trigger>
  <Dialog.Content>
    <Dialog.Title>Title</Dialog.Title>
    <Dialog.Description>Content</Dialog.Description>
  </Dialog.Content>
</Dialog>

// ✅ Render props for flexibility
<DataTable
  data={memos}
  renderRow={(memo) => <MemoRow memo={memo} />}
  renderEmpty={() => <EmptyState />}
/>
```

---

## State Management

### State Categories

| Category | Solution | Example |
|----------|----------|---------|
| **Server State** | TanStack Query | Memos, user data, CRM connections |
| **Global UI State** | React Context | Auth, theme, sidebar open |
| **Local UI State** | useState/useReducer | Form inputs, modals, toggles |
| **URL State** | React Router | Current page, filters, memo ID |

### TanStack Query Patterns

```typescript
// src/features/memos/hooks/useMemos.ts
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { memosApi } from '../api';

// Query keys as constants
export const memoKeys = {
  all: ['memos'] as const,
  lists: () => [...memoKeys.all, 'list'] as const,
  list: (filters: MemoFilters) => [...memoKeys.lists(), filters] as const,
  details: () => [...memoKeys.all, 'detail'] as const,
  detail: (id: string) => [...memoKeys.details(), id] as const,
};

// List hook
export function useMemos(filters?: MemoFilters) {
  return useQuery({
    queryKey: memoKeys.list(filters ?? {}),
    queryFn: () => memosApi.list(filters),
  });
}

// Single item hook
export function useMemo(id: string) {
  return useQuery({
    queryKey: memoKeys.detail(id),
    queryFn: () => memosApi.get(id),
    enabled: !!id,
  });
}

// Mutation with optimistic update
export function useApproveMemo() {
  const queryClient = useQueryClient();
  
  return useMutation({
    mutationFn: memosApi.approve,
    onSuccess: (data, id) => {
      queryClient.setQueryData(memoKeys.detail(id), data);
      queryClient.invalidateQueries({ queryKey: memoKeys.lists() });
    },
  });
}
```

### Context Pattern

```typescript
// src/features/auth/context.tsx
import { createContext, useContext, ReactNode } from 'react';
import { useQuery } from '@tanstack/react-query';
import { authApi } from './api';
import type { User } from './types';

interface AuthContextValue {
  user: User | null;
  isLoading: boolean;
  isAuthenticated: boolean;
}

const AuthContext = createContext<AuthContextValue | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const { data: user, isLoading } = useQuery({
    queryKey: ['auth', 'me'],
    queryFn: authApi.me,
    retry: false,
    staleTime: Infinity,
  });
  
  const value: AuthContextValue = {
    user: user ?? null,
    isLoading,
    isAuthenticated: !!user,
  };
  
  return (
    <AuthContext.Provider value={value}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  const context = useContext(AuthContext);
  if (!context) {
    throw new Error('useAuth must be used within AuthProvider');
  }
  return context;
}
```

---

## API Layer

### API Client

```typescript
// src/shared/lib/api-client.ts
const API_BASE = import.meta.env.VITE_API_URL ?? 'http://localhost:8000/api/v1';

export class ApiError extends Error {
  constructor(
    public status: number,
    public data: unknown,
    message?: string
  ) {
    super(message ?? `API Error: ${status}`);
    this.name = 'ApiError';
  }
}

class ApiClient {
  private token: string | null = null;

  setToken(token: string | null) {
    this.token = token;
  }

  private async request<T>(
    endpoint: string,
    options: RequestInit = {}
  ): Promise<T> {
    const url = `${API_BASE}${endpoint}`;
    
    const headers: HeadersInit = {
      'Content-Type': 'application/json',
      ...(this.token && { Authorization: `Bearer ${this.token}` }),
      ...options.headers,
    };

    const response = await fetch(url, { ...options, headers });

    if (!response.ok) {
      const data = await response.json().catch(() => ({}));
      throw new ApiError(response.status, data);
    }

    // Handle 204 No Content
    if (response.status === 204) {
      return undefined as T;
    }

    return response.json();
  }

  get<T>(endpoint: string): Promise<T> {
    return this.request<T>(endpoint, { method: 'GET' });
  }

  post<T>(endpoint: string, data?: unknown): Promise<T> {
    return this.request<T>(endpoint, {
      method: 'POST',
      body: data ? JSON.stringify(data) : undefined,
    });
  }

  put<T>(endpoint: string, data: unknown): Promise<T> {
    return this.request<T>(endpoint, {
      method: 'PUT',
      body: JSON.stringify(data),
    });
  }

  patch<T>(endpoint: string, data: unknown): Promise<T> {
    return this.request<T>(endpoint, {
      method: 'PATCH',
      body: JSON.stringify(data),
    });
  }

  delete<T>(endpoint: string): Promise<T> {
    return this.request<T>(endpoint, { method: 'DELETE' });
  }

  // Special method for file uploads
  async upload<T>(endpoint: string, file: Blob, fieldName = 'file'): Promise<T> {
    const formData = new FormData();
    formData.append(fieldName, file);

    const response = await fetch(`${API_BASE}${endpoint}`, {
      method: 'POST',
      headers: {
        ...(this.token && { Authorization: `Bearer ${this.token}` }),
      },
      body: formData,
    });

    if (!response.ok) {
      const data = await response.json().catch(() => ({}));
      throw new ApiError(response.status, data);
    }

    return response.json();
  }
}

export const api = new ApiClient();
```

### Feature API Files

```typescript
// src/features/memos/api.ts
import { api } from '@/shared/lib/api-client';
import type { Memo, MemoFilters, CreateMemoResponse } from './types';

export const memosApi = {
  list: (filters?: MemoFilters) => 
    api.get<Memo[]>('/memos', { params: filters }),
    
  get: (id: string) => 
    api.get<Memo>(`/memos/${id}`),
    
  upload: (audioBlob: Blob) => 
    api.upload<CreateMemoResponse>('/memos/upload', audioBlob, 'audio'),
    
  approve: (id: string, edits?: Partial<MemoExtraction>) => 
    api.post<Memo>(`/memos/${id}/approve`, edits),
    
  reject: (id: string) => 
    api.post<Memo>(`/memos/${id}/reject`),
    
  delete: (id: string) => 
    api.delete<void>(`/memos/${id}`),
};
```

---

## Type System

### Core Types

```typescript
// src/features/memos/types.ts

/** Memo status through its lifecycle */
export type MemoStatus =
  | 'uploading'       // Audio being uploaded to storage
  | 'transcribing'    // Deepgram processing audio
  | 'extracting'      // LLM extracting structured data
  | 'pending_review'  // Waiting for user to approve
  | 'approved'        // User approved, CRM updated
  | 'rejected'        // User rejected the extraction
  | 'failed';         // Processing error occurred

/** Extracted CRM data from voice memo */
export interface MemoExtraction {
  // Deal Information
  companyName: string | null;
  dealAmount: number | null;
  dealCurrency: string;
  dealStage: string | null;
  closeDate: string | null;  // ISO date string
  
  // Contact Information
  contactName: string | null;
  contactRole: string | null;
  contactEmail: string | null;
  contactPhone: string | null;
  
  // Meeting Intelligence
  summary: string;
  painPoints: string[];
  nextSteps: string[];
  competitors: string[];
  objections: string[];
  decisionMakers: string[];
  
  // Confidence scores (0-1) per field
  confidence: {
    overall: number;
    fields: Record<string, number>;
  };
}

/** Voice memo entity */
export interface Memo {
  id: string;
  userId: string;
  status: MemoStatus;
  
  // Audio
  audioUrl: string;
  audioDuration: number;  // seconds
  
  // Transcription
  transcript: string | null;
  transcriptConfidence: number | null;
  
  // Extraction
  extraction: MemoExtraction | null;
  
  // Error
  errorMessage: string | null;
  
  // Timestamps
  createdAt: string;
  processedAt: string | null;
  approvedAt: string | null;
}

/** Filters for memo list queries */
export interface MemoFilters {
  status?: MemoStatus;
  startDate?: string;
  endDate?: string;
  limit?: number;
  offset?: number;
}
```

```typescript
// src/features/integrations/types.ts

/** Supported CRM providers */
export type CRMProvider = 'hubspot' | 'salesforce' | 'pipedrive';

/** CRM connection status */
export type ConnectionStatus = 'connected' | 'expired' | 'error';

/** CRM connection entity */
export interface CRMConnection {
  id: string;
  userId: string;
  provider: CRMProvider;
  status: ConnectionStatus;
  
  // Provider-specific metadata
  metadata: {
    portalId?: string;      // HubSpot
    instanceUrl?: string;   // Salesforce
    companyDomain?: string; // Pipedrive
    userEmail?: string;
  };
  
  // Token management
  tokenExpiresAt: string | null;
  lastSyncedAt: string | null;
  
  createdAt: string;
}

/** CRM field for dynamic forms */
export interface CRMField {
  name: string;
  label: string;
  type: 'string' | 'number' | 'date' | 'select' | 'multiselect';
  required: boolean;
  options?: { value: string; label: string }[];
}

/** CRM deal schema (fetched from connected CRM) */
export interface CRMDealSchema {
  properties: CRMField[];
  stages: { id: string; label: string }[];
}
```

```typescript
// src/features/auth/types.ts

/** User entity */
export interface User {
  id: string;
  email: string;
  fullName: string | null;
  companyName: string | null;
  avatarUrl: string | null;
  createdAt: string;
}

/** Login credentials */
export interface LoginCredentials {
  email: string;
  password: string;
}

/** Signup data */
export interface SignupData {
  email: string;
  password: string;
  fullName: string;
  companyName?: string;
}

/** Auth response from API */
export interface AuthResponse {
  user: User;
  accessToken: string;
  refreshToken: string;
}
```

---

## Database Schema

### MVP Tables (Supabase/PostgreSQL)

```sql
-- Enable UUID extension
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- ============================================
-- 1. USER PROFILES
-- Extends Supabase auth.users
-- ============================================
CREATE TABLE user_profiles (
  id UUID PRIMARY KEY REFERENCES auth.users(id) ON DELETE CASCADE,
  full_name TEXT,
  company_name TEXT,
  avatar_url TEXT,
  created_at TIMESTAMPTZ DEFAULT NOW(),
  updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- RLS: Users can only access their own profile
ALTER TABLE user_profiles ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Users can view own profile"
  ON user_profiles FOR SELECT
  USING (auth.uid() = id);

CREATE POLICY "Users can update own profile"
  ON user_profiles FOR UPDATE
  USING (auth.uid() = id);

-- ============================================
-- 2. CRM CONNECTIONS
-- OAuth connections to CRM providers
-- ============================================
CREATE TABLE crm_connections (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
  
  provider TEXT NOT NULL CHECK (provider IN ('hubspot', 'salesforce', 'pipedrive')),
  status TEXT NOT NULL DEFAULT 'connected' CHECK (status IN ('connected', 'expired', 'error')),
  
  -- Encrypted tokens (use Supabase Vault in production)
  access_token TEXT NOT NULL,
  refresh_token TEXT,
  token_expires_at TIMESTAMPTZ,
  
  -- Provider-specific metadata
  metadata JSONB DEFAULT '{}',
  
  last_synced_at TIMESTAMPTZ,
  created_at TIMESTAMPTZ DEFAULT NOW(),
  updated_at TIMESTAMPTZ DEFAULT NOW(),
  
  UNIQUE(user_id, provider)
);

-- RLS
ALTER TABLE crm_connections ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Users can manage own connections"
  ON crm_connections FOR ALL
  USING (auth.uid() = user_id);

-- ============================================
-- 3. VOICE MEMOS
-- The core entity
-- ============================================
CREATE TABLE memos (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
  
  -- Status lifecycle
  status TEXT NOT NULL DEFAULT 'uploading' CHECK (
    status IN ('uploading', 'transcribing', 'extracting', 'pending_review', 'approved', 'rejected', 'failed')
  ),
  
  -- Audio
  audio_url TEXT NOT NULL,
  audio_duration REAL,  -- seconds
  
  -- Transcription (from Deepgram)
  transcript TEXT,
  transcript_confidence REAL CHECK (transcript_confidence BETWEEN 0 AND 1),
  
  -- Extraction (from GPT-5-mini)
  extraction JSONB,
  
  -- Error handling
  error_message TEXT,
  
  -- Timestamps
  created_at TIMESTAMPTZ DEFAULT NOW(),
  processed_at TIMESTAMPTZ,
  approved_at TIMESTAMPTZ
);

-- Indexes for common queries
CREATE INDEX idx_memos_user_status ON memos(user_id, status);
CREATE INDEX idx_memos_user_created ON memos(user_id, created_at DESC);

-- RLS
ALTER TABLE memos ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Users can manage own memos"
  ON memos FOR ALL
  USING (auth.uid() = user_id);

-- ============================================
-- FUNCTIONS
-- ============================================

-- Auto-update updated_at timestamp
CREATE OR REPLACE FUNCTION update_updated_at()
RETURNS TRIGGER AS $$
BEGIN
  NEW.updated_at = NOW();
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER user_profiles_updated_at
  BEFORE UPDATE ON user_profiles
  FOR EACH ROW EXECUTE FUNCTION update_updated_at();

CREATE TRIGGER crm_connections_updated_at
  BEFORE UPDATE ON crm_connections
  FOR EACH ROW EXECUTE FUNCTION update_updated_at();
```

---

## Backend Architecture

### Folder Structure

```
backend/
├── app/
│   ├── __init__.py
│   ├── main.py                 # FastAPI app entry point
│   ├── config.py               # Settings from environment
│   ├── deps.py                 # Dependency injection
│   │
│   ├── api/
│   │   ├── __init__.py
│   │   ├── router.py           # Main router combining all routes
│   │   ├── auth.py             # /auth/* endpoints
│   │   ├── memos.py            # /memos/* endpoints
│   │   └── crm.py              # /crm/* endpoints
│   │
│   ├── services/
│   │   ├── __init__.py
│   │   ├── transcription.py    # Deepgram integration
│   │   ├── extraction.py       # GPT-5-mini integration
│   │   └── hubspot.py          # HubSpot API client
│   │
│   ├── models/
│   │   ├── __init__.py
│   │   ├── memo.py             # Memo Pydantic models
│   │   ├── user.py             # User Pydantic models
│   │   └── crm.py              # CRM Pydantic models
│   │
│   └── utils/
│       ├── __init__.py
│       └── exceptions.py       # Custom exception classes
│
├── requirements.txt
├── .env.example
└── README.md
```

### API Endpoints

```
# Authentication
POST   /api/v1/auth/signup
POST   /api/v1/auth/login
POST   /api/v1/auth/logout
POST   /api/v1/auth/refresh
GET    /api/v1/auth/me

# Voice Memos
POST   /api/v1/memos/upload        # Upload audio, start processing
GET    /api/v1/memos               # List user's memos
GET    /api/v1/memos/:id           # Get single memo
POST   /api/v1/memos/:id/approve   # Approve and update CRM
POST   /api/v1/memos/:id/reject    # Reject extraction
DELETE /api/v1/memos/:id           # Delete memo

# CRM Integration
GET    /api/v1/crm/connections           # List user's connections
GET    /api/v1/crm/hubspot/authorize     # Start OAuth flow
GET    /api/v1/crm/hubspot/callback      # OAuth callback
POST   /api/v1/crm/hubspot/disconnect    # Remove connection
GET    /api/v1/crm/hubspot/schema        # Get deal fields/stages
POST   /api/v1/crm/hubspot/test          # Test connection
```

---

## What We Don't Do

### MVP Exclusions

| Don't Do | Why | When to Add |
|----------|-----|-------------|
| Docker | Adds complexity, not needed for single dev | When deploying to production |
| Redis/Celery | Sync processing is fast enough | When processing > 10 memos/sec |
| LangChain | Direct API calls are simpler | Never (probably) |
| WebSocket streaming | Batch is fine for 30-120s audio | When users want live transcription |
| Multiple CRM support | Focus on HubSpot first | After 100 paying HubSpot users |
| Mobile apps | PWA/web is sufficient | After proving product-market fit |
| Team features | Individual users first | After €10K MRR |

### Code Exclusions

| Don't Do | Instead |
|----------|---------|
| Abstract before needed | Write specific code, refactor when pattern emerges |
| Create utils "just in case" | Only extract when used 3+ times |
| Add error handling for impossible cases | Trust your own internal code |
| Build for scale Day 1 | Build for clarity, optimize when needed |
| Comment obvious code | Write self-documenting code |

---

## Changelog

| Date | Change | Author |
|------|--------|--------|
| 2025-12-30 | Initial architecture document | - |

---

> **Remember:** The goal is to help sales reps update their CRM in 60 seconds.
> Every line of code should serve that goal.


