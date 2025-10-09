from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from google import genai
from pydantic import BaseModel

import json
import logging
import os
import time

load_dotenv()

google_client = genai.Client(api_key=os.getenv("GOOGLE_API_KEY"))

# === Logging setup ===
logger = logging.getLogger("recipe_app")
logger.setLevel(logging.INFO)
logger.propagate = False
if logger.hasHandlers():
    logger.handlers.clear()

file_handler = logging.FileHandler("recipe_server.log", mode="a", encoding="utf-8")
file_handler.setFormatter(logging.Formatter("%(asctime)s - %(levelname)s - %(message)s"))
logger.addHandler(file_handler)

# === FastAPI setup ===
app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# === Models ===
class ChatMessage(BaseModel):
    role: str
    text: str

class ChatRequest(BaseModel):
    message: str
    history: list[ChatMessage] | None = None

class FeedbackRequest(BaseModel):
    type: str  # upvote / downvote
    message: str | None = None


# === Utility: Load & Save Feedback Summary ===
FEEDBACK_FILE = "feedback_summary.json"

def load_feedback_summary():
    if not os.path.exists(FEEDBACK_FILE):
        return {"preferences": {}}
    try:
        with open(FEEDBACK_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        logger.error(f"Failed to load feedback summary: {e}")
        return {"preferences": {}}


def save_feedback_summary(data):
    try:
        with open(FEEDBACK_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
    except Exception as e:
        logger.error(f"Failed to save feedback summary: {e}")


# === FEEDBACK ENDPOINT ===
@app.post("/api/feedback")
async def feedback(req: FeedbackRequest):
    """
    Collects user feedback from frontend.
    Updates feedback summary file and logs raw feedback.
    """
    feedback_entry = {
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        "type": req.type,
        "message": req.message or "",
    }

    # Log feedback
    logger.info(f"User feedback: {feedback_entry}")

    # Append raw feedback to a .jsonl file
    with open("feedback_log.jsonl", "a", encoding="utf-8") as f:
        f.write(json.dumps(feedback_entry, ensure_ascii=False) + "\n")

    # === Update preference summary ===
    summary = load_feedback_summary()
    prefs = summary.get("preferences", {})

    # Normalize message to lower case for matching
    msg = (req.message or "").lower()

    if req.type == "upvote":
        prefs["positive_feedback_count"] = prefs.get("positive_feedback_count", 0) + 1
    else:
        prefs["negative_feedback_count"] = prefs.get("negative_feedback_count", 0) + 1
        # Track specific complaint types
        if "too easy" in msg or "simple" in msg:
            prefs["make_harder"] = prefs.get("make_harder", 0) + 1
        if "too hard" in msg or "complex" in msg:
            prefs["make_easier"] = prefs.get("make_easier", 0) + 1
        if "more ingredient" in msg or "add" in msg:
            prefs["add_ingredients"] = prefs.get("add_ingredients", 0) + 1
        if "less ingredient" in msg or "simplify" in msg:
            prefs["reduce_ingredients"] = prefs.get("reduce_ingredients", 0) + 1
        if "faster" in msg or "quick" in msg:
            prefs["shorter_time"] = prefs.get("shorter_time", 0) + 1
        if "longer" in msg or "slow cook" in msg:
            prefs["longer_time"] = prefs.get("longer_time", 0) + 1

    summary["preferences"] = prefs
    save_feedback_summary(summary)

    return {"status": "success", "message": "Feedback received"}


# === CHAT ENDPOINT ===
@app.post("/api/chat")
async def chat(req: ChatRequest):
    """
    Handles chat requests with adaptive prompt tuning based on past feedback.
    """
    user_input = req.message
    history = req.history or []

    # === Load adaptive preferences ===
    summary = load_feedback_summary()
    prefs = summary.get("preferences", {})

    # === Build dynamic tuning instructions ===
    tuning_notes = []
    if prefs.get("make_harder", 0) > prefs.get("make_easier", 0):
        tuning_notes.append("Make recipes slightly more complex and advanced.")
    elif prefs.get("make_easier", 0) > prefs.get("make_harder", 0):
        tuning_notes.append("Simplify recipes with fewer cooking techniques.")

    if prefs.get("add_ingredients", 0) > prefs.get("reduce_ingredients", 0):
        tuning_notes.append("Include more diverse ingredients.")
    elif prefs.get("reduce_ingredients", 0) > prefs.get("add_ingredients", 0):
        tuning_notes.append("Use fewer ingredients for simpler dishes.")

    if prefs.get("shorter_time", 0) > prefs.get("longer_time", 0):
        tuning_notes.append("Prioritize faster, quick-cook recipes.")
    elif prefs.get("longer_time", 0) > prefs.get("shorter_time", 0):
        tuning_notes.append("Add more slow-cook or longer recipes for flavor depth.")

    adaptive_prompt = (
        "Based on user feedback, adjust your style accordingly:\n"
        + ("\n".join(f"- {note}" for note in tuning_notes) if tuning_notes else "- Maintain your current balance.")
    )

    # === System prompt ===
    system_prompt = (
        "You are a helpful and creative recipe builder who can also chat casually.\n"
        "If the user asks about recipes or ingredients, respond with a valid JSON recipe using the schema below.\n"
        "Otherwise, respond conversationally in plain text.\n\n"
        f"{adaptive_prompt}\n"
    )

    # === Detect if user wants a recipe ===
    recipe_triggers = ["recipe", "cook", "ingredients", "dish", "meal", "food", "bake", "grill"]
    wants_recipe = any(word in user_input.lower() for word in recipe_triggers)

    # === Build conversation history ===
    conversation = "\n".join([f"{m.role.capitalize()}: {m.text}" for m in history])
    if conversation:
        conversation += "\n"
    conversation += f"User: {user_input}"

    # === Recipe schema ===
    if wants_recipe:
        instruction = (
            "\nNow generate a recipe in valid JSON format using this schema:\n"
            "{\n"
            '  "recipes": [\n'
            "    {\n"
            '      "name": "Recipe Name",\n'
            '      "ingredients": ["list", "of", "ingredients"],\n'
            '      "instructions": ["step", "by", "step", "instructions"],\n'
            '      "cookingTime": "estimated time",\n'
            '      "difficulty": "Easy | Medium | Hard",\n'
            '      "nutrition": {\n'
            '        "calories": 450,\n'
            '        "protein": "12g",\n'
            '        "carbs": "60g"\n'
            "      },\n"
            '      "otherInfo": {"optional": "any extra notes"}\n'
            "    }\n"
            "  ]\n"
            "}"
        )
    else:
        instruction = "\nRespond conversationally in natural language, not JSON."

    full_prompt = f"System: {system_prompt}\n\n{conversation}\n{instruction}"
    logger.info(f"Full Prompt (truncated): {full_prompt[:300]}...")

    # === Call Gemini with retries ===
    for attempt in range(3):
        try:
            response = google_client.models.generate_content(
                model="gemini-2.5-flash",
                contents=full_prompt,
            )
            reply_text = response.text or "(No response from model)"

            parsed_output = None
            if wants_recipe:
                try:
                    parsed_output = json.loads(reply_text)
                except Exception:
                    logger.warning("Invalid JSON output from Gemini")
                    parsed_output = None

            return {
                "reply": parsed_output if parsed_output else reply_text,
                "is_json": bool(parsed_output),
            }

        except Exception as e:
            logger.error(f"Attempt {attempt+1} failed: {e}")
            time.sleep(2 ** attempt)

    return {
        "reply": "Error: Failed to get a response from Gemini after multiple attempts.",
        "is_json": False,
    }
