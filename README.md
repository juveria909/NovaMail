# AI Email Campaign Automation Agent

> A production-ready Python backend that generates deeply personalized email campaigns using Google Gemini AI, powered by a live 1000-record customer dataset refreshed from the web every 5 seconds.

---

## Project Structure

```
ai-email-agent/
│
├── backend/                        ← Python FastAPI backend
│   ├── main.py                     ← Server entry point, all API routes
│   ├── config.py                   ← All settings (reads from .env)
│   │
│   ├── data/                       ← PART 1: Live Dataset
│   │   ├── live_fetcher.py         ← Fetches real users from RandomUser.me API
│   │   ├── data_enricher.py        ← Adds behavioral signals (purchases, email stats)
│   │   └── stream_manager.py       ← In-memory dataset with live refresh loop
│   │
│   ├── ai/                         ← PART 2: AI Email Generation
│   │   ├── system_prompts.py       ← Modular prompt blocks (identity, customer, campaign)
│   │   ├── prompt_builder.py       ← Assembles prompts for each campaign type
│   │   ├── json_extractor.py       ← 3-layer JSON extraction + schema validation
│   │   ├── ai_adapter.py           ← Unified Gemini/Groq client with fallback + retry
│   │   └── email_generator.py      ← Orchestrator + SendGrid sender
│   │
│   └── utils/
│       ├── logger.py               ← Structured logging configuration
│       └── validators.py           ← Business-rule validation helpers
│
├── .env                            ← API keys (NEVER commit this to git)
├── requirements.txt                ← Python dependencies
└── README.md                       ← This file
```

---

## Quick Start

### Step 1 — Set up your API keys

Open `.env` and fill in:

```env
GEMINI_API_KEY=your_key_here       # https://aistudio.google.com/app/apikey (free)
SENDGRID_API_KEY=your_key_here     # https://signup.sendgrid.com/ (free: 100/day)
FROM_EMAIL=you@yourdomain.com      # Must be verified in SendGrid dashboard
```

> **Leave `EMAIL_STUB_MODE=true` while developing** — emails won't actually send,
> but everything else works perfectly. Flip to `false` when ready to send real emails.

### Step 2 — Install dependencies

```bash
pip install -r requirements.txt
```

### Step 3 — Run the server

```bash
python -m backend.main
```

Server starts at: **http://localhost:8000**  
Interactive API docs: **http://localhost:8000/docs**

---

## API Reference

### Dataset Endpoints (Part 1)

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/api/dataset` | Get live records (add `?limit=50&segment=inactive`) |
| `GET` | `/api/dataset/stats` | Dataset statistics and segment counts |
| `GET` | `/api/dataset/customer/{id}` | Get one customer by UUID |
| `GET` | `/api/dataset/search?q=fitness` | Search by name, email, or interest |
| `GET` | `/api/dataset/segments` | Segment breakdown with descriptions |

### Email Generation Endpoints (Part 2)

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/api/email/generate` | Generate a personalized email |
| `POST` | `/api/email/followup` | Generate a follow-up email |
| `POST` | `/api/email/rewrite` | Rewrite an email with feedback |
| `POST` | `/api/email/batch` | Generate emails for many customers |

---

## Example Requests

### Generate a Welcome Email

```bash
curl -X POST http://localhost:8000/api/email/generate \
  -H "Content-Type: application/json" \
  -d '{
    "campaign_type": "welcome",
    "send": false
  }'
```

### Generate Re-engagement Email for a Specific Customer

```bash
curl -X POST http://localhost:8000/api/email/generate \
  -H "Content-Type: application/json" \
  -d '{
    "campaign_type": "reengagement",
    "customer_id": "550e8400-e29b-41d4-a716-446655440000",
    "send": false
  }'
```

### Generate 3 A/B Test Variants

```bash
curl -X POST http://localhost:8000/api/email/generate \
  -H "Content-Type: application/json" \
  -d '{
    "campaign_type": "variant_test",
    "num_variants": 3,
    "base_campaign_type": "reengagement"
  }'
```

### Generate Follow-up (customer opened but didn't click)

