import asyncio
import os
import logging
import random

from openai import AsyncOpenAI

from system_prompt import SYSTEM_PROMPT
import state as st

logger = logging.getLogger(__name__)

client = AsyncOpenAI(api_key=os.getenv("OPENAI_API_KEY", "").strip())
OWNER_NUMBER = "919265335430"

# Exact messages from n8n workflow
COMPLAINT_RESPONSES = [
    "For this matter, please allow our Senior Education Consultant to get back to you shortly.",
    "I am still working on your request at the moment. Thank you for your patience and our Senior Education Consultant will get back to you very soon.",
    "Just to assure you, I am actively working on your request and will update you as soon as I can",
]

# Same 3 messages used as fallback for OTHER / IGNORE (matches n8n Pick Fallback Message node)
FALLBACK_MESSAGES = COMPLAINT_RESPONSES

CLOSING_PHRASES = [
    "noted down your requirements",
    "sending a list of the most suitable tutor profiles",
    "keep an eye out for my messages",
]

FAQ_SYSTEM_PROMPT = """You are Geraldine Goh, Senior Education Consultant at Nanyang Tuition (a subsidiary of Nanyang Learning Pte Ltd). You are NOT a bot. Parents must feel like they are speaking directly with Geraldine — warm, human, and genuinely helpful.
Website: www.nanyangtuition.com

<WHATSAPP_FORMATTING>
Bold: *text*
Italic: _text_
Use emojis naturally — they should feel warm, not decorative.
</WHATSAPP_FORMATTING>

<HOW_TO_WRITE>
Write exactly like a real consultant texting on WhatsApp.

- Break your reply into short natural chunks — one thought per line, then a line break
- Do NOT write one long paragraph
- Do NOT use bullet points unless listing 3 or more items (like a rate list)
- Do NOT end your reply with a question. Just answer what was asked and stop.
- Emojis go inside the sentence or at the end of a thought, naturally
- Never start with "Great question!" or any filler
- Warm, human, real — not structured, not robotic
</HOW_TO_WRITE>

<SIGNATURE>
Use only when wrapping up or sharing full information:
Geraldine Goh
*Nanyang Tuition*
www.nanyangtuition.com
_A Subsidiary of Nanyang Learning Pte Ltd_
</SIGNATURE>

<ABOUT>
- Est. 2006 | 30,000+ families helped in Singapore
- One-to-one home and online tuition
- No Admin Fees | No GST | No Deposits | No Upfront Payment | No Contract
- Fees postpaid after every 2nd or 4th week of lessons
- Contact: WhatsApp +65 8298 7978 | www.nanyangtuition.com
</ABOUT>

<FAQ_RESPONSES>
These are example replies. Write in this style — natural, warm, broken into short thoughts with line breaks.

Different from a tuition centre?

We provide one-to-one personalised home lessons, so the tutor focuses entirely on your child. 😊

Unlike a tuition centre, there's no fixed group pace — the tutor adjusts fully to your child's school syllabus, learning speed, and specific weak areas.

Most students tend to progress much faster this way.

---

How long to find a tutor?

Usually within 1 to 3 working days, depending on the subject, level, and location. 😊

We'll reach out as soon as we've shortlisted the most suitable profiles for your consideration.

---

Can I change tutors?

Yes, absolutely — no contract binding at all. 😊

If at any point you feel the tutor isn't the right fit, just let us know and we'll arrange a replacement.

What matters most is that your child benefits from the lessons. You can have peace of mind.

---

Any hidden fees?

No hidden charges at all. 😊

*No Admin Fees | No GST | No Deposits | No Upfront Payment | No Contract Binding.*

Fees are only paid after lessons are conducted — postpaid at the end of every 2nd or 4th week.

---

Do you offer a trial lesson?

Normally we will not practise trial lesson.

However, should you find the tutor's teaching method is not suitable after the first lesson, you may terminate the tutor immediately through the agency. You are required to make the one lesson fee to the agency for termination.

Otherwise, the tuition will continue as per arranged weekly. 😃

You may wish to see this as a trial.

---

How long before we see results?

It really depends on your child's current level and the gaps involved.

Most students begin to show better understanding and confidence within a few weeks of consistent lessons. Academic results typically improve over one to two months, especially with regular practice. 😊

---

Is online tuition effective?

Yes, it can be just as effective as face-to-face lessons! 😊

Many students find it more convenient too — it saves travelling time and allows more flexible scheduling.

The tutor still provides full one-to-one attention throughout.

---

What qualifications do your tutors have?

Our tutors range from MOE and NIE-trained school teachers to experienced full-time tutors, degree graduates, and university undergraduates. 😊

Each tutor is carefully screened based on their qualifications, teaching experience, and background in the relevant subject and level.

---

Do you cover AEIS / SPERS / JPACT?

Yes! We have tutors who specialise in Singapore school entrance exams including AEIS, S-AEIS, SPERS, and JPACT — for both local and international students. 😊

---

What are the rates?

Rates depend on the level, subject, and tutor category. As a general guide:

- *Primary:* $30–$80/hr
- *Secondary:* $35–$85/hr
- *Junior College:* $45–$150/hr

---

How does payment work?

After the 2nd lesson, the agency fee (50% of the agreed monthly fee) is paid to Nanyang Learning.

From the 4th lesson onwards, you pay the tutor directly at the end of every 4 lessons. 😊

No upfront payment, no deposit, no contract.

---

My child tried tutors before and it didn't work.

I completely understand — and I hear you. 😊

Sometimes the issue isn't tutoring itself, it's finding the right match. We take time to understand your child's learning style before recommending anyone.

And if it doesn't feel right after the first lesson, you can replace the tutor immediately. No stress.

---

Can lessons be at home?

Yes, all lessons are conducted at your home unless you prefer online. 😊

The tutor travels to you at the scheduled time. There are no extra travel charges.

</FAQ_RESPONSES>

<OFF_TOPIC>
If asked about anything unrelated to tuition:
"I'm here to help with your tuition needs. For other matters, please allow our Senior Education Consultant to get back to you within one (1) working day. 😊"
</OFF_TOPIC>

<NEVER>
- End replies with a question
- Write one long unbroken paragraph
- Use bullet points for normal answers
- Say "Guaranteed grades" or anything salesy
- Sound like a chatbot or customer service script
</NEVER>
"""

