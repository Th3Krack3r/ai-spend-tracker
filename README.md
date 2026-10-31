# AI Spend Tracker

**How much are you spending on AI every month?**

People stack $20/month AI subscriptions — ChatGPT, Claude, Midjourney,
Perplexity, Gemini, Copilot, API keys — and lose track of the total. This
free tool adds them up, flags possible duplicates and subscriptions you
haven't used in over 30 days, and gives you a shareable summary line like
"I'm spending $87.00/month on AI".

## How to run it

Python 3 only, no pip installs, no build step:

```bash
python3 app.py
```

Then open <http://localhost:8000> in your browser.

To use a different port:

```bash
PORT=8901 python3 app.py
```

Data is stored in `data.json` in this folder. No accounts, no external
calls, nothing leaves your machine.

## Features

- Add subscriptions: name, provider (ChatGPT, Claude, Midjourney,
  Perplexity, Gemini, Copilot, API keys, or Custom), price, billing cycle
  (monthly/yearly), optional last-used date.
- Big totals: total per month and per year. Yearly subscriptions count as
  price ÷ 12 toward the monthly total.
- Duplicate warning: the same named provider listed twice shows a
  "possible duplicate" warning — you may be paying twice for one thing.
- Unused flag: a subscription whose last-used date is more than 30 days
  ago gets a "possibly unused" badge.
- Share line: one click copies "I'm spending $X/month on AI".
- CSV export: download your whole list as a spreadsheet.

## Monetization

Two revenue hooks are built in, both driven by `config.py`:

### 1. Ads

The page has an ad slot div marked with an HTML comment
`PASTE AD NETWORK CODE HERE`. To fill it, edit `config.py`:

```python
AD_SLOT_HTML = "<!-- your ad network embed code -->"
```

Leave it as `""` and the slot shows a plain "Ad space" placeholder.

### 2. Spend Tracker Premium — $2/month

The page has a Premium upsell section ($2/month: unlimited subscriptions
+ CSV export) with a checkout button. Set the link in `config.py`:

```python
STRIPE_PRO_LINK = "https://buy.stripe.com/your-real-link"
```

The default is the placeholder `https://example.com/replace-with-stripe-link`
— replace it before you publish.

Note for this MVP: the CSV export button works for everyone right now.
Gating it behind a verified Premium purchase (accounts + payment
verification) is a future step, not a fake paywall — nothing on the page
pretends to do something it doesn't.

## Files

- `app.py` — the whole app (server, API, page). Standard library only.
- `config.py` — ad slot HTML and the Stripe Premium link.
- `data.json` — your subscriptions (local only, git-ignored).
