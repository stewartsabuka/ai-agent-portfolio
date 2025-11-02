from datetime import datetime

from fastapi import FastAPI
from pydantic import BaseModel
from graph import run_agent

app = FastAPI(title="AI Daily Assistant")

class Query(BaseModel):
    prompt: str

@app.post("/agent")
async def agent_endpoint(q: Query):
    result = await run_agent(q.prompt)
    return {"result": result}


@app.get("/health")
def health():
    return {"ok": True, "time": datetime.now().isoformat()}