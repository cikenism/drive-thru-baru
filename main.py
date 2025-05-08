import asyncio
import os
import traceback
import sounddevice as sd
import numpy as np
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from google import genai
from google.genai import types
from dotenv import load_dotenv

load_dotenv()
app = FastAPI()

CHANNELS = 1
SEND_SAMPLE_RATE = 16000
RECEIVE_SAMPLE_RATE = 24000
CHUNK_SIZE = 2048
MODEL = "models/gemini-2.0-flash-live-001"

def save_order(items: list[str]):
    print("\n📝 Pesanan Disimpan:", items)
    return {"status": "ok", "pesanan": items}

tools = [{
    "function_declarations": [{
        "name": "save_order",
        "description": "menyimpan pesanan makanan atau minuman pelanggan ke sistem.",
        "parameters": {
            "type": "object",
            "properties": {
                "items": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "menu": {"type": "string", "description": "Menu makanan atau minuman yang dipesan seperti ayam goreng, fanta, cola, kentang goreng, dll. Jangan mencatat hal-hal aneh seperti hewan, benda asing, atau kata tidak relevan"},
                            "qty": {"type": "integer", "description": "Jumlah item yang dipesan, misalnya 1, 2, 5"}
                        },
                        "required": ["menu", "qty"]
                    }
                },
                "note": {"type": "string"}
            },
            "required": ["items"]
        },
    }]
}]

CONFIG = types.LiveConnectConfig(
    system_instruction=types.Content(parts=[
        types.Part(text="Kamu adalah asisten drive thru. Sapa pelanggan dan tanya apa yang ingin mereka pesan lalu simpan pesanan pelanggan ke dalam sistem menggunakan fungsi yang tersedia. Jawablah hanya dalam bahasa Indonesia.")
    ]),
    response_modalities=["AUDIO"],
    speech_config=types.SpeechConfig(language_code="id-ID"),
    tools=tools,
)

client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))

@app.websocket("/ws/audio")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    print("🔌 WebSocket Connected")

    audio_buffer = b''
    audio_in_queue = asyncio.Queue()
    out_queue = asyncio.Queue(maxsize=5)

    async with client.aio.live.connect(model=MODEL, config=CONFIG) as session:
        async def sender():
            try:
                while True:
                    data = await websocket.receive_bytes()
                    await session.send(input={"data": data, "mime_type": "audio/pcm"})
            except WebSocketDisconnect:
                print("❌ Client disconnected (send)")

        async def receiver():
            try:
                turn = session.receive()
                async for response in turn:
                    if response.text:
                        await websocket.send_text(response.text)

                    if response.data:
                        await websocket.send_bytes(response.data)

                    if response.tool_call:
                        responses = []
                        for fc in response.tool_call.function_calls:
                            if fc.name == "save_order":
                                items = fc.args.get("items", [])
                                result = save_order(items)
                                responses.append(
                                    types.FunctionResponse(
                                        id=fc.id, name=fc.name, response=result
                                    )
                                )
                        await session.send_tool_response(function_responses=responses)
            except WebSocketDisconnect:
                print("❌ Client disconnected (receive)")

        await asyncio.gather(sender(), receiver())
