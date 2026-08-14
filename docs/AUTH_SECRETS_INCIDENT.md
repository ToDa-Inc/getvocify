# Auth secrets treated as "optional" (Aug 2026)

Two separate identity-check failures, found and closed in the same session,
sharing the same root cause: a security-critical variable was configured as
optional in code and/or documentation, and a partial fix that depended on
that variable being set was deployed without confirming it actually was.
Both let the wrong caller obtain access tied to someone else's account.
Written immediately after the fix, same reasoning as
`docs/ASSOCIATIONS_BUG.md`, so a future incident with this shape gets
recognized instead of re-investigated from scratch.

## Incident 1: `/auth/refresh` re-issued sessions based on an unverified caller-supplied token

### What was wrong

Supabase's hosted GoTrue has a known platform bug
([supabase/supabase#39394](https://github.com/supabase/supabase/issues/39394)):
`auth.sessions` has an `oauth_client_id` column that some GoTrue versions
can't scan, so `POST /token?grant_type=refresh_token` fails with
`missing destination name oauth_client_id in *models.Session` on a
project's every refresh. This app's `/auth/refresh` caught that specific
error and fell back to re-issuing a session via admin `generate_link` +
`verify_otp` (a "magiclink bypass") - identifying *who* to re-issue for from
an `access_token` the client included in the request body, decoded with:

```python
pyjwt.decode(access_token, options={"verify_signature": False, "verify_exp": False})
```

Neither the signature nor the expiry was checked. Any caller could send an
arbitrary refresh_token (as long as it triggered the `oauth_client_id`
error - which, per production logs, happened on nearly every refresh) paired
with a forged `access_token` JSON payload claiming any known `sub`/`email`,
and receive back a fully valid session for that identity. No prior
compromise of the victim was required - a public email or Supabase user UUID
was enough.

### Timeline

| Date | Commit | State |
|---|---|---|
| 2026-08-06 12:59 | `3a135a3985bc446cb469a940d7cfb794334c92d9` | Bypass introduced. `verify_signature: False, verify_exp: False`, unconditional. |
| 2026-08-09 19:48 | `d4880de1c3e70d5e7f8c2747ce2e1cd05db22437` | Adds signature verification gated on `SUPABASE_JWT_SECRET` being set - but `SUPABASE_JWT_SECRET` had never been configured in Railway. The gate never activated; production kept running the fully unverified branch introduced on 08-06. |
| 2026-08-14 (this session) | — | `SUPABASE_JWT_SECRET` set in Railway for the first time. |
| 2026-08-14/15 (this session) | pending push | Bypass mechanism removed entirely - see "What closed it". |

**Exposure window: 2026-08-06 to 2026-08-14, nine days**, not the three days
between the two commits above. The 08-09 commit did not reduce real-world
risk at all until the missing config was noticed and fixed independently,
five days later.

Both commits are confirmed on `origin/main` (`git merge-base --is-ancestor`),
i.e. both were deployed to production via Railway's push-to-deploy.

### What could have been done with it

Full session takeover for any user whose email address or Supabase UUID was
known to the attacker (both are either guessable, visible in the UI, or
present in this repo's own git history/logs) - no prior access to the
victim's device, browser storage, or any real token required.

### Detecting after the fact

Every successful bypass logged: `"Supabase refresh broken (oauth_client_id);
re-issued session via magiclink bypass for %s"` with the resolved email.
That log line does not include the caller's IP - cross-reference its
timestamps against Railway's Network Logs for `POST /api/v1/auth/refresh` to
recover it. (Left to the account owner to run against real log data - not
executed as part of this investigation.)

### What closed it

The originally-planned fix (require `SUPABASE_JWT_SECRET`, verify signature
+ expiry) was superseded once we tried to also verify that the
caller-supplied `access_token` belonged to the *same session* as the failing
`refresh_token` - the missing check in the 08-09 commit. There is no
Supabase Admin API or exposed table that provides that binding
independently of the broken `refresh_session` call itself. Since that check
can never be satisfied, the entire bypass was removed: `/auth/refresh` now
returns a clean 401 whenever GoTrue's `oauth_client_id` bug fires, and the
user has to log in again. `SUPABASE_JWT_SECRET` is now enforced at startup
(`app.api.auth.validate_startup_config`) regardless - defense in depth, not
the sole fix.

## Incident 2: `JWT_SECRET` (OAuth state signing) documented with a live-looking placeholder

### What was wrong

`JWT_SECRET` signs the `state` param HubSpot/Salesforce send back on OAuth
callback (`app/services/hubspot/oauth.py`, `app/services/salesforce/oauth.py`).
`state` carries `{"user_id": ..., "exp": ...}`; the callback trusts the
decoded `user_id` to decide which `crm_connections` row to
`upsert(..., on_conflict="user_id,provider")` with the tokens returned by
whichever CRM account just completed the consent screen.

Anyone who knows `JWT_SECRET` can forge a `state` naming an arbitrary
victim's `user_id`, complete the real OAuth consent screen with their *own*
CRM account, and have the callback silently store their tokens under the
victim's account. Every subsequent sync for that victim would then write
into the attacker's CRM instead of the victim's - a data-exfiltration path
disguised as a normal, successful connection on the victim's side, not just
a denial of service.

Unlike Incident 1, `config.py` never hardcoded an insecure default in code
(`JWT_SECRET: Optional[str] = None`). The danger was in `.env.example`,
which has shipped `JWT_SECRET=your-super-secret-key-change-in-production`
since `65ac3300` (2025-12-30) - present in this repo's history for ~7.5
months, and the repo is public. Every other secret in that file is
documented as an empty `FIELD=` line, which obviously needs filling in;
this was the one line that already looked filled in, making it the one
most likely to survive a copy-paste from `.env.example` to a real
deployment unchanged.

### Timeline

Unconfirmed. Unlike Incident 1, there is no log line that fires only when
this secret is used insecurely, and we did not read the Railway variable's
value (per this project's rule against reading production secrets
directly) - only the account owner rotated it, from this session, to a
random 48-byte value generated with `openssl`. We do not know how long the
placeholder (or any other weak value) was actually live in Railway before
that rotation. HubSpot's OAuth connect flow using this secret has existed
in the codebase since 2026-02-19 (`24c5396c`), which bounds the earliest
possible exposure but proves nothing about the actual deployed value at any
given time.

### What closed it

1. `JWT_SECRET` rotated to a random value (done by the account owner,
   independent of any code change - this alone stops exploitation of the
   *old* value, though tokens signed under it were already only valid for
   10 minutes by design, self-expiring).
2. `app.config.validate_startup_config` now refuses to start the app if
   `JWT_SECRET` is unset **or** equals the exact placeholder string from
   `.env.example` - the placeholder is checked explicitly, not just
   "unset", because it's public and could be reintroduced by a future
   copy-paste.
3. `.env.example`'s `JWT_SECRET` line changed to an empty `FIELD=`, matching
   every other secret in the file, so it no longer looks pre-filled.

## Lessons

1. **A variable security depends on cannot be "optional" in code or in
   `.env.example`.** Both incidents trace back to this. `SUPABASE_JWT_SECRET`
   was `Optional[str] = None` with no startup check, so the app ran for over
   a week with no way to verify the one token deciding who gets a re-issued
   session. `JWT_SECRET`'s danger wasn't even in code - it was a
   documentation file offering a value that looked real enough to keep.
   Anything that gates an identity decision now has a `validate_startup_config`
   check (`crm_updates`, `auth`, `config` - three so far) that fails the
   *deploy*, not a random request.
2. **A mitigation that depends on configuration you haven't confirmed is
   present mitigates nothing.** The 2026-08-09 commit was correct code that
   did nothing for five days, because nobody checked whether
   `SUPABASE_JWT_SECRET` was actually set in Railway before relying on it.
   "The code now checks for X" and "X is true in production" are two
   different claims, and only the second one closes an incident. Every fix
   in this document that depends on an env var got its own explicit,
   separate confirmation step for that reason.
