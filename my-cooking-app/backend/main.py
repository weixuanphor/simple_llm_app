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
logger.propagate = False  # critical: stop sending logs to Uvicorn/root handlers
# remove existing handlers (if reloaded)
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


class ChatMessage(BaseModel):
    role: str
    text: str

class ChatRequest(BaseModel):
    message: str
    history: list[ChatMessage] | None = None

@app.post("/api/chat")
async def chat(req: ChatRequest):
    """
    Handles chat requests:
    - Uses previous conversation history for context
    - Asks Gemini to generate a recipe in JSON format
    """
    user_input = req.message
    history = req.history or []

    # === System Prompt (Role Definition) ===
    system_prompt = (
        "You are a helpful and creative recipe builder who can also chat casually. "
        "If the user asks about recipes or ingredients, respond with a valid JSON recipe "
        "following the required schema. Otherwise, respond normally in text."
    )

    # === Decide response mode (detect recipe intent) ===
    recipe_triggers = ["recipe", "cook", "ingredients", "dish", "meal"]
    wants_recipe = any(word in user_input.lower() for word in recipe_triggers)

    # === Construct conversation history ===
    conversation = "\n".join(
        [f"{msg.role.capitalize()}: {msg.text}" for msg in history]
    )
    if conversation:
        conversation += "\n"
    conversation += f"User: {user_input}"

    # === Add conditional JSON schema instruction ===
    if wants_recipe:
        instruction = (
            "\n\nNow generate a recipe in valid JSON format using this schema:\n"
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
            "      }\n"
            "    }\n"
            "  ]\n"
            "}"
        )
    else:
        instruction = (
            "\n\nUser is not asking for a recipe. "
            "Respond conversationally in natural language. "
            "Do NOT use JSON, brackets, or structured data here."
        )

    full_prompt = f"System: {system_prompt}\n\n{conversation}\n{instruction}"
    logger.info(f"Full Prompt: {full_prompt}...")

    # === Call Gemini with retries (error handling) ===
    max_retries = 3
    delay = 2
    for attempt in range(max_retries):
        try:
            response = google_client.models.generate_content(
                model="gemini-2.5-flash",
                contents=full_prompt,
            )
            reply_text = response.text or "(No response from model)"

            # parse JSON only if in recipe mode
            parsed_output = None
            if wants_recipe:
                try:
                    parsed_output = json.loads(reply_text)
                except Exception:
                    # fallback if not valid JSON
                    parsed_output = None
                    logger.warning("Model returned invalid JSON format")

            logger.info(f"User: {user_input} | Reply: {reply_text}...")

            return {
                "reply": parsed_output if parsed_output else reply_text,
                "is_json": bool(parsed_output),
            }

        except Exception as e:
            logger.error(f"Error on attempt {attempt + 1}: {e}")
            if attempt < max_retries - 1:
                time.sleep(delay)
                delay *= 2
            else:
                return {
                    "reply": "Error: Unable to get response from model after multiple attempts.",
                    "is_json": False,
                }
