import os
import json
import re

from dotenv import load_dotenv
load_dotenv()

from fastapi import FastAPI, HTTPException, Query
from pydantic import BaseModel
from google.genai import types

from services import CarBotEngine

app = FastAPI(title="dubizzle Cars AI Assistant API")
engine = CarBotEngine()

MAX_HISTORY_TURNS = 6       # how many past turns to replay for short-term memory
MAX_TOOL_ITERATIONS = 4     # guard against infinite tool-call loops

COMPETITOR_BLOCKLIST = ["yallamotor", "carswitch", "drivearabia", "opensooq", "carsome"]


class ChatRequest(BaseModel):
    uid: str
    message: str


tools_spec = [
    {
        "name": "search_inventory",
        "description": "Search car listings in the dubizzle inventory by filters. Always use this before describing any specific car.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "make": {"type": "STRING"},
                "model": {"type": "STRING"},
                "year_min": {"type": "INTEGER"},
                "year_max": {"type": "INTEGER"},
                "price_min": {"type": "INTEGER"},
                "price_max": {"type": "INTEGER"},
                "q": {"type": "STRING", "description": "free text to match against description/trim"}
            }
        }
    },
    {
        "name": "book_slot",
        "description": "Book a viewing/test-drive slot for a specific listing id. Slots are only valid Monday-Saturday, 8am-8pm, format 'YYYY-MM-DD HH:MM'.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "lid": {"type": "INTEGER", "description": "the listing id to book"},
                "slot": {"type": "STRING", "description": "'YYYY-MM-DD HH:MM' 24h format"}
            },
            "required": ["lid", "slot"]
        }
    },
    {
        "name": "record_lead",
        "description": "Save/update the user's name, budget and stated needs/preferences as a qualified lead. Call this whenever the user shares budget or preference info, even mid-conversation.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "name": {"type": "STRING"},
                "budget": {"type": "STRING"},
                "needs": {"type": "STRING"}
            },
            "required": ["budget", "needs"]
        }
    }
]

SYS_PROMPT = """You are the official dubizzle Cars AI Assistant.
Rules:
1. Only help with buying, selling, or exploring cars from the dubizzle inventory provided via tools, booking viewings, and related automotive chit-chat.
2. Politely decline any non-automotive request (e.g. writing code, general trivia, unrelated tasks) and steer back to cars.
3. NEVER mention or compare to competitor platforms by name.
4. Viewing/test-drive slots are strictly Monday to Saturday, 8am to 8pm. Always propose slots in that window.
5. Never invent car listings, prices, or specs. Only describe cars returned by the search_inventory tool.
6. When the user mentions a budget, price range, or specific needs (e.g. "white SUV under 20k"), call record_lead to save it, even if they haven't asked to book anything yet.
7. Use the returning-user context (name/known preferences) naturally if provided, without being repetitive about it."""


def build_contents(uid, u, message):
    """Replay recent short-term history + long-term profile context, then the new message."""
    ctx_lines = [
        f"[Session context] User ID: {uid}.",
        f"Known name: {u.get('name') or 'unknown'}.",
        f"Known long-term preferences: {json.dumps(u.get('prefs') or {})}.",
    ]
    contents = [
        {"role": "user", "parts": [{"text": "\n".join(ctx_lines)}]},
        {"role": "model", "parts": [{"text": "Understood, I'll use this context."}]},
    ]

    recent = (u.get("history") or [])[-MAX_HISTORY_TURNS:]
    for turn in recent:
        contents.append({"role": "user", "parts": [{"text": turn["user"]}]})
        contents.append({"role": "model", "parts": [{"text": turn["assistant"]}]})

    contents.append({"role": "user", "parts": [{"text": message}]})
    return contents


def run_tool(fn_name, args, uid, u):
    if fn_name == "search_inventory":
        return engine.search_inventory(**args)
    if fn_name == "book_slot":
        return engine.book_slot(uid, args.get("lid"), args.get("slot"))
    if fn_name == "record_lead":
        if args.get("name"):
            u["name"] = args.get("name")
        prefs = u.setdefault("prefs", {})
        if args.get("budget"):
            prefs["budget"] = args.get("budget")
        if args.get("needs"):
            prefs["needs"] = args.get("needs")
        return engine.record_lead(uid, args.get("name") or u.get("name") or "unknown",
                                   args.get("budget"), args.get("needs"))
    return {"error": f"unknown tool {fn_name}"}


def sanitize_reply(text: str) -> str:
    if not text:
        return text
    lowered = text.lower()
    for name in COMPETITOR_BLOCKLIST:
        if name in lowered:
            return ("I can only speak to dubizzle's own listings and services, "
                    "so I can't comment on other platforms. How else can I help with your car search?")
    return text


@app.post("/api/chat")
def chat(req: ChatRequest):
    u = engine.get_user(req.uid)
    contents = build_contents(req.uid, u, req.message)

    config = types.GenerateContentConfig(
        system_instruction=SYS_PROMPT,
        tools=[{"function_declarations": tools_spec}],
        temperature=0.2,
    )

    last_tool_output = None
    reply_text = ""

    for _ in range(MAX_TOOL_ITERATIONS):
        resp = engine.client.models.generate_content(
            model="gemini-2.5-flash",
            contents=contents,
            config=config,
        )

        calls = resp.function_calls
        if not calls:
            reply_text = resp.text or ""
            break

        # Append the model's turn (the function call) then feed back each tool result
        model_parts = [{"function_call": fc} for fc in calls]
        contents.append({"role": "model", "parts": model_parts})

        response_parts = []
        for fc in calls:
            args = dict(fc.args or {})
            result = run_tool(fc.name, args, req.uid, u)
            last_tool_output = result
            response_parts.append(
                {"function_response": {"name": fc.name, "response": {"result": result}}}
            )
        contents.append({"role": "user", "parts": response_parts})
    else:
        reply_text = "Sorry, I had trouble completing that request. Could you rephrase?"

    reply_text = sanitize_reply(reply_text)

    hist = u.get("history", [])
    hist.append({"user": req.message, "assistant": reply_text})
    u["history"] = hist[-10:]
    engine.save_user(u)

    return {"response": reply_text, "tool_output": last_tool_output}


@app.get("/api/user/{uid}")
def get_user_profile(uid: str):
    return engine.get_user(uid)


@app.get("/api/inventory")
def get_inventory(
    make: str | None = None,
    model: str | None = None,
    year_min: int | None = None,
    year_max: int | None = None,
    price_min: int | None = None,
    price_max: int | None = None,
    q: str | None = None,
):
    return engine.search_inventory(
        make=make, model=model, year_min=year_min, year_max=year_max,
        price_min=price_min, price_max=price_max, q=q,
    )
