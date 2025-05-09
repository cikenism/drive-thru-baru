import os
import asyncio
import websockets
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from google import genai

app = FastAPI()

# Enable CORS for frontend access
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Update with frontend URL in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

MODEL = "models/gemini-2.0-flash-live-001"
CONFIG = {"response_modalities": ["AUDIO"]}

# Initialize Google GenAI client
client = genai.Client(http_options={"api_version": "v1beta"})


@app.websocket("/ws/audio")
async def audio_proxy(websocket: WebSocket):
    await websocket.accept()

    try:
        async with client.aio.live.connect(model=MODEL, config=CONFIG) as session:
            # Task to receive data from Google and send back to frontend
            async def receive_from_google():
                async for response in session.receive():
                    if response.data:
                        await websocket.send_bytes(response.data)
                    if response.text:
                        await websocket.send_text(response.text)

            receiver_task = asyncio.create_task(receive_from_google())

            # Receive audio from frontend and forward to Google API
            while True:
                data = await websocket.receive_bytes()
                await session.send({"data": data, "mime_type": "audio/pcm"})

    except WebSocketDisconnect:
        print("Frontend disconnected.")
    except Exception as e:
        print("Error:", e)
    finally:
        await websocket.close()


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=int(os.environ.get("PORT", 8000)), reload=True)
