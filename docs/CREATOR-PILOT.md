# Creator license renewal pilot

Resolve now has a separate creator application. It tracks **fixed-term paid-ad licenses → renewal proposals → creator-recorded acceptance → creator-reported payments**. It is an invitation-pilot foundation, not a production launch or evidence of product-market fit. The original accounts-payable demo remains at `app.main:app`.

## Run locally

Use Python 3.12 and Node 22+ for the optional JavaScript syntax check. The frontend has no bundler or runtime package dependencies.

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements-dev.txt
.venv/bin/python -m uvicorn app.creator:app --host 127.0.0.1 --port 8000
```

Open `http://localhost:8000`. Choose **Explore a demo** for isolated fictional data, or **Start free** for an empty persistent account. Demo sessions expire after 24 hours; signing out deletes that demo account. Expired demo accounts are cleaned up when the application starts. Real sessions last seven days. There is no self-service password recovery yet; use a password manager during the pilot.

SQLite defaults to `data/creator.sqlite3`. Set `RESOLVE_CREATOR_DB` to an absolute path on a persistent local volume in a hosted pilot. Do not place it on ephemeral container storage or a network filesystem. Reads and writes use serialized transactions; run **one application instance** during this pilot. SQLite plus synchronous billing calls is not the horizontally scalable architecture.

## Check

```bash
.venv/bin/ruff check app/creator*.py tests/test_creator*.py tests/conftest.py
.venv/bin/ruff format --check app/creator*.py tests/test_creator*.py tests/conftest.py
.venv/bin/mypy app/creator*.py --check-untyped-defs
node --check static/creator.js
.venv/bin/python -m pytest -q
```

Use `python -m pytest` so the repository root is on the import path. Tests include the original demo regression suite, private account boundaries, CSRF, request-size limits, concurrent/duplicate payments, reversals, CSV formula escaping, renewal date arithmetic and Stripe transport fixtures. Tests create temporary databases. Stripe tests never contact Stripe or make a charge.

## Product rules

- One license records one usage scope, one contact, and a fixed inclusive date range. Perpetual rights and complex exclusivity schedules are outside the pilot.
- Renewal fees are creator-entered proposals, not earned revenue. The app suggests no market rate and makes no claim to detect ongoing ad use.
- A draft snapshots the scope, fee, dates and reference links. Editing the license invalidates acceptance of its old draft; close the draft and prepare another.
- An expired license starts its proposed next term today, never retroactively. Accepting a renewal sets the current license dates to that renewal's dates. History retains previous terms.
- Approval is entered by the creator after written agreement. It is not an electronic signature collected from the brand.
- USD integer cents are used for balances. A payment can only be recorded after acceptance and cannot exceed the balance. Idempotency keys prevent duplicate submissions; reversals preserve history and move no money.
- Email drafts are reviewed and copied/opened in a mail client. Resolve neither sends nor measures delivery/replies.
- Free accounts can keep three unarchived licenses; Pro allows 2,000. A downgrade retains records and exports but prevents adding/restoring licenses over the free limit. Existing license workflows remain usable.
- The CSV export is a renewal summary. Per-license text exports contain renewal, payment and activity history. References and payments are not independently verified.

## Optional Stripe subscription billing

Billing charges for **Resolve**, never for a brand's renewal. Without the complete configuration, billing reports unavailable and the free workspace works normally. No keys are required for development.

Configure in your hosting provider's secret/environment settings, never commit values:

| Variable | Value |
| --- | --- |
| `RESOLVE_PUBLIC_URL` | Exact origin, e.g. `https://creators.example.com`, no path or query; HTTPS in a hosted environment. |
| `RESOLVE_CREATOR_DB` | Absolute persistent SQLite path. |
| `STRIPE_SECRET_KEY` | A secret key for the chosen Stripe account/mode. Start with test mode. |
| `STRIPE_PRICE_ID` | An active recurring **USD 19.00 every month** price. Checkout refuses a mismatched amount/currency/interval. |
| `STRIPE_WEBHOOK_SECRET` | Signing secret of the endpoint below; Stripe CLI forwarding uses its own local secret. |

