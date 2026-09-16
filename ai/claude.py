import json

from anthropic import Anthropic


def create_client(api_key):
    return Anthropic(api_key=api_key)


def analyse_email(client, email):
    prompt = f"""
You are a careful personal secretary analysing an email for Ben.

Your job is to help Ben identify emails that genuinely require his attention.
Do not treat an email as requiring action merely because it contains information.

EMAIL
From: {email['sender']}
Subject: {email['subject']}
Date: {email['date']}

Body:
{email['body']}

Return ONLY valid JSON with exactly these fields:

{{
    "category": "Tutoring",
    "priority": "Medium",
    "action_required": true,
    "reply_needed": true,
    "availability_request": false,
    "requested_day": null,
    "requested_start": null,
    "requested_end": null,
    "summary": "A short summary of the email."
}}

CATEGORY

Choose exactly one:

University
Tutoring
Personal
Finance
Shopping
Newsletter
Marketing
Work
Travel
Other

PRIORITY

High:
The email is genuinely important or time-sensitive and should probably
be dealt with soon.

Medium:
The email requires some attention but is not urgent.

Low:
The email is useful information but does not need prompt attention.

ACTION REQUIRED

Set this to true ONLY when Ben actually needs to do something.

Examples:
- Someone asks Ben a question → true
- Someone asks Ben to confirm something → true
- A university deadline requires work → true
- A receipt arrives → false
- A newsletter arrives → false
- Marketing arrives → false
- An automated notification that requires no response → false

REPLY NEEDED

Set this to true ONLY when Ben would reasonably be expected
to reply to the sender.

Examples:
- Someone asks Ben a direct question → true
- Someone asks Ben to confirm something → true
- A parent enquires about a tutoring lesson → true
- A university announces a deadline → false
- A receipt arrives → false
- A newsletter arrives → false
- Marketing email → false

If action_required is false, reply_needed must also be false.

AVAILABILITY REQUEST

Set this to true ONLY if the email is asking about Ben's availability
for a specific activity, appointment, meeting, lesson or similar.

If true, extract the requested time period where possible.

REQUESTED DAY

Use the day of the week, for example:

"Sunday"

If no day is specified, use null.

REQUESTED START / REQUESTED END

Use 24-hour HH:MM format.

For example, if someone asks whether Ben is free Sunday afternoon,
use:

"12:00"
"17:00"

If a precise time cannot be determined, use a sensible interpretation
of the requested period.

If this is not an availability request, both values must be null.

SUMMARY

Summarise the important information in no more than three sentences.
Focus on what Ben actually needs to know or do.

Do not include markdown.
Do not include ```json.
Return only the JSON object.
"""

    message = client.messages.create(
        model="claude-sonnet-5",
        max_tokens=400,
        messages=[
            {
                "role": "user",
                "content": prompt
            }
        ]
    )

    for block in message.content:
        if block.type == "text":
            try:
                text = block.text.strip()

                if text.startswith("```"):
                    text = text.replace("```json", "")
                    text = text.replace("```", "")
                    text = text.strip()

                return json.loads(text)

            except json.JSONDecodeError:
                return {
                    "error": "Claude returned invalid JSON",
                    "raw_response": block.text
                }

    return {
        "error": "Claude returned no text response"
    }


def draft_reply(client, email, calendar_availability=None):
    if calendar_availability:
        availability_text = "\n".join(
            f"- {start}–{end}"
            for start, end in calendar_availability
        )
    else:
        availability_text = "No availability found."

    prompt = f"""
You are drafting an email reply on behalf of Ben.

Write a natural, concise and polite reply to the email below.

EMAIL
From: {email['sender']}
Subject: {email['subject']}

Body:
{email['body']}

CALENDAR AVAILABILITY

{availability_text}

IMPORTANT RULES:

- Write only the reply itself.
- Do not include analysis or explanations.
- Do not invent facts, commitments, dates, prices or availability.
- If calendar availability is provided, use it when relevant.
- If the email asks about availability, only offer times shown in
  CALENDAR AVAILABILITY.
- Do not claim Ben is available at any other time.
- If no availability is provided, use a placeholder such as
  [availability] rather than inventing a time.
- Match the level of formality of the original email.
- Keep the reply concise unless the email clearly requires a detailed response.
- Sign off as:

Best,
Ben
"""

    message = client.messages.create(
        model="claude-sonnet-5",
        max_tokens=500,
        messages=[
            {
                "role": "user",
                "content": prompt
            }
        ]
    )

    for block in message.content:
        if block.type == "text":
            return block.text.strip()

    return "[Claude returned no draft]"