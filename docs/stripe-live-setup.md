# Stripe Live (Enterprise Billing)

## Railway variables

```env
STRIPE_SECRET_KEY=sk_live_...
STRIPE_WEBHOOK_SECRET=whsec_...
```

## API

- `POST /api/billing/stripe/checkout-session` — creates Checkout (needs auth + plan)
- `POST /api/billing/stripe/webhook` — Stripe events (configure endpoint in Stripe Dashboard)

## Webhook URL

`https://YOUR-SERVICE.up.railway.app/api/billing/stripe/webhook`

## Test

Use Stripe test keys in staging; switch to `sk_live_` only after Dashboard activation.
