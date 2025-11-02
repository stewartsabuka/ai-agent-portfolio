import asyncio
import json
import os
import re
import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional

TASKS_PATH = os.getenv("TASKS_PATH", "tasks.json")


# ---------- storage ----------

def _load_tasks_sync() -> List[Dict[str, Any]]:
    if not os.path.exists(TASKS_PATH):
        return []
    try:
        with open(TASKS_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
            if isinstance(data, list):
                return data
    except Exception:
        pass
    return []


def _save_tasks_sync(tasks: List[Dict[str, Any]]) -> None:
    with open(TASKS_PATH, "w", encoding="utf-8") as f:
        json.dump(tasks, f, ensure_ascii=False, indent=2)


async def load_tasks() -> List[Dict[str, Any]]:
    return await asyncio.to_thread(_load_tasks_sync)


async def save_tasks(tasks: List[Dict[str, Any]]) -> None:
    await asyncio.to_thread(_save_tasks_sync, tasks)


# ---------- helpers ----------

def _now_iso() -> str:
    return datetime.utcnow().isoformat(timespec="seconds") + "Z"


def _format_list(tasks: List[Dict[str, Any]]) -> str:
    if not tasks:
        return "Your list is empty."
    lines = []
    for i, t in enumerate(tasks, start=1):
        status = "✓" if t.get("done") else "•"
        title = t.get("title") or "(untitled)"
        prio = f" [p{t['priority']}]" if t.get("priority") else ""
        due = f" (due {t['due']})" if t.get("due") else ""
        lines.append(f"{i}. {status} {title}{prio}{due}")
    return "Tasks:\n" + "\n".join(lines)


def _parse_priority(text: str) -> Optional[int]:

    text_l = text.lower()
    m = re.search(r"\bp\s*([1-3])\b", text_l) or re.search(r"priority\s*([1-3])", text_l)
    if m:
        return int(m.group(1))
    if "high" in text_l:
        return 1
    if "medium" in text_l or "med" in text_l:
        return 2
    if "low" in text_l:
        return 3
    return None


def _parse_due(text: str) -> Optional[str]:
    t = text.lower()
    if "tomorrow" in t:
        return "tomorrow"
    if "today" in t:
        return "today"
    m = re.search(r"\b(20\d{2}-\d{2}-\d{2})\b", text)
    if m:
        return m.group(1)
    return None


def _extract_titles_to_add(text: str) -> List[str]:
    """
    Accepts formats like:
      - "add buy milk"
      - "add: buy milk; call mom; book dentist"
      - "todo buy milk, call mom"
    Splits on ';' first, then commas.
    """
    t = text.strip()

    # strip leading verbs/keywords
    t = re.sub(r"^\s*(add|todo|task|remember|note|create|append)[:\s,-]*", "", t, flags=re.I)

    parts = []
    for chunk in t.split(";"):
        chunk = chunk.strip().strip(",")
        if not chunk:
            continue
        if "," in chunk:
            parts.extend([c.strip() for c in chunk.split(",") if c.strip()])
        else:
            parts.append(chunk)
    return [p for p in parts if len(p) > 1]


def _normalize_index(user_idx: int, tasks: List[Dict[str, Any]]) -> Optional[int]:
    if user_idx < 1 or user_idx > len(tasks):
        return None
    return user_idx - 1


# ---------- commands ----------

async def _cmd_list(_: str) -> str:
    tasks = await load_tasks()
    open_tasks = [t for t in tasks if not t.get("done")]
    done_tasks = [t for t in tasks if t.get("done")]
    text = _format_list(open_tasks)
    if done_tasks:
        text += f"\n\nCompleted ({len(done_tasks)}): " + ", ".join([t.get("title", "?") for t in done_tasks[:5]])
    return text


async def _cmd_add(text: str) -> str:
    titles = _extract_titles_to_add(text)
    if not titles:
        return "Tell me what to add, e.g. 'add buy milk; call mom'."

    prio = _parse_priority(text)
    due = _parse_due(text)

    tasks = await load_tasks()
    for title in titles:
        tasks.append({
            "id": str(uuid.uuid4()),
            "title": title,
            "done": False,
            "priority": prio,
            "due": due,
            "created": _now_iso(),
            "updated": _now_iso(),
        })
    await save_tasks(tasks)

    return f"Added {len(titles)} task(s): " + "; ".join(titles[:3]) + ("..." if len(titles) > 3 else "")


async def _cmd_done(text: str) -> str:
    m = re.search(r"\b(done|complete|finish|close)\s+(\d+)\b", text, flags=re.I)
    if not m:
        m = re.search(r"\bmark\s+(\d+)\s+done\b", text, flags=re.I)
    if not m:
        return "Specify which task: e.g. 'done 2'."

    idx = int(m.group(m.lastindex))  # last captured number
    tasks = await load_tasks()
    i = _normalize_index(idx, tasks)
    if i is None:
        return f"Task #{idx} not found."

    tasks[i]["done"] = True
    tasks[i]["updated"] = _now_iso()
    await save_tasks(tasks)
    return f"Marked #{idx} as done: {tasks[i].get('title','')}"


async def _cmd_remove(text: str) -> str:
    m = re.search(r"\b(remove|delete)\s+(\d+)\b", text, flags=re.I)
    if not m:
        return "Specify which task to remove: e.g. 'remove 3'."
    idx = int(m.group(2))
    tasks = await load_tasks()
    i = _normalize_index(idx, tasks)
    if i is None:
        return f"Task #{idx} not found."
    title = tasks[i].get("title", "")
    tasks.pop(i)
    await save_tasks(tasks)
    return f"Removed #{idx}: {title}"


async def _cmd_clear(_: str) -> str:
    await save_tasks([])
    return "Cleared all tasks."


async def _cmd_next(_: str) -> str:
    tasks = await load_tasks()
    open_tasks = [t for t in tasks if not t.get("done")]
    if not open_tasks:
        return "No open tasks."
    
    open_tasks.sort(key=lambda t: (t.get("priority") or 9, t.get("created") or ""))
    t = open_tasks[0]
    pr = f"p{t['priority']}" if t.get("priority") else "p?"
    due = f", due {t['due']}" if t.get("due") else ""
    return f"Next: {t.get('title','(untitled)')} ({pr}{due})"



async def add_tasks(state: Dict[str, Any]) -> str:
    """
    Agent tool. Reads state['prompt'] and performs:
      - 'list' / 'show' → list tasks
      - 'add ...' / 'todo ...' → add tasks
      - 'done N' / 'complete N' → mark done
      - 'remove N' / 'delete N' → remove
      - 'clear' → clear all
      - 'next' → suggest next task
    Returns a short summary string.
    """
    prompt = (state.get("prompt") or "").strip()

    if not prompt:
        return "Try: 'add buy milk', 'list', 'done 2', 'remove 3', 'clear', or 'next'."

    low = prompt.lower()

    # Route by intent
    if re.search(r"\b(list|show|tasks)\b", low):
        return await _cmd_list(prompt)

    if re.search(r"\b(add|todo|task|remember|note|create|append)\b", low):
        return await _cmd_add(prompt)

    if re.search(r"\b(done|complete|finish|close|mark\s+\d+\s+done)\b", low):
        return await _cmd_done(prompt)

    if re.search(r"\b(remove|delete)\b", low):
        return await _cmd_remove(prompt)

    if re.fullmatch(r"\s*clear\s*", low):
        return await _cmd_clear(prompt)

    if re.search(r"\bnext\b", low):
        return await _cmd_next(prompt)

    return await _cmd_add(prompt)