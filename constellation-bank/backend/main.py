import json
import os
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

try:  # optional .env support
    from dotenv import load_dotenv
    load_dotenv()
except Exception:
    pass

from . import data as D
from . import orchestrator as O

app = FastAPI(title="Constellation Bank - multi-agent banking MVP")


class Chat(BaseModel):
    session_id: str = "default"
    message: str


class Decision(BaseModel):
    approve: bool


@app.get("/api/health")
def health():
    live = O._client is not None
    return {"mode": "live" if live else "offline", "supervisor_model": O.SUPERVISOR_MODEL,
            "agent_model": O.AGENT_MODEL, "agents": O.public_agents()}


@app.get("/api/snapshot")
def snapshot():
    return {"customer": D.CUSTOMER["name"], "accounts": D.STATE["accounts"], "cards": D.STATE["cards"],
            "pending": [a for a in D.PENDING.values() if a["status"] == "PENDING"]}


@app.post("/api/chat")
def chat(body: Chat):
    def stream():
        for e in O.handle(body.session_id, body.message[:1000]):
            yield json.dumps(e, default=str) + "\n"
    return StreamingResponse(stream(), media_type="application/x-ndjson")


@app.post("/api/actions/{action_id}/decision")
def decision(action_id: str, body: Decision):
    return O.decide(action_id, body.approve)


@app.post("/api/reset")
def reset():
    D.reset()
    O.HISTORY.clear()
    return {"ok": True}


FRONTEND = Path(__file__).resolve().parent.parent / "frontend"
app.mount("/", StaticFiles(directory=FRONTEND, html=True), name="ui")
