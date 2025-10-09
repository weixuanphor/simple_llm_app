from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from dotenv import load_dotenv
from anthropic import Anthropic
from google import genai

import os

load_dotenv()
anthropic_client = Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
google_client = genai.Client(api_key=os.getenv("GOOGLE_API_KEY"))

app = FastAPI()

# Allow requests from your frontend (Vite uses port 5173)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # or ["http://localhost:5173"]
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Message format
class ChatRequest(BaseModel):
    message: str

# @app.post("/api/chat")
# def chat_endpoint(req: ChatRequest):
#     user_input = req.message
#     # You can replace this logic with a real model or external API call
#     response = f"Agent: I received your message → '{user_input}'"
#     return {"reply": response}


@app.post("/api/chat")
async def chat(req: ChatRequest):
    user_input = req.message

    # Claude model call
    # response = anthropic_client.messages.create(
    #     # model="claude-3-7-sonnet",
    #     model="claude-3-5-sonnet-20241022",
    #     max_tokens=100,
    #     messages=[
    #         {"role": "user", "content": user_input}
    #     ]
    # )
    # reply_text = response.content[0].text

    response = google_client.models.generate_content(
        model="gemini-2.5-flash", contents=user_input
    )
    print(response.text)
    reply_text = response.text
    
    return {"reply": reply_text}