# Stripe workspace billing — design spec

**Date**: 2026-09-09  
**Status**: Implemented

## Goal

Company owners and admins subscribe the workspace to Starter or Pro (monthly or yearly). Vocify admin controls whether a workspace is open, must pay, or is fully unlocked. Open is the default. No landing checkout, no usage credits.

## Decisions

- Billable unit: workspace plan (`starter` | `pro` × `monthly` | `yearly`). Quantity is always 1.
- Buyer: company owner or admin.
- Seat cap stays on `companies.seat_limit` (admin). Stripe quantity is not synced to seats.
- After they pay, Stripe is source of truth for the plan. Admin can still unlock or change the seat cap.
- New companies stay open (`access_mode = open`). Paywall is opt-in per company.
- Paywall: `access_mode = paywalled` and billing status is not `active` or `trialing` (3-day `past_due` grace). Locked dashboard except Billing.
- Dialer: Pro on a live subscription, unlocked workspaces, or open workspaces that have not subscribed yet.
- Collection: Stripe Checkout for first subscribe; Subscription.modify to switch plan/interval; Customer Portal for card and invoices.

## Catalog

| Plan | Interval | EUR | Stripe product |
|---|---|---|---|
| Starter | monthly | 30 | `prod_VENfYYKhSV2KAB` |
| Pro | monthly | 50 | `prod_VENfWDk6BSnMIy` |
| Starter | yearly | 300 | `prod_VENgF43xTwG3OT` |
| Pro | yearly | 500 | `prod_VENgP2K1H6YO7c` |

Shared: transcriptions, summaries, CRM logging, tasks, follow-up email, scoring, live coaching.  
Pro: dialer included with 1,000 minutes.

Checkout resolves each product's `default_price` (optional `STRIPE_PRICE_*` env overrides).

## Data

On `companies` (workspace policy only):

- `seat_limit`
- `access_mode` (`open` | `paywalled` | `unlocked`, default `open`)

On `company_billing` (1:1 Stripe snapshot):

- `stripe_customer_id`
- `stripe_subscription_id`
- `billing_status` (`none` | `active` | `trialing` | `past_due` | `canceled` | `unpaid` | `incomplete`)
- `plan_type` (`starter` | `pro` | null)
- `billing_interval` (`monthly` | `yearly` | null)
- `quantity`
- `current_period_end`
- `cancel_at_period_end`
- `past_due_since` (3-day grace before a paywalled workspace locks)

`stripe_webhook_events` stores processed Stripe event ids after a successful apply.

## Surfaces

- `GET/POST /api/v1/billing/*` — status (includes catalog), checkout `{plan, interval}`, portal
- `POST /webhooks/stripe` — signed, idempotent
- `/dashboard/settings/billing` — Starter / Pro paywall
- Admin company — access mode + license slider
- Dashboard layout — redirect to billing when paywalled; hide dialer unless entitled

## Out of scope

Landing pricing, hard lock on signup, calling minute meters, promo codes, embedded Checkout, affiliates.
