from dotenv import load_dotenv
import anthropic

load_dotenv()

SYSTEM_PROMPT = """You are a friendly travel planning assistant. Your job is to gather trip preferences through natural conversation.

Ask about these topics one at a time, in a natural order:
1. Destination (must be a specific city — if vague like "somewhere warm", ask for a specific city)
2. Dates or duration of the trip
3. Party size (solo, couple, family, group)
4. Pace (relaxed or packed)
5. Food preferences (optional — ask casually)
6. Activity preferences (optional — ask casually)

IMPORTANT RULES:
- Ask only ONE question at a time. Never send a list of questions.
- Infer the budget signal (backpacker / mid-range / luxury) from context clues in their answers. NEVER ask "what's your budget?"
- Keep responses short and conversational.
- If the user goes off-topic, gently redirect to trip planning.
- If the user asks to book something, say: "I can't book yet, but I'll show you where to book."

When you have collected: destination, dates, party, pace, and have inferred a budget signal, output the preferences in EXACTLY this format and nothing else after it:

TRIP PREFERENCES EXTRACTED

Destination: [city]
Dates: [duration or dates]
Party: [party description]
Pace: [relaxed or packed]
Budget Signal: [backpacker / mid-range / luxury]
Food Preferences: [preferences or "None specified"]
Activity Preferences: [preferences or "None specified"]

Ready to search."""


def run_intake_service() -> tuple[dict, tuple[int, int]]:
    client = anthropic.Anthropic()
    messages = []
    total_input = 0
    total_output = 0

    print("TripMind — Travel Planner\n")
    print("Assistant: Hi! I'm your travel planning assistant. Where are you thinking of going?\n")

    messages.append({
        "role": "assistant",
        "content": "Hi! I'm your travel planning assistant. Where are you thinking of going?"
    })

    while True:
        user_input = input("You: ").strip()
        if not user_input:
            continue

        messages.append({"role": "user", "content": user_input})

        response = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=1024,
            system=SYSTEM_PROMPT,
            messages=messages,
        )

        total_input  += response.usage.input_tokens
        total_output += response.usage.output_tokens

        assistant_reply = response.content[0].text
        messages.append({"role": "assistant", "content": assistant_reply})

        if "TRIP PREFERENCES EXTRACTED" in assistant_reply:
            print(f"\nAssistant: {assistant_reply}\n")
            return _parse_preferences(assistant_reply), (total_input, total_output)

        print(f"\nAssistant: {assistant_reply}\n")


def _parse_preferences(text: str) -> dict:
    prefs = {}
    field_map = {
        "Destination": "destination",
        "Dates": "dates",
        "Party": "party",
        "Pace": "pace",
        "Budget Signal": "budget_signal",
        "Food Preferences": "food_preferences",
        "Activity Preferences": "activity_preferences",
    }
    for label, key in field_map.items():
        for line in text.splitlines():
            if line.startswith(f"{label}:"):
                prefs[key] = line.split(":", 1)[1].strip()
                break
    return prefs


if __name__ == "__main__":
    preferences, _ = run_intake_service()
    print("Extracted preferences:", preferences)
