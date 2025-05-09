import os
import asyncio
from fastapi import FastAPI, WebSocket
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv
import google.generativeai as genai

load_dotenv()

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Konfigurasi API Gemini
genai.configure(api_key=os.getenv("GEMINI_API_KEY"))
MODEL = "models/gemini-2.0-flash-live-001"

# Konfigurasi function calling
config = {
    "systemInstruction": {
        "parts": [
            {
                "text": "Kamu adalah asisten drive thru. Jawab hanya dalam Bahasa Indonesia."
            }
        ]
    },
    "responseModalities": ["AUDIO", "TEXT"],
    "speechConfig": {
        "languageCode": "id-ID"
    },
    "tools": [
        {
            "functionDeclarations": [
                {
                    "name": "save_order",
                    "description": "Menyimpan pesanan makanan atau minuman pelanggan.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "items": {
                                "type": "array",
                                "items": {
                                    "type": "object",
                                    "properties": {
                                        "menu": {"type": "string"},
                                        "qty": {"type": "integer"}
                                    },
                                    "required": ["menu", "qty"]
                                }
                            }
                        },
                        "required": ["items"]
                    }
                }
            ]
        }
    ]
}


def save_order(items):
    print("\n📝 Pesanan Disimpan:", items)
    return {"status": "ok", "pesanan": items}


@app.websocket("/ws/audio")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()

    async with genai.aio.connect(model=MODEL, config=config) as session:

        async def sender():
            while True:
                data = await websocket.receive_bytes()
                await session.send_audio(data, mime_type="audio/pcm")

        async def receiver():
            async for response in session:
                # Kirim teks ke klien
                if response.text:
                    await websocket.send_text(response.text)

                # Kirim audio ke klien
                if response.audio:
                    await websocket.send_bytes(response.audio)

                # Tangani pemanggilan fungsi
                if response.function_calls:
                    for call in response.function_calls:
                        if call.name == "save_order":
                            items = call.args.get("items", [])
                            result = save_order(items)
                            await session.send_function_response(
                                name="save_order",
                                id=call.id,
                                response=result
                            )

        await asyncio.gather(sender(), receiver())