CLASSIFIER_SYSTEM = """You are a classifier for a tutoring business WhatsApp chatbot. Classify the message into ONE category.

DEFAULT to NEW_PARENT for any ambiguous message.

SHORTHAND – these are all valid NEW_PARENT messages:
- hrs/hr/h/2hr/1.5hrs = lesson duration
- ft/full time/FT = full-time tutor category
- uni/university = university student tutor
- p1-p6/pri 1-pri 6 = Primary levels
- s1-s4/sec1-sec4 = Secondary levels
- jc/jc1/jc2 = Junior College
- eng/math/maths/sci/chi/chem/bio/phys = subjects
- per wk/pw/3x/4x/once a week/twice a week = lessons per week
- ok/yes/no/sure/can/done/thanks = short replies in conversation
- Any number + subject + level combo = NEW_PARENT

NEW_PARENT – greetings, service questions, sharing child details, shorthand replies, ANY ambiguous message
COMPLAINT_URGENT – ONLY if explicitly: cancel class, refund, complaint about tutor, technical issue
FAQ – any question about whether a service is available, what subjects or levels are offered, pricing, or any information-seeking without sharing specific personal enrollment details. Examples: "Do you provide X?", "Do you have Y classes?", "Do you teach piano?", "How much does it cost?" — ALL treated as FAQ
OTHER – tutor asking about assignments, business partnership, nothing else fits

WHEN IN DOUBT: NEW_PARENT.

Respond ONLY: NEW_PARENT or COMPLAINT_URGENT or FAQ or OTHER"""

POST_COMPLETE_CLASSIFIER_SYSTEM = """This person's tuition enquiry was already completed. They have been told we will get back to them.

Classify their NEW message into ONE category:

WANTS_NEW_TUTOR – wants tuition for a NEW subject or different level. Keywords: another subject, also want, new tutor, additional, english also, maths too.

COMPLAINT_URGENT – cancel class, refund, complaint about tutor, technical issue.

FAQ – asking a question about services, pricing, scheduling, tutors, AEIS, online lessons, special needs.

IGNORE – casual follow-ups, thank you messages, ok noted.

Respond with ONLY one word: WANTS_NEW_TUTOR or COMPLAINT_URGENT or FAQ or IGNORE"""


# ── FAQ agent has its own per-user memory (separate from Geraldine) ──────────
_faq_history: dict[str, list[dict]] = {}


async def _classify(system: str, text: str) -> str:
    resp = await client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": text},
        ],
        temperature=0,
        max_tokens=15,
    )
    return resp.choices[0].message.content.strip().upper()


async def classify_new_message(text: str) -> str:
    return await _classify(CLASSIFIER_SYSTEM, text)


async def classify_post_completion(text: str) -> str:
    return await _classify(POST_COMPLETE_CLASSIFIER_SYSTEM, text)


def _is_complete(reply: str) -> bool:
    low = reply.lower()
    has_tag = "[[conversation_complete]]" in low
    has_phrase = any(p in low for p in CLOSING_PHRASES)
    return has_tag or has_phrase


async def run_geraldine(wa_id: str, text: str) -> str:
    user_state = st.get_state(wa_id)
    user_state.history.append({"role": "user", "content": text})

    resp = await client.chat.completions.create(
        model="gpt-4o",
        messages=[{"role": "system", "content": SYSTEM_PROMPT}] + user_state.history,
        temperature=0.3,
    )

    reply = resp.choices[0].message.content or ""
    user_state.history.append({"role": "assistant", "content": reply})

    if _is_complete(reply):
        clean = reply.replace("[[CONVERSATION_COMPLETE]]", "").strip()
        user_state.status = st.Status.COMPLETED
        asyncio.create_task(_send_completion_summary(wa_id, list(user_state.history)))
        return clean

    return reply


async def run_faq(wa_id: str, text: str) -> str:
    if wa_id not in _faq_history:
        _faq_history[wa_id] = []
    _faq_history[wa_id].append({"role": "user", "content": text})

    resp = await client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role": "system", "content": FAQ_SYSTEM_PROMPT}] + _faq_history[wa_id][-10:],
        temperature=0.3,
    )
    reply = resp.choices[0].message.content or ""
    _faq_history[wa_id].append({"role": "assistant", "content": reply})
    return reply


def _detect_urgency(text: str) -> str:
    low = text.lower()
    if any(w in low for w in ["cancel", "refund", "urgent", "immediately", "scam"]):
        return "HIGH"
    if any(w in low for w in ["question", "wondering", "just asking"]):
        return "LOW"
    return "MEDIUM"


async def handle_complaint(wa_id: str, text: str) -> str:
    user_state = st.get_state(wa_id)
    user_state.complaint_count += 1
    idx = min(user_state.complaint_count - 1, len(COMPLAINT_RESPONSES) - 1)
    urgency = _detect_urgency(text)

    # Notify owner on EVERY complaint (matches n8n — no threshold)
    asyncio.create_task(_notify_owner_complaint(wa_id, text, urgency, user_state.complaint_count))

    return COMPLAINT_RESPONSES[idx]


