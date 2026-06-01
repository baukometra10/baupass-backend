# Stripe Live (Enterprise Billing)

## Railway variables

```env
STRIPE_SECRET_KEY=sk_live_...
STRIPE_WEBHOOK_SECRET=whsec_...

# Create Products/Prices in Stripe Dashboard, then map:
STRIPE_PRICE_STARTER=price_...
STRIPE_PRICE_PROFESSIONAL=price_...
STRIPE_PRICE_ENTERPRISE=price_...
STRIPE_PRICE_STARTER_ANNUAL=price_...
STRIPE_PRICE_PROFESSIONAL_ANNUAL=price_...
STRIPE_PRICE_ENTERPRISE_ANNUAL=price_...
```

## Public pricing (net, excl. VAT)

| Plan | Base / month | Workers included | Extra worker |
|------|-------------|------------------|--------------|
| Tageskarte | 29 € / day | — | — |
| Starter | 69 € | 10 | 5,99 € |
| Professional | 249 € | 25 | 7,50 € |
| Enterprise | 599 € | 50 | 9,50 € |

Annual subscription checkout applies **17% discount** on the base fee.

Market reference: Crewly ~49 € + 4,99 €/MA, 123erfasst 7–12 €/MA, Ditio ~17 €/active user.

## Bootstrap products (one-time)

```bash
# Local or CI with STRIPE_SECRET_KEY set:
python backend/ops/setup_stripe_products.py

# Preview only:
python backend/ops/setup_stripe_products.py --dry-run

# Or superadmin API:
POST /api/v2/billing/stripe/bootstrap
```

## Trial

First Stripe subscription checkout includes **14 days free** (`BAUPASS_STRIPE_TRIAL_DAYS=14`).
Set `BAUPASS_STRIPE_TRIAL_DAYS=0` to disable. Trial end syncs to `companies.trial_ends_at` via webhook.

## API

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/v2/billing/pricing` | Public pricing catalog |
| GET | `/api/v2/billing/overview` | Company plan, workers, open invoices |
| GET | `/api/v2/billing/revenue-metrics` | Superadmin MRR estimate |
| POST | `/api/v2/billing/stripe/checkout-session` | Subscription upgrade |
| POST | `/api/v2/billing/stripe/portal-session` | Stripe Customer Portal |
| POST | `/api/v2/billing/invoices/{id}/payment-link` | One-off invoice payment |
| POST | `/api/billing/stripe/webhook` | Stripe events (legacy path) |
| POST | `/api/v2/billing/stripe/webhook` | Stripe events (v2 path) |

## UI (Enterprise-Hub & Control Pass)

When `STRIPE_SECRET_KEY` is set, `GET /api/platform/enterprise-catalog` includes `billing.stripeConfigured` and `billing.selfServeCheckout` (company-admin only).

- **Company-admin:** Hub buttons «Professional buchen» / «Enterprise buchen» start Stripe Checkout via parent shell.
- **Superadmin:** «Tarif & Firma (Admin)» opens Admin → companies (plan assignment).
- **Without Stripe:** Hub falls back to mailto / Rechnungen block.

Local Python: use **3.12** (see `.python-version`). E2E: `npx playwright test tests/e2e/platform-smoke.spec.js`.

## Webhook URL

`https://YOUR-SERVICE.up.railway.app/api/billing/stripe/webhook`

Enable events: `checkout.session.completed`, `customer.subscription.*`, `invoice.paid`, `invoice.payment_failed`.

## Test

Use Stripe test keys in staging; switch to `sk_live_` only after Dashboard activation.
