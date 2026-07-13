import json
import os
import requests
from dotenv import load_dotenv
import anthropic

load_dotenv()

GOOGLE_KEY = os.getenv("GOOGLE_PLACES_API_KEY")
PLACES_URL = "https://maps.googleapis.com/maps/api/place/textsearch/json"

# Maps budget signal to (min_price_level, max_price_level) — Google scale 0-4
BUDGET_PRICE_RANGE = {
    "backpacker": (0, 2),
    "mid-range":  (1, 3),
    "luxury":     (3, 4),
}


def _search(query: str, place_type: str) -> list[dict]:
    params = {"query": query, "type": place_type, "key": GOOGLE_KEY}
    resp = requests.get(PLACES_URL, params=params, timeout=10)
    resp.raise_for_status()
    return resp.json().get("results", [])


def _price_symbol(level: int | None) -> str:
    if level is None:
        return "N/A"
    return "$" * level if level > 0 else "Free"


def _filter_by_budget(places: list[dict], budget: str, min_rating: float = 4.0) -> list[dict]:
    lo, hi = BUDGET_PRICE_RANGE.get(budget, (0, 4))
    out = []
    for p in places:
        if p.get("rating", 0) < min_rating:
            continue
        level = p.get("price_level")
        if level is None or lo <= level <= hi:
            out.append(p)
    return out


def _format_for_prompt(places: list[dict]) -> str:
    lines = []
    for p in places:
        name = p.get("name", "?")
        addr = p.get("formatted_address", p.get("vicinity", "N/A"))
        rating = p.get("rating", "N/A")
        price = _price_symbol(p.get("price_level"))
        lines.append(f"- {name} | {addr} | Rating: {rating} | Price: {price}")
    return "\n".join(lines) if lines else "(no results)"


def _gather_places(destination: str, preferences: dict) -> tuple[str, str, str, list[str]]:
    budget = preferences.get("budget_signal", "mid-range").lower()
    food_prefs = preferences.get("food_preferences", "")
    activity_prefs = preferences.get("activity_preferences", "")
    warnings = []

    # Hotels
    raw_hotels = _search(f"hotels in {destination}", "lodging")
    hotels = _filter_by_budget(raw_hotels, budget)[:5]
    if not hotels:
        hotels = sorted(raw_hotels, key=lambda p: p.get("rating", 0), reverse=True)[:5]
        warnings.append(f"No hotels found matching '{budget}' budget — showing top-rated alternatives.")

    # Restaurants
    food_qualifier = f"{food_prefs} " if food_prefs and food_prefs.lower() != "none specified" else ""
    raw_restaurants = _search(f"{food_qualifier}restaurants in {destination}", "restaurant")
    restaurants = _filter_by_budget(raw_restaurants, budget)[:7]
    if not restaurants:
        restaurants = sorted(raw_restaurants, key=lambda p: p.get("rating", 0), reverse=True)[:7]
        warnings.append(f"No restaurants found matching '{budget}' budget — showing top-rated alternatives.")

    # Activities — three searches merged and deduplicated
    activity_qualifier = f"{activity_prefs} " if activity_prefs and activity_prefs.lower() != "none specified" else ""
    raw_attractions = _search(f"{activity_qualifier}tourist attractions in {destination}", "tourist_attraction")
    raw_museums = _search(f"museums in {destination}", "museum")
    raw_parks = _search(f"parks in {destination}", "park")

    seen_ids: set[str] = set()
    merged: list[dict] = []
    for p in raw_attractions + raw_museums + raw_parks:
        pid = p.get("place_id")
        if pid and pid not in seen_ids:
            seen_ids.add(pid)
            merged.append(p)

    activities = [p for p in merged if p.get("rating", 0) >= 4.0][:12]
    if not activities:
        activities = sorted(merged, key=lambda p: p.get("rating", 0), reverse=True)[:12]

    return (
        _format_for_prompt(hotels),
        _format_for_prompt(restaurants),
        _format_for_prompt(activities),
        warnings,
    )


def run_search_format_service(preferences: dict) -> tuple[dict, tuple[int, int]]:
    destination = preferences.get("destination", "")
    budget = preferences.get("budget_signal", "mid-range")

    print(f"\nSearching Google Places for {destination}...\n")
    hotels_block, restaurants_block, activities_block, warnings = _gather_places(destination, preferences)

    warning_note = ""
    if warnings:
        warning_note = "BUDGET WARNINGS (include these in practical_tips):\n"
        warning_note += "\n".join(f"- {w}" for w in warnings) + "\n\n"

    prompt = f"""You are an expert travel advisor. Return ONLY a valid JSON object — no markdown, no extra text.

TRAVELER PROFILE:
- Destination: {destination}
- Dates: {preferences.get('dates', 'N/A')}
- Party: {preferences.get('party', 'N/A')}
- Pace: {preferences.get('pace', 'N/A')}
- Budget: {budget}
- Food preferences: {preferences.get('food_preferences', 'None specified')}
- Activity preferences: {preferences.get('activity_preferences', 'None specified')}

REAL PLACES FROM GOOGLE PLACES API — use ONLY these names; never invent a place:

HOTELS:
{hotels_block}

RESTAURANTS:
{restaurants_block}

ACTIVITIES:
{activities_block}

{warning_note}Return this exact JSON structure:
{{
  "destination": "{destination}",
  "overview": "<one vivid paragraph about {destination}>",
  "hotels": [
    {{"name": "<name from list>", "neighborhood": "<area>", "price_range": "<$–$$$$>", "why": "<one sentence why it fits this traveler>"}},
    ... (3 hotels)
  ],
  "restaurants": [
    {{"name": "<name from list>", "cuisine": "<type>", "price_range": "<$–$$$$>", "why": "<one sentence>"}},
    ... (4-5 restaurants)
  ],
  "activities": [
    {{"name": "<name from list>", "category": "<museum/park/landmark/etc.>", "why": "<fits traveler because...>", "tip": "<practical tip>"}},
    ... (6-8 activities)
  ],
  "practical_tips": [
    "Transport: ...",
    "Customs: ...",
    "Best time: ...",
    "Watch-out: ..."
  ]
}}

Rules:
- Use ONLY hotel/restaurant/activity names from the lists above.
- If a list shows "(no results)", omit that section and add a practical_tip advising the traveler to search Google Maps.
- Explain WHY each pick fits this specific traveler.
- Return valid JSON only."""

    client = anthropic.Anthropic()
    response = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=4096,
        messages=[{"role": "user", "content": prompt}],
    )

    usage = (response.usage.input_tokens, response.usage.output_tokens)

    raw = response.content[0].text.strip()
    if raw.startswith("```"):
        raw = raw.split("\n", 1)[1]
        raw = raw.rsplit("```", 1)[0]

    return json.loads(raw), usage


if __name__ == "__main__":
    sample = {
        "destination": "Paris",
        "dates": "5 days in September",
        "party": "couple",
        "pace": "relaxed",
        "budget_signal": "mid-range",
        "food_preferences": "French, bistros, pastries",
        "activity_preferences": "art, museums, walking",
    }
    result, _ = run_search_format_service(sample)
    print(json.dumps(result, indent=2, ensure_ascii=False))