async def _notify_owner_complaint(wa_id: str, complaint_text: str, urgency: str, count: int):
    from whatsapp import send_message
    msg = (
        f"⚠️ *Complaint Received*\n\n"
        f"*Phone:* +{wa_id}\n"
        f"*Urgency:* {urgency}\n"
        f"*Complaint #:* {count}\n\n"
        f"*Message:*\n{complaint_text}"
    )
    try:
        await send_message(OWNER_NUMBER, msg)
        logger.info(f"Complaint notification sent to owner for {wa_id} (#{count}, {urgency})")
    except Exception as e:
        logger.error(f"Failed to send complaint notification: {e}")


async def _send_completion_summary(wa_id: str, history: list[dict]):
    from whatsapp import send_message
    summary_prompt = (
        f"Read the conversation below. This parent's conversation is now complete.\n\n"
        f"CRITICAL RULES:\n"
        f"- Extract ONLY what the parent actually said. Word for word where possible.\n"
        f"- Do NOT infer, guess, or add anything the parent did not explicitly state.\n"
        f"- If a field was not mentioned, write: Not provided\n\n"
        f"Output EXACTLY:\n\n"
        f"*New Lead Summary:*\n\n"
        f"*Name:* [name]\n"
        f"*Phone:* +{wa_id}\n"
        f"*Postal Code:* [postal code]\n\n"
        f"*Student Gender:* [gender]\n"
        f"*Level:* [level]\n"
        f"*Subject(s):* [subjects]\n\n"
        f"*Tutor Preference:* [category]\n"
        f"*Lesson Duration:* [duration]\n"
        f"*Lessons Per Week:* [number]\n"
        f"*Male Tutor:* [Yes/No/Not mentioned]\n"
        f"*Remarks:* [exact words from parent or: Not provided]\n\n"
        f"Bold labels with *asterisks*. Blank lines between sections.\n\n"
        f"Conversation:\n"
        + "\n".join(f"{m['role'].upper()}: {m['content']}" for m in history)
    )
    try:
        resp = await client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {
                    "role": "system",
                    "content": "You are a data extraction assistant for Nanyang Tuition. Read the FULL conversation. Details were shared across multiple messages. Extract everything. Use *asterisks* for bold.",
                },
                {"role": "user", "content": summary_prompt},
            ],
            temperature=0.2,
        )
        summary = resp.choices[0].message.content or ""
        owner_msg = f"⚠️ *New Enquiry Summary*\n\n{summary}"
        await send_message(OWNER_NUMBER, owner_msg)
        logger.info(f"Completion summary sent to owner for {wa_id}")
    except Exception as e:
        logger.error(f"Failed to send completion summary: {e}")


async def process_message(wa_id: str, text: str) -> str | None:
    user_state = st.get_state(wa_id)

    # ── Post-completion routing ───────────────────────────────────────────────
    if user_state.status == st.Status.COMPLETED:
        category = await classify_post_completion(text)
        logger.info(f"Post-completion [{wa_id}]: {category}")

        if category == "WANTS_NEW_TUTOR":
            st.reset_conversation(wa_id)
            return await run_geraldine(wa_id, text)
        elif category == "COMPLAINT_URGENT":
            return await handle_complaint(wa_id, text)
        elif category == "FAQ":
            return await run_faq(wa_id, text)
        else:
            # IGNORE → send a fallback (matches n8n Pick Fallback Message node)
            return random.choice(FALLBACK_MESSAGES)

    # ── Active conversation — classify EVERY message ──────────────────────────
    category = await classify_new_message(text)
    logger.info(f"Classify [{wa_id}]: {category}")

    if category == "COMPLAINT_URGENT":
        return await handle_complaint(wa_id, text)
    elif category == "FAQ":
        return await run_faq(wa_id, text)
    elif category == "OTHER":
        # Other (business partner, tutor inquiry) → fallback (matches n8n)
        return random.choice(FALLBACK_MESSAGES)
    else:
        # NEW_PARENT (or ambiguous default)
        return await run_geraldine(wa_id, text)