```bash
curl -X POST http://localhost:8000/api/email/followup \
  -H "Content-Type: application/json" \
  -d '{
    "customer_id": "550e8400-e29b-41d4-a716-446655440000",
    "previous_email_subject": "Sarah, we miss you!",
    "outcome": "opened_no_click",
    "send": false
  }'
```

### Rewrite an Email with Feedback

```bash
curl -X POST http://localhost:8000/api/email/rewrite \
  -H "Content-Type: application/json" \
  -d '{
    "customer_id": "550e8400-e29b-41d4-a716-446655440000",
    "original_email": "{\"subject_line\": \"Hi Sarah\", ...}",
    "feedback": "Make the subject line more curiosity-driven and cut body by 30%"
  }'
```

### Run a Batch Campaign (5 inactive customers)

```bash
curl -X POST http://localhost:8000/api/email/batch \
  -H "Content-Type: application/json" \
  -d '{
    "campaign_type": "reengagement",
    "segment": "inactive",
    "limit": 5,
    "send": false
  }'
```

---

## Customer Segments

| Segment | Meaning | Best Campaign |
|---------|---------|---------------|
| `new_signup` | Joined in last 7 days | Welcome |
| `new` | Joined 8–30 days ago | Welcome / Nurture |
| `active` | Regularly engaged | Upsell / Feature |
| `inactive` | No activity 90+ days | Re-engagement |
| `high_value` | Frequent buyer, active | VIP / Exclusive |
| `at_risk` | Going quiet (45–90 days) | Retention |

---

## Follow-up Outcomes

| Outcome | Meaning | AI Strategy |
|---------|---------|-------------|
| `opened_no_click` | Opened, didn't click CTA | Address objections |
| `not_opened` | Didn't open at all | New subject line, fresh hook |
| `clicked_no_convert` | Clicked, didn't complete action | Remove friction |
| `converted` | Completed the action | Celebrate, set expectations |

---

## How the Live Dataset Works

```
RandomUser.me API
      ↓  (fetch 1000 real users on startup)
  live_fetcher.py
      ↓  (add behavioral signals: interests, purchases, email stats)
  data_enricher.py
      ↓  (store in memory, refresh 20 records every 5 seconds)
  stream_manager.py
      ↓  (serve to API routes)
  /api/dataset endpoints
```

---

## How Email Generation Works

```
API Request (campaign_type, customer_id)
      ↓
  email_generator.py  (picks customer from dataset)
      ↓
  prompt_builder.py   (assembles system prompt + user message)
      ↓
  ai_adapter.py       (calls Gemini, falls back to Groq if needed)
      ↓
  json_extractor.py   (3-layer extraction + schema validation)
      ↓
  email_generator.py  (optionally sends via SendGrid)
      ↓
  API Response (structured JSON with email content + metadata)
```

---

## Switching from Gemini to Groq

In `.env`:
```env
AI_PROVIDER=groq
GROQ_API_KEY=your_groq_key_here
```

That's it. The adapter handles everything else automatically.

---

## Activating SendGrid (Real Email Sending)

1. Sign up free at [sendgrid.com](https://signup.sendgrid.com/)
2. Go to **Settings → API Keys → Create API Key** (Full Access)
3. Go to **Settings → Sender Authentication** → verify your `FROM_EMAIL`
4. Update `.env`:
   ```env
   EMAIL_STUB_MODE=false
   SENDGRID_API_KEY=SG.your_real_key_here
   FROM_EMAIL=you@yourverifieddomain.com
   ```
5. Restart the server — emails will now actually send!

---

## Rate Limits (Free Tiers)

| Service | Free Limit | What Happens If Exceeded |
|---------|-----------|--------------------------|
| Gemini 2.0 Flash | 15 req/min, 1500/day | 429 error → auto-retry with backoff |
| Groq (LLaMA 3.3) | 30 req/min, 14400/day | 429 error → fallback to Gemini |
| RandomUser.me | Unlimited | Throttle if hammered |
| SendGrid | 100 emails/day | Bounced — upgrade plan needed |
