# TripMind — Project Context

TripMind is a conversational travel agent built from independent services, deployed as a web app.

## Terminology

**Two different questions, two different words:**

- **Service** — an ARCHITECTURAL role: a deployable unit with one responsibility and a clear interface. Describes structure and boundaries. Everything here is a service.
- **Agent** — an internal MECHANISM: the component relies on LLM decisioning to choose its actions (reasons, loops, decides what to do next). Describes what is inside.

These are not in tension. A component can be a **service** (architectural role) whose **internals are agentic** (mechanism).

- **Function** — pure plumbing: takes input, transforms it, returns output. No reasoning. (Renderers.)

## Architecture

**Intake Service** (`intake_service.py`)
Conversation to extract travel preferences. Fixed-flow internals.

**Search + Format Service** (`search_format_service.py`)
Searches Google Places, returns a structured itinerary (dict). Fixed pipeline.

**Renderers** (`renderers.py`)
Functions: `render_terminal(itinerary)` and `render_pdf(itinerary)`.

**Cost Tracking** (`track_cost.py`)
Calculates and displays API cost per run.

**Main** (`main.py`)
Terminal entry point: intake -> search -> render -> cost summary.

**Web App** (`app.py`) — the deployment layer
Gradio chat interface that calls the SAME services. The services do not change.

## Environment

Local (`.env`, never committed):
- `ANTHROPIC_API_KEY`
- `GOOGLE_PLACES_API_KEY`

Deployed: the same keys go in the Hugging Face Space Secrets panel. Never in source control.

## Tech Stack

- Python 3
- Anthropic API (model: `claude-sonnet-4-6`)
- Google Places API
- Gradio (web interface)
- Hugging Face Spaces (hosting, ZeroGPU free tier)
- `spaces` package (required by ZeroGPU — see Deployment Gotchas)

---

## Intake Service — Spec

**Goal:** Extract trip preferences through natural conversation.

**Asks (one at a time, not as a form):** destination, dates/duration, party size, pace, food preferences (optional), activity preferences (optional).

**Infers:** budget signal (backpacker / mid-range / luxury) from context. Never asks directly.

**Stops when it has:** destination, dates, party, pace, budget.

**Output:** a preferences dict.

**Guardrails:**
- Vague destination ("somewhere warm") -> ask for a specific city
- Off-topic -> redirect to trip planning
- Booking request -> "I can't book yet, but I'll show you where to book"
- Keep responses short and natural

**Important for the web version:** the service must work turn-by-turn (given the conversation so far, return the next question OR signal that extraction is complete). It cannot rely on a blocking `input()` loop.

---

## Search + Format Service — Spec

**Goal:** Search real places, return a structured itinerary (data, not a printed string).

**Input:** preferences dict.

**Search:**
- Hotels: Google Places type "lodging", filter by budget
- Restaurants: Google Places type "restaurant", filter by cuisine
- Activities: Google Places types "tourist_attraction", "museum", "park"
- Destination overview + tips: Claude's knowledge

**Output:** structured dict:
```python
{
    "destination": "Paris",
    "overview": "...",
    "hotels": [{"name","neighborhood","price_range","why"}],       # 3
    "restaurants": [{"name","cuisine","price_range","why"}],       # 4-5
    "activities": [{"name","category","why","tip"}],               # 6-8
    "practical_tips": ["..."]                                       # 3-5
}
```

**Guardrails:**
- Only return REAL places from the API; never invent
- No results in budget -> offer alternatives, flag it
- Impossible budget -> flag and suggest alternatives
- Explain WHY each recommendation

---

## Renderers — Functions, Not Services

`render_terminal(itinerary)` — prints to terminal.

`render_pdf(itinerary)` — writes a PDF via reportlab/fpdf2.
- Save to `itineraries/{destination}_{timestamp}.pdf`
- `os.makedirs("itineraries", exist_ok=True)`
- Returns the file path (so the web app can offer it as a download)

Architecture principle: a service or agent reasons. A renderer just formats. Do not make rendering a service.

---

## Cost Tracking

```python
INPUT_COST_PER_1M = 3.00
OUTPUT_COST_PER_1M = 15.00

def calculate_cost(input_tokens, output_tokens):
    return (input_tokens / 1_000_000 * INPUT_COST_PER_1M +
            output_tokens / 1_000_000 * OUTPUT_COST_PER_1M)
```

Accumulate tokens across service calls; display cost per run and extrapolated to 10,000 users.

---

## Web App (`app.py`) — Deployment Layer

**The key principle:** the services do NOT change. `app.py` is a thin web layer that calls the same
`intake_service` and `search_format_service` the terminal version calls. This is the payoff of
decomposition — the logic was never tangled up with the terminal I/O, so it ports cleanly.

**Framework:** Gradio, using `gr.ChatInterface` — preserves the conversational UX (a chat, not a form).

**State handling:** the terminal version loops with `input()`. Gradio is event-driven: each user
message calls a function with `(message, history)`. So the app must hold conversation state across
turns using `gr.State`:
- The conversation so far
- The preferences extracted so far
- Whether intake is complete

**Flow:**