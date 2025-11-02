import os
from langgraph.graph import StateGraph, START, END
from typing import Dict, Any
from tools.gmail import summarize_unread
from tools.calendar import plan_day
from tools.weather import today_weather
from tools.tasks import add_tasks

State = Dict[str, Any]

def node_router(state: State):
    prompt = state["prompt"].lower()
    if "email" in prompt:
        return "summarize"
    if "schedule" in prompt or "plan" in prompt:
        return "calendar"
    if "weather" in prompt:
        return "weather"
    return "tasks"

async def summarize_node(state: State) -> State:
    result = await summarize_unread(state)
    return {"result": result}

async def calendar_node(state: State) -> State:
    result = await plan_day(state)
    return {"result": result}

async def weather_node(state: State) -> State:
    result = await today_weather(state)
    return {"result": result}

async def tasks_node(state: State) -> State:
    result = await add_tasks(state)
    return {"result": result}

async def run_agent(user_prompt: str) -> str:
    g = StateGraph(State)
    g.add_node("summarize", summarize_node)
    g.add_node("calendar", calendar_node)
    g.add_node("weather", weather_node)
    g.add_node("tasks", tasks_node)
    g.add_conditional_edges(
        START,
        node_router,
        {
            "summarize": "summarize",
            "calendar": "calendar",
            "weather": "weather",
            "tasks": "tasks",
        },
    )
    g.add_edge("summarize", END)
    g.add_edge("calendar", END)
    g.add_edge("weather", END)
    g.add_edge("tasks", END)
    app = g.compile()
    resp = await app.ainvoke({"prompt": user_prompt})
    if isinstance(resp, dict):
        return resp.get("result", "")
    return str(resp)