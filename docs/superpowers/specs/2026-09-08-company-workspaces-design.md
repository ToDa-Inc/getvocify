# Company workspaces, seats, and invites — design spec

**Date**: 2026-09-08  
**Status**: Implemented

See implementation in:
- `backend/migrations/028_companies.sql`
- `backend/app/services/company.py`
- `backend/app/api/company.py`
- `src/pages/dashboard/TeamPage.tsx`

This document mirrors the approved plan: relational companies with shared CRM/glossary/product context, Vocify-admin seat caps, Resend transactional email.