1. Create the product and monthly price in [Stripe's dashboard](https://dashboard.stripe.com/test/products). [API keys](https://dashboard.stripe.com/test/apikeys) and [webhook destinations](https://dashboard.stripe.com/test/workbench/webhooks) must be from the same account/mode.
2. Enable the [customer portal](https://dashboard.stripe.com/test/settings/billing/portal), including cancellation. Keep the pilot price fixed; arbitrary subscription price changes are not supported by this entitlement mapping.
3. Point the webhook destination at `https://YOUR_ORIGIN/api/billing/webhook` and use the **2025-03-31.basil** event/API version. Subscribe to `customer.subscription.created`, `.updated`, `.deleted`, `checkout.session.completed`, `checkout.session.async_payment_succeeded`, `invoice.payment_succeeded`, and `invoice.payment_failed`.
4. For local test-mode forwarding, follow [Stripe CLI documentation](https://docs.stripe.com/stripe-cli) and run `stripe listen --forward-to localhost:8000/api/billing/webhook`. Copy the printed signing secret into the server's environment and restart it. This step requires owner authentication; it has not been exercised in this build.
5. Exercise hosted checkout, webhook delivery, payment failure, cancellation and portal return in test mode before considering a live pilot. The current automated tests use fixture responses and signed fixture payloads; they do **not** verify a real hosted checkout.

Customers and checkout sessions use stable idempotency keys. An open checkout is reused. The browser return URL never grants access. Raw webhook bodies are authenticated with HMAC-SHA256, a five-minute timestamp tolerance, constant-time comparisons and event-ID deduplication. To handle out-of-order events, the server fetches **current** subscription state and checks both the customer and server-set user metadata plus the configured price. `active` and `trialing` subscriptions grant Pro; other states use Free. Cancellation at period end remains Pro while Stripe still reports active. API failures leave the prior entitlement unchanged and return a retryable error without marking the event processed. Monitor webhook delivery/retries; there is no scheduled reconciliation job yet.

API references: [Checkout sessions](https://docs.stripe.com/api/checkout/sessions/create), [customers](https://docs.stripe.com/api/customers/create), [subscriptions](https://docs.stripe.com/api/subscriptions/list), [portal sessions](https://docs.stripe.com/api/billing_portal/sessions/create), [signature verification](https://docs.stripe.com/webhooks/signature).

## What must happen before a public paid launch

The market research found real license expiry transactions and existing paid offers, **including direct competitors**. Novelty, low saturation, willingness to switch and willingness to pay for Resolve are unproven. Pricing is a hypothesis. Do not buy traffic or build a broad creator suite on the strength of a competitor price list.

Start with 15 interviews with creators who have several paid-ad licenses and at least two renewals coming due in the next 60 days. Inspect their most recent actual renewal and existing tools. Recruit ten into a supported pilot; disclose the proposed $19 price before onboarding. Experimental gates: 8/15 report repeated unsolved pain; 5/10 enter two real licenses and draft an offer within a week; 3/10 pay without a bundled service; those paying customers return within 30 days. Track user-reported time saved, offers sent, approvals and payments separately. Payment causality is not inferred from the dashboard.

Before collecting real subscriptions: set up and verify hosting, HTTPS, trusted proxy configuration, a persistent volume, backups/restore, monitoring, webhook alerts, support/refund/cancellation handling and clear privacy/terms. Authentication currently lacks email verification, recovery and account deletion; provision those workflows or a documented supported process before external customer onboarding. Never expose the original unauthenticated synthetic demo as a production tenant API.

After repeat paid use: migrate through versioned schemas to managed PostgreSQL; add account lifecycle flows, bounded queries/pagination, background jobs, scheduled renewal notifications, reconciliation, durable event processing and abuse controls at the edge. Test migrations and restore drills before scaling instances. The current rate limit is local to the database and uses the ASGI client address; configure trusted proxy headers carefully. Prefer opt-in integrations only after demand supports them.
