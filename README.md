# dubizzle Cars AI Assistant

An AI assistant that lets users explore a car inventory, get contextual multi-turn
answers, book viewing slots, and get remembered across sessions.

## Quick Setup

### Prerequisites
- Python 3.10+, `uv` installed (`pip install uv`)
- A free Gemini API key from Google AI Studio
- Replace `cars.csv` with the provided dataset if different from the sample included here
  (headers are auto-lowercased and an `id` column is auto-generated if missing, so most
  reasonable CSV layouts will work out of the box)

```bash
export GEMINI_API_KEY="your_api_key_here"
# or put it in a .env file: GEMINI_API_KEY=your_api_key_here
```

### Install deps
```bash
uv sync
```

### Run the backend
```bash
uv run uvicorn main:app --reload --port 8000
```

### Run the Streamlit client (separate terminal)
```bash
uv run streamlit run app.py
```

Open the Streamlit URL, enter a User ID in the sidebar (e.g. `usr_101`), and chat.
To test long-term memory recall, chat as `usr_101`, mention a preference/budget,
close the tab, reopen, and re-enter the same User ID — the sidebar and the model's
replies should reflect what it remembers.

## Why these choices

**Client:** Streamlit was chosen over a notebook because it gives a real chat UI
(message bubbles, spinner, sidebar identity switch) that makes it trivial to demo
both short-term context and cross-session recall live, which matters most for the
"screenshot the conversation" requirement.

**Retrieval:** Given ~100 rows with a mix of structured columns (make/model/year/price)
and one free-text description field, plain pandas filtering + one `q` full-text
parameter was chosen over a vector DB. At this scale a vector index adds latency and
setup cost without improving accuracy — the filters can be combined precisely by the
model via function calling, and grounding is guaranteed because the model only ever
sees rows the tool actually returned (no hallucinated inventory).

**Memory:** Short-term memory is handled by replaying the last few turns of the
current session's conversation back into the Gemini `contents` array on every call
(not just storing them unused). Long-term memory uses a single SQLite table keyed by
`uid` storing `name`, `prefs` (JSON), and a rolling window of recent `history`
(JSON) — simple, inspectable, and durable across process restarts, which is enough
for the "returning user" requirement without needing a dedicated memory service.

**Guardrails:** Enforced at two levels — the system prompt instructs the model to
stay on-topic, decline non-automotive requests, and never name competitors, and a
lightweight backend post-filter (`sanitize_reply`) blocks any competitor name that
slips through before the response is returned. Booking slots are validated in code
(`validate_slot`), not just prompted, so the model can't hallucinate an out-of-hours
slot into the bookings table.

## Out of scope / possible extensions
Given the time constraint, a few things were intentionally left out: multi-tool-call
still runs in a bounded loop (max 4 iterations) rather than a full agent loop with
retries/backoff; there's no auth on the API (uid is trusted as given); the vector/RAG
option was skipped in favor of pandas filtering as described above; and lead scoring/
qualification is just recorded, not scored or routed anywhere. A production version
would add: proper auth + rate limiting, a real vector index if the catalog grows past
a few thousand listings, streaming responses in the UI, and a background job to
summarize/prune long history instead of a fixed 10-turn window.

## Project structure
```
main.py       - FastAPI app: /api/chat, /api/user/{uid}, /api/inventory
services.py   - CarBotEngine: inventory search, SQLite persistence, booking, leads
app.py        - Streamlit chat client
cars.csv      - Sample inventory (swap in the provided dataset if different)
```
