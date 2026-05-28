# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What This Is

A WhatsApp AI agent for **Nanyang Tuition** (Singapore), deployed on Railway. The bot persona is "Geraldine Goh, Senior Education Consultant." It handles new tuition enquiries, FAQs, and complaints via the Meta WhatsApp Cloud API.

## Running Locally

```bash
pip install -r requirements.txt
# Set env vars (see .env) then:
uvicorn main:app --host 0.0.0.0 --port 8000
```

For local webhook testing, use `cloudflared.exe` (included) to tunnel to localhost.

## Deploying

Railway auto-deploy is broken — every deploy must be triggered manually via the Railway GraphQL API. `deploy_railway.js` is a project-creation script and must NOT be used for redeployments.

**Correct redeploy sequence** (must disconnect + reconnect to force Railway to pull the latest GitHub commit — `serviceInstanceDeployV2` alone reuses the cached old commit):

```js
// 1. Disconnect
mutation { serviceDisconnect(id: SERVICE_ID) { id } }

// 2. Reconnect (branch is required)
mutation { serviceConnect(id: SERVICE_ID, input: { repo: "dhruvesh76/whatsapp-ai-agent", branch: "main" }) { id } }

// 3. Deploy
mutation { serviceInstanceDeployV2(serviceId: SERVICE_ID, environmentId: ENV_ID) }
```

```
Project ID:     05f0189a-4c7f-4204-bab3-b01b3903920a
Service ID:     03732ac4-6df2-4da9-840a-2d27ac922681
Environment ID: 28017ed9-c7c5-40be-87c3-17671471cabd
Railway token:  e038b562-87b8-4e08-a8cb-95b90da22b6d (account: scale.mediax@gmail.com)
GitHub repo:    dhruvesh76/whatsapp-ai-agent
App URL:        https://agent-production-aee4.up.railway.app
```

