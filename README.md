# Dubizzle Cars AI Assistant

## Overview

This project is a conversational AI assistant for the dubizzle Cars marketplace. It allows users to search the provided car inventory using natural language, ask follow-up questions about listings, book viewing slots, and remember user preferences across multiple sessions.

The backend is built with FastAPI and uses Gemini 2.5 Flash with function calling for intent recognition. A lightweight Streamlit application is used as the client interface.

---

## Features

- Natural language car inventory search
- Gemini 2.5 Flash function calling
- Multi-turn conversations with short-term memory
- Persistent user memory using SQLite
- Vehicle viewing/test-drive booking
- Lead qualification with CSV export
- FastAPI REST API
- Streamlit chat interface
- Automotive-only guardrails with competitor filtering

---

## Project Structure

```
.
├── app.py              # Streamlit frontend
├── main.py             # FastAPI backend
├── services.py         # Business logic
├── cars.csv            # Vehicle inventory
├── app.db              # SQLite database (created automatically)
├── leads.csv           # Qualified leads (created automatically)
├── pyproject.toml
├── uv.lock
└── README.md
```

---

## Architecture

```
                Streamlit UI
                     │
                     ▼
             FastAPI Backend
                     │
     ┌───────────────┼────────────────┐
     │               │                │
     ▼               ▼                ▼
 Gemini API      SQLite DB        cars.csv
(Function Calling)  (Memory)      (Inventory)
                     │
                     ▼
              leads.csv (Lead Storage)
```

---

## Setup

### 1. Clone the repository

```bash
git clone <repository-url>
cd dubizzle-car-assistant
```

### 2. Install dependencies

```bash
uv sync
```

### 3. Create a `.env` file

```
GEMINI_API_KEY=your_api_key_here
```

You can get a free API key from Google AI Studio.

### 4. Start the backend

```bash
uv run uvicorn main:app --reload
```

### 5. Start the Streamlit application

Open another terminal and run:

```bash
uv run streamlit run app.py
```

---

## Implementation

The assistant uses Gemini 2.5 Flash with function calling to identify the user's intent. Inventory-related requests are converted into structured search parameters and executed against the local car dataset using pandas. This keeps every response grounded in the provided inventory and prevents the model from inventing listings.

Short-term memory is maintained by replaying recent conversation history, allowing users to ask follow-up questions naturally. Long-term memory is implemented using SQLite, where user names, preferences, and recent conversations are stored. Qualified leads are also recorded in a CSV file whenever users share their budget or vehicle requirements.

---

## Design Decisions

### Streamlit

I chose Streamlit because it provides a clean conversational interface with very little setup, making it ideal for demonstrating multi-turn conversations and returning-user memory.

### Retrieval Method

Since the provided dataset contains only around 100 vehicle listings, I chose pandas filtering instead of a vector database. This keeps the implementation simple while ensuring every response comes directly from the provided inventory.

### Memory

SQLite was used for persistent user memory because it requires no additional services and is sufficient for storing user profiles, conversation history, and preferences across sessions.

---

## Future Improvements

Some features that could be added in a production system include:

- Semantic search using embeddings for larger inventories
- Authentication instead of simple user identification
- Preventing double-booking of viewing slots
- Improved ranking of search results
- Streaming responses in the chat interface
- Calendar integration for booking confirmations

---

## Demonstration

### Multi-turn Conversation

![Multi-turn Conversation](images/multiturn.png)

The assistant successfully searches the inventory, remembers the selected vehicle, answers follow-up questions, and books a viewing slot.

---

### Returning User Memory

![Returning User](images/memory.png)

The assistant recognizes a returning user, recalls previous preferences, and continues the conversation using information stored from an earlier session.
