import json
from urllib.parse import quote_plus

from dotenv import load_dotenv
import anthropic

load_dotenv()


# ── Link builder ─────────────────────────────────────────────────────────────

def _build_booking_url(hotel: str, city: str, checkin: str, checkout: str, guests: int) -> str:
    ss = quote_plus(f"{hotel} {city}")
    return (
        f"https://www.booking.com/searchresults.html"
        f"?ss={ss}&checkin={checkin}&checkout={checkout}&group_adults={guests}"
    )


# ── System prompt ─────────────────────────────────────────────────────────────

def _system_prompt(itinerary: dict, preferences: dict) -> str:
    city = itinerary.get("destination", "")
    hotels = itinerary.get("hotels", [])
    hotel_list = "\n".join(
        f"  {i+1}. {h['name']} — {h['neighborhood']} — {h['price_range']} — {h['why']}"
        for i, h in enumerate(hotels)
    )

    return f"""You are a booking assistant for TripMind. Your only job: help the traveler book one hotel from their itinerary.

TRIP DETAILS:
- Destination: {city}
- Dates: {preferences.get('dates', 'TBD')}
- Party: {preferences.get('party', 'TBD')}
- Budget: {preferences.get('budget_signal', 'mid-range')}

ITINERARY HOTELS (only offer these, never invent):
{hotel_list}

YOUR FLOW:
1. Interpret which hotel the traveler wants — they may say "the second one", "the cheap one", "the Marais one", etc.
2. Confirm 4 parameters before acting:
   - Hotel name (exact, from the list)
   - Check-in date (YYYY-MM-DD)
   - Check-out date (YYYY-MM-DD)
   - Number of guests (integer)
   Derive defaults from their trip dates and party size where possible.
   If dates are vague (e.g. "5 days in July"), ask for a specific check-in date.
   If party implies a clear number (solo=1, couple=2), use it without asking.
3. After the traveler confirms the parameters, output EXACTLY this block — nothing else after it:

BOOKING_READY
{{"hotel": "<exact hotel name from list>", "city": "<destination>", "checkin": "<YYYY-MM-DD>", "checkout": "<YYYY-MM-DD>", "guests": <integer>}}

4. If the traveler declines, says "no thanks", or wants to skip, output EXACTLY this — nothing else:

BOOKING_DECLINED

GUARDRAILS:
- Never claim to have booked anything. You build a link; the traveler books on Booking.com themselves.
- Never claim to know live availability or prices. The link shows those.
- Only offer hotels from the list above.
- If the traveler's choice is ambiguous, ask — do not guess.
- If they edit (different hotel, different dates, more nights), adjust and re-confirm before outputting BOOKING_READY.
- If asked about restaurants or activities, explain this version covers hotels only (restaurants=OpenTable, activities=GetYourGuide — same pattern, not yet built).
- Keep responses short and conversational."""


# ── Agentic loop ──────────────────────────────────────────────────────────────

def run_booking_service(itinerary: dict, preferences: dict) -> tuple[bool, tuple[int, int]]:
    """
    Runs the booking agent loop.
    Returns (link_generated: bool, (total_input_tokens, total_output_tokens)).
    """
    client = anthropic.Anthropic()
    system = _system_prompt(itinerary, preferences)
    messages = []
    total_input = 0
    total_output = 0

    hotels = itinerary.get("hotels", [])
    names = " / ".join(h["name"] for h in hotels)
    opening = f"Would you like help booking one of your hotels? I have: {names}. Which one interests you — or would you prefer to skip?"
    print(f"\nAssistant: {opening}\n")
    messages.append({"role": "assistant", "content": opening})

    while True:
        user_input = input("You: ").strip()
        if not user_input:
            continue

        messages.append({"role": "user", "content": user_input})

        response = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=1024,
            system=system,
            messages=messages,
        )

        total_input  += response.usage.input_tokens
        total_output += response.usage.output_tokens
        reply = response.content[0].text
        messages.append({"role": "assistant", "content": reply})

        if "BOOKING_READY" in reply:
            raw_json = reply.split("BOOKING_READY", 1)[1].strip()
            # Defensive: grab only the JSON object in case of trailing text
            start = raw_json.index("{")
            end   = raw_json.rindex("}") + 1
            params = json.loads(raw_json[start:end])

            url = _build_booking_url(
                params["hotel"],
                params["city"],
                params["checkin"],
                params["checkout"],
                int(params["guests"]),
            )

            print(f"\nAssistant: Here's your pre-filled Booking.com link for {params['hotel']}:\n")
            print(f"  {url}\n")
            print("  Open that link to see live availability and complete your reservation.\n")
            return True, (total_input, total_output)

        if "BOOKING_DECLINED" in reply:
            print("\nAssistant: No problem — enjoy your trip!\n")
            return False, (total_input, total_output)

        print(f"\nAssistant: {reply}\n")


# ── Standalone test ───────────────────────────────────────────────────────────

if __name__ == "__main__":
    sample_itinerary = {
        "destination": "Paris",
        "hotels": [
            {
                "name": "Hôtel du Petit Moulin",
                "neighborhood": "Le Marais",
                "price_range": "$$$",
                "why": "Boutique hotel in a converted bakery — romantic, central, steps from the Picasso Museum.",
            },
            {
                "name": "Generator Paris",
                "neighborhood": "Oberkampf",
                "price_range": "$",
                "why": "Stylish budget option with a rooftop bar, great for travellers who want to explore at night.",
            },
            {
                "name": "Hôtel Plaza Athénée",
                "neighborhood": "8th arrondissement",
                "price_range": "$$$$",
                "why": "Iconic luxury hotel on Avenue Montaigne — the gold standard of Paris.",
            },
        ],
    }

    sample_preferences = {
        "dates": "July 10–15, 2026",
        "party": "couple",
        "budget_signal": "mid-range",
    }

    booked, usage = run_booking_service(sample_itinerary, sample_preferences)
    print(f"Session ended. Link generated: {booked}. Tokens used: input={usage[0]:,} output={usage[1]:,}")
