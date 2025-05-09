import os
import ssl
import json
import base64
import asyncio
import websockets
from fastapi import FastAPI, WebSocket
from dotenv import load_dotenv

load_dotenv()

app = FastAPI()

MODEL = "models/gemini-2.0-flash-live-001"
API_KEY = os.getenv("GEMINI_API_KEY")
GEMINI_WS_URL = "wss://generativelanguage.googleapis.com/ws/google.ai.generativelanguage.v1beta.GenerativeService.BidiGenerateContent"

HEADERS = {
    "Authorization": f"Bearer {API_KEY}"
}

# Fungsi dipanggil oleh Gemini (toolCall)
def save_order(items):
    print("\n📝 Pesanan Disimpan:", items)
    return {"status": "ok", "pesanan": items}

@app.websocket("/ws/audio")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()

    async with websockets.connect(GEMINI_WS_URL, extra_headers=HEADERS, ssl=ssl.create_default_context()) as gemini_ws:
        # Kirim setup awal
        setup_message = {
            "setup": {
                "model": MODEL,
                "config": {
                    "systemInstruction": {
                        "parts": [{"text": "Kamu adalah asisten drive thru. Jawab hanya dalam Bahasa Indonesia."}]
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
            }
        }
        await gemini_ws.send(json.dumps(setup_message))

        async def sender():
            while True:
                data = await websocket.receive_bytes()
                encoded = base64.b64encode(data).decode("utf-8")
                await gemini_ws.send(json.dumps({
                    "realtimeInput": {
                        "data": encoded,
                        "mimeType": "audio/pcm"
                    }
                }))

        async def receiver():
            async for msg in gemini_ws:
                res = json.loads(msg)

                # Teks dari Gemini
                if "textResponse" in res:
                    text = res["textResponse"]["text"]
                    await websocket.send_text(text)

                # Audio dari Gemini
                if "audioResponse" in res:
                    audio_b64 = res["audioResponse"]["data"]
                    audio_bytes = base64.b64decode(audio_b64)
                    await websocket.send_bytes(audio_bytes)

                # Tool Call
                if "toolCall" in res:
                    calls = res["toolCall"]["functionCalls"]
                    responses = []
                    for call in calls:
                        if call["name"] == "save_order":
                            items = call["args"].get("items", [])
                            result = save_order(items)
                            responses.append({
                                "functionResponse": {
                                    "name": "save_order",
                                    "id": call["id"],
                                    "response": result
                                }
                            })
                    for r in responses:
                        await gemini_ws.send(json.dumps({"toolResponse": r}))

        await asyncio.gather(sender(), receiver())
