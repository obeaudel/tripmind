import gradio as gr
import spaces
from dotenv import load_dotenv
import anthropic

from intake_service import SYSTEM_PROMPT, _parse_preferences
from search_format_service import run_search_format_service
from renderers import render_pdf
from track_cost import calculate_cost

load_dotenv()

_OPENING = (
    "Hi! I'm TripMind, your AI travel planner. "
    "Tell me where you want to go and I'll build you a personalised itinerary — "
    "hotels, restaurants, things to do, and a PDF to keep. Where are you thinking of going?"
)


# ── Itinerary → Markdown ──────────────────────────────────────────────────────

def _itinerary_md(it: dict) -> str:
    dest = it.get("destination", "Your Destination")
    lines = [f"## Your {dest} Itinerary", "", it.get("overview", ""), ""]

    lines.append("### Where to Stay")
    for h in it.get("hotels", []):
        lines += [f"**{h['name']}** — {h['neighborhood']} — {h['price_range']}", f"*{h['why']}*", ""]

    lines.append("### Where to Eat")
    for r in it.get("restaurants", []):
        lines += [f"**{r['name']}** — {r['cuisine']} — {r['price_range']}", f"*{r['why']}*", ""]

    lines.append("### What to Do")
    for a in it.get("activities", []):
        lines += [f"**{a['name']}** ({a['category']})", f"*{a['why']}*", f"Tip: {a['tip']}", ""]

    lines.append("### Practical Tips")
    for tip in it.get("practical_tips", []):
        lines.append(f"- {tip}")

    return "\n".join(lines)


# ── Chat handler ──────────────────────────────────────────────────────────────

@spaces.GPU
def respond(message: str, history: list, state: dict):
    """Called on every user message. Returns (history, state, pdf_update, cleared_input)."""
    if not message.strip():
        return history, state, gr.update(), ""

    history = list(history)
    history.append({"role": "user", "content": message})

    if state.get("intake_done"):
        history.append({"role": "assistant", "content": "Your itinerary is ready above — grab the PDF below!"})
        return history, state, gr.update(), ""

    # ── Intake turn ───────────────────────────────────────────────────────────
    messages = list(state["messages"])
    messages.append({"role": "user", "content": message})

    try:
        client = anthropic.Anthropic()
        response = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=1024,
            system=SYSTEM_PROMPT,
            messages=messages,
        )
    except anthropic.APIConnectionError:
        err = "Couldn't reach the AI service — check your connection and try again."
        history.append({"role": "assistant", "content": err})
        return history, state, gr.update(), ""
    except anthropic.AuthenticationError:
        err = "API key error — please check your ANTHROPIC_API_KEY."
        history.append({"role": "assistant", "content": err})
        return history, state, gr.update(), ""
    except Exception as e:
        err = f"Something went wrong ({type(e).__name__}). Please try again."
        history.append({"role": "assistant", "content": err})
        return history, state, gr.update(), ""

    reply = response.content[0].text
    messages.append({"role": "assistant", "content": reply})

    new_state = {
        **state,
        "messages": messages,
        "total_input":  state["total_input"]  + response.usage.input_tokens,
        "total_output": state["total_output"] + response.usage.output_tokens,
    }

    # ── Intake complete — run search + render ─────────────────────────────────
    if "TRIP PREFERENCES EXTRACTED" in reply:
        new_state["intake_done"] = True
        prefs = _parse_preferences(reply)
        new_state["preferences"] = prefs

        history.append({"role": "assistant", "content": reply})

        try:
            itinerary, (si, so) = run_search_format_service(prefs)
            new_state["itinerary"] = itinerary
            new_state["total_input"]  += si
            new_state["total_output"] += so

            pdf_path = render_pdf(itinerary)
            new_state["pdf_path"] = pdf_path

            cost = calculate_cost(new_state["total_input"], new_state["total_output"])
            cost_note = (
                f"\n\n---\n*Cost this run: ${cost:.4f} "
                f"· At 10,000 users: ${cost * 10_000:,.2f}*"
            )
            history.append({"role": "assistant", "content": _itinerary_md(itinerary) + cost_note})
            return history, new_state, gr.update(value=pdf_path, visible=True), ""

        except Exception as e:
            err = (
                f"Got your preferences, but something went wrong searching for places "
                f"({type(e).__name__}). Please refresh and try again."
            )
            history.append({"role": "assistant", "content": err})
            return history, new_state, gr.update(visible=False), ""

    history.append({"role": "assistant", "content": reply})
    return history, new_state, gr.update(), ""


# ── Layout ────────────────────────────────────────────────────────────────────

_INITIAL_STATE = {
    "messages": [{"role": "assistant", "content": _OPENING}],
    "intake_done": False,
    "total_input": 0,
    "total_output": 0,
}

with gr.Blocks(title="TripMind — AI Travel Planner", theme=gr.themes.Soft()) as demo:
    gr.Markdown(
        "# TripMind\n"
        "Your AI travel planner. Have a conversation — I'll build a personalised "
        "itinerary and a PDF you can keep."
    )

    state = gr.State(dict(_INITIAL_STATE, messages=list(_INITIAL_STATE["messages"])))

    chatbot = gr.Chatbot(
        value=[{"role": "assistant", "content": _OPENING}],
        type="messages",
        height=520,
        label="TripMind",
        show_copy_button=True,
    )

    with gr.Row():
        msg = gr.Textbox(
            placeholder="Where are you thinking of going?",
            scale=9,
            container=False,
            autofocus=True,
        )
        send_btn = gr.Button("Send", scale=1, variant="primary")

    pdf_output = gr.File(
        label="Download your itinerary PDF",
        visible=False,
        interactive=False,
    )

    inputs  = [msg, chatbot, state]
    outputs = [chatbot, state, pdf_output, msg]

    msg.submit(respond, inputs, outputs)
    send_btn.click(respond, inputs, outputs)

if __name__ == "__main__":
    demo.launch()