Use `node --use-system-ca` when running the deploy script on Windows (Railway's cert requires system CA).

## Architecture

```
WhatsApp user
    ↓ Meta webhook POST /webhook
main.py  → dedup seen IDs → image? → reply & return
                           → owner commands (STOP / RESET / RESET ALL)
                           → debounce.add_message()
debounce.py  10s buffer per user, combines rapid messages with \n
                           ↓
pipeline.py  process_message()
    ├─ OWNER_TAKEN_OVER → return None
    ├─ _is_silent() check → return None (farewells / standalone acks)
    ├─ plain "thank you" → "You are welcome, feel free to reach out anytime."
    ├─ _GRATITUDE_WITH_CONTEXT → "You are welcome, feel free to reach out anytime."
    ├─ NT number regex → _NT_RESPONSE (hard-coded, no GPT)
    ├─ job seeker keywords → _JOB_SEEKER_RESPONSE (hard-coded, no GPT)
    ├─ fitness keywords → run_geraldine() directly (bypass FAQ agent)
    ├─ COMPLETED state
    │       ├─ rate/pricing keywords → run_geraldine() with full history (no reset)
    │       ├─ POST_COMPLETE_CLASSIFIER
    │       │       ├─ WANTS_NEW_TUTOR → reset state, run_geraldine()
    │       │       ├─ COMPLAINT_URGENT → handle_complaint()
    │       │       ├─ FAQ → _faq_with_followup()
    │       │       └─ IGNORE → return None
    └─ ACTIVE state → CLASSIFIER
            ├─ NEW_PARENT → GPT-4o as Geraldine (SYSTEM_PROMPT)
            │       └─ closing phrase detected → _send_completion_summary() to owner
            ├─ FAQ → _faq_with_followup() (FAQ agent + optional Geraldine handoff)
            ├─ COMPLAINT_URGENT → handle_complaint() + async owner notification
            └─ OTHER → random FALLBACK_MESSAGES
```

**State** (`state.py`): pure in-memory dict, resets on every redeploy. Per user: `status` (ACTIVE / COMPLETED / OWNER_TAKEN_OVER), `history` (full GPT message list), `complaint_count`.

**Debounce** (`debounce.py`): 10-second asyncio timer per `wa_id`. Cancels and restarts on each new message. Fires joined text to `process_and_send` callback.

## Key Files

| File | Purpose |
|---|---|
| `main.py` | FastAPI app, webhook handler, owner commands, image handler |
| `pipeline.py` | All routing logic, hard-coded keyword checks, classifier prompts, FAQ agent, complaint cycling, owner summary generation |
| `system_prompt.py` | Single `SYSTEM_PROMPT` constant — Geraldine's full instructions, all category form templates, pricing tables, fitness/violin/piano rules |
| `state.py` | In-memory user state management |
| `debounce.py` | Per-user 10-second message buffer |
| `whatsapp.py` | Meta WhatsApp Cloud API `send_message()` |

## Hard-Coded Python Rules (pipeline.py — bypass GPT entirely)

These checks run before any GPT call. Order matters.

| Trigger | Response |
|---|---|
| Message matches `\bNT\s*\d+` regex | `_NT_RESPONSE` — exact PDF text ("Good day to you. We are only able to process...") |
| Job/assignment seeker keywords | `_JOB_SEEKER_RESPONSE` — directs to website Tutor Registration |
| Fitness keywords | Route directly to `run_geraldine()` — never goes to FAQ agent |
| Plain `"thank you"` (exact) | "You are welcome, feel free to reach out anytime." |
| Phrases in `_GRATITUDE_WITH_CONTEXT` | "You are welcome, feel free to reach out anytime." |
| Post-completion + rate keywords | `run_geraldine()` with existing history (no state reset) |

## Critical Behaviour Rules

- **Silent messages**: farewells and standalone acks (`ok`, `thanks`, `bye`, `thx`, `ty`, etc.) always return `None`. Plain `"thank you"` (exact match) returns the warm acknowledgement instead of silence.
- **Owner commands**: owner number `919265335430` — `STOP <num>`, `RESET <num>`, `RESET ALL`. Non-command messages from owner fall through to normal pipeline. RESET ALL must be checked before `RESET ` prefix (order matters).
- **Optional fields**: male tutor preference and additional remarks are permanently optional — closed after form is sent once, never re-asked. Enforced in both `system_prompt.py` (PERMANENTLY_OPTIONAL_FIELDS section) and classifier prompts.
- **Complaint cycling**: 5 entries in `COMPLAINT_RESPONSES`; `complaint_count` on state selects index (capped at 4).
- **Completion detection**: `CLOSING_PHRASES` list scanned in GPT reply text triggers `_send_completion_summary()` to owner. Also triggered by `[[CONVERSATION_COMPLETE]]` tag in GPT reply.
- **Form template spacing**: blank line after every 2 questions (pairs), not every 1. Blank line between `Could you also share:` header and first question.
- **Language rules**: no contractions, no hyphens or dashes in any bot message. Enforced in both `FAQ_SYSTEM_PROMPT` and `SYSTEM_PROMPT`.
- **Owner summary**: category-aware — Piano/Violin/Fitness/Art/Academic/University each have their own field set in `_send_completion_summary()`.
- **IP stream flow**: after parent answers "IP" for stream → go DIRECTLY to IP pricing. No extra school or face-to-face questions before pricing.
- **Exact PDF responses**: NT, job seeker, fitness male rejection, fitness closing, group training, violin no-violin, package replies — all use word-for-word text from the client-approved PDF. Do NOT rephrase these.

## Lead Flow (Academic Tuition — do not break this)

1. Determine subject/level (ask if missing)
2. Send category form (name, postal, gender, stream where applicable)
3. Send pricing template matching exact level
4. Send closing message ("I have noted your requirements…")

The IP extra-questions rule (school + face-to-face before pricing) was intentionally removed — it broke this 4-step flow.

## Fitness-Specific Rules (system_prompt.py)

- Form header bold: `*May i have your:*` — individual field lines are NOT bold
- Male trainer request → "We regret to inform you that we are currently only accepting female students."
- Group training (first ask) → "Yes, group training can be arranged. May I check both your schedules and goals? I will also be able to advise on the group training rates accordingly." Only show full pros/cons + rates ($75/$105) when fees are explicitly asked.
- Package question → "I will check on the available package options and get back to you with the details."
- Closing → "I have noted your requirements and will be matching you with a fitness trainer profile. I will share the trainer's profile and credentials with you by this weekend, or possibly later today. Do keep an eye out for my message."

## Violin No-Violin Flow (system_prompt.py)

Step 1 (parent says no violin at home): "May i check if you will be getting a Violin as there will be homework and regular practicing is required after each lesson."
Step 2a (will look for one): "You can do a search at Shopee / Carousell or at a shop for Violin? [newline] If you are unsure of the size of the violin, you can bring your child to the music shop to test the size. [newline] May i have your thoughts?"
Step 2b (not getting one): "Unfortunately, the instructor does not have spare violins, as they come in various sizes. You will need to bring your child to be fitted for the appropriate size." → STOP.
Step 3 (confirms will buy, category not yet given): "There are 2 categories of tutors available. May i check will be your option(s)?" → proceed to violin pricing.

## Environment Variables

```
GROQ_API_KEY
WHATSAPP_ACCESS_TOKEN
WHATSAPP_PHONE_NUMBER_ID
WHATSAPP_VERIFY_TOKEN=nanyang_verify_2024
PORT=8000
```
