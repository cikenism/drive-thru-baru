from fastapi import FastAPI, WebSocket
import os
from dotenv import load_dotenv
from google import genai
from google.genai import types
import asyncio
import json

load_dotenv()

app = FastAPI()

MODEL = "models/gemini-2.0-flash-live-001"
client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))

# Fungsi yang dipanggil Gemini via tool_call
def save_order(items: list[dict]):
    print("\n📝 Pesanan Disimpan:", items)
    return {"status": "ok", "pesanan": items}

# Deklarasi fungsi Gemini
tools = [
    {
        "function_declarations": [
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
                                    "menu": {"type": "string", "description": "Menu makanan atau minuman yang dipesan seperti ayam goreng, fanta, cola, kentang goreng, dll. Jangan mencatat hal-hal aneh seperti hewan, benda asing, atau kata tidak relevan"},
                                    "qty": {"type": "integer", "description": "Jumlah item yang dipesan, misalnya 1, 2, 5"}
                                },
                                "required": ["menu", "qty"]
                            }
                        },
                        "note": {
                            "type": "string",
                            "description": "Catatan tambahan"
                        }
                    },
                    "required": ["items"]
                },
            }
        ]
    }
]

# Konfigurasi LiveConnect Gemini
config = types.LiveConnectConfig(
    system_instruction=types.Content(parts=[
        types.Part(text="Kamu adalah asisten drive thru. Jawab hanya dalam Bahasa Indonesia.")
    ]),
    response_modalities=["AUDIO", "TEXT"],
    speech_config=types.SpeechConfig(language_code="id-ID"),
    tools=tools,
)

@app.websocket("/ws/audio")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()

    async with client.aio.live.connect(model=MODEL, config=config) as session:

        async def sender():
            while True:
                data = await websocket.receive_bytes()
                await session.send(input={"data": data, "mime_type": "audio/pcm"})

        async def receiver():
            turn = session.receive()
            async for response in turn:
                if response.text:
                    await websocket.send_text(response.text)

                if response.data:
                    await websocket.send_bytes(response.data)

                if response.tool_call:
                    function_responses = []
                    for fc in response.tool_call.function_calls:
                        if fc.name == "save_order":
                            items = fc.args.get("items", [])
                            result = save_order(items)
                            function_responses.append(
                                types.FunctionResponse(
                                    id=fc.id,
                                    name=fc.name,
                                    response=result
                                )
                            )
                    await session.send_tool_response(function_responses=function_responses)

        await asyncio.gather(sender(), receiver())
