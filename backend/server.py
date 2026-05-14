import os
from typing import Any, Dict, List

from dotenv import load_dotenv
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from actions import ActionRouter
from memory import MemoryStore
from planner import Planner
from websocket_manager import WebSocketManager
from workflow_engine import WorkflowEngine

load_dotenv()


class ChatRequest(BaseModel):
    message: str


class ChatResponse(BaseModel):
    response: str
    action: Dict[str, Any] | None = None


class LLMClient:
    def __init__(self) -> None:
        self.api_key = os.getenv("GROQ_API_KEY")
        self.model = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")
        self._client = None
        if self.api_key:
            try:
                from openai import OpenAI

                self._client = OpenAI(api_key=self.api_key, base_url="https://api.groq.com/openai/v1")
            except Exception:
                self._client = None

    def generate(self, prompt: str, context: List[Dict[str, str]]) -> str:
        if not self._client:
            return f"(local fallback) You said: {prompt}"

        messages = [{"role": "system", "content": "You are JARVIS, a concise helpful assistant."}]
        messages.extend(context[-8:])
        messages.append({"role": "user", "content": prompt})

        try:
            result = self._client.chat.completions.create(model=self.model, messages=messages, temperature=0.2)
            return result.choices[0].message.content or "I could not generate a response."
        except Exception as exc:
            return f"Model error: {exc}"


app = FastAPI(title="JARVIS AI Assistant", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

memory = MemoryStore("database/memory.db")
router = ActionRouter(memory)
planner = Planner()
workflow = WorkflowEngine(router)
ws_manager = WebSocketManager()
llm = LLMClient()


@app.get("/health")
async def health() -> Dict[str, str]:
    return {"status": "ok"}


@app.get("/config")
async def config() -> Dict[str, str]:
    return {
        "model": llm.model,
        "has_groq_key": "true" if llm.api_key else "false",
    }


@app.post("/chat", response_model=ChatResponse)
async def chat(req: ChatRequest) -> ChatResponse:
    memory.add_message("user", req.message)
    action_result = await router.execute(req.message)
    context = memory.recent_messages()
    llm_reply = llm.generate(req.message, context)

    combined = f"{action_result['message']}\n\n{llm_reply}" if action_result.get("message") else llm_reply
    memory.add_message("assistant", combined)
    return ChatResponse(response=combined, action=action_result)


@app.post("/plan")
async def create_plan(req: ChatRequest) -> Dict[str, Any]:
    plan = planner.create_plan(req.message)
    return plan


@app.post("/workflow")
async def run_workflow(req: ChatRequest) -> Dict[str, Any]:
    plan = planner.create_plan(req.message)
    results = await workflow.execute(plan["steps"])
    return {"goal": plan["goal"], "results": results}


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket) -> None:
    await ws_manager.connect(websocket)
    try:
        while True:
            payload = await websocket.receive_json()
            user_message = str(payload.get("message", "")).strip()
            if not user_message:
                await ws_manager.send_json(websocket, {"type": "error", "message": "Empty message."})
                continue

            memory.add_message("user", user_message)
            action_result = await router.execute(user_message)
            assistant_reply = llm.generate(user_message, memory.recent_messages())
            final = f"{action_result['message']}\n\n{assistant_reply}" if action_result.get("message") else assistant_reply
            memory.add_message("assistant", final)

            await ws_manager.send_json(
                websocket,
                {
                    "type": "assistant",
                    "message": final,
                    "action": action_result,
                },
            )
    except WebSocketDisconnect:
        ws_manager.disconnect(websocket)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("server:app", host="0.0.0.0", port=8000, reload=True)
