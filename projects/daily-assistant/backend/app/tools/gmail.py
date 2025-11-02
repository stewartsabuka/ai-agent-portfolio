# tools/gmail.py
import asyncio
import datetime as dt
import os
from collections import Counter
from typing import Any, Dict, List, Optional

from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials

# Read-only Gmail scope
SCOPES = ["https://www.googleapis.com/auth/gmail.readonly"]

GMAIL_QUERY = os.getenv("GMAIL_QUERY", "is:unread in:inbox newer_than:2d")
GMAIL_MAX_RESULTS = int(os.getenv("GMAIL_MAX_RESULTS", "25"))


def _get_creds() -> Credentials:
    creds = None
    if os.path.exists("token.json"):
        creds = Credentials.from_authorized_user_file("token.json", SCOPES)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file("credentials.json", SCOPES)
            creds = flow.run_local_server(port=0)
        with open("token.json", "w") as token:
            token.write(creds.to_json())
    return creds


def _gmail_list_messages(service, query: str, max_results: int) -> List[str]:
    resp = service.users().messages().list(userId="me", q=query, maxResults=max_results).execute()
    return [m["id"] for m in resp.get("messages", [])]


def _gmail_get_message(service, msg_id: str) -> Dict[str, Any]:
    return service.users().messages().get(userId="me", id=msg_id, format="metadata", metadataHeaders=["From","Subject","Date"]).execute()


def _parse_header(headers: List[Dict[str, str]], name: str) -> Optional[str]:
    for h in headers:
        if h.get("name") == name:
            return h.get("value")
    return None


def _clean_sender(sender_val: str) -> str:
    if not sender_val:
        return "Unknown"
    if "<" in sender_val and ">" in sender_val:
        return sender_val.split("<", 1)[0].strip().strip('"')
    return sender_val


def _summarize_messages(meta_messages: List[Dict[str, Any]]) -> str:
    if not meta_messages:
        return "No unread emails 🎉"

    senders = []
    subjects = []
    times: List[dt.datetime] = []

    for m in meta_messages:
        headers = m.get("payload", {}).get("headers", [])
        s_from = _clean_sender(_parse_header(headers, "From") or "")
        s_subj = (_parse_header(headers, "Subject") or "").strip()
        s_date = _parse_header(headers, "Date") or ""
        senders.append(s_from)
        if s_subj:
            subjects.append(s_subj)
        try:
            from email.utils import parsedate_to_datetime
            d = parsedate_to_datetime(s_date)
            if d.tzinfo:
                d = d.astimezone(dt.timezone.utc).replace(tzinfo=None)
            times.append(d)
        except Exception:
            pass

    count = len(meta_messages)
    top_senders = ", ".join([f"{name}×{n}" for name, n in Counter(senders).most_common(3)])
    latest = max(times) if times else None
    latest_str = latest.isoformat(timespec="minutes") + "Z" if latest else "unknown time"

    preview = "; ".join(subjects[:3]) if subjects else "no subjects"

    return f"{count} unread email(s). Top senders: {top_senders}. Latest around {latest_str}. Subjects: {preview}"


def _summarize_unread_sync(prompt: str) -> str:
    """
    Synchronous core:
    - Builds Gmail service
    - Lists unread messages with query (optionally adjusted by prompt)
    - Returns a compact summary string
    """
    query = GMAIL_QUERY
    if "24h" in prompt or "day" in prompt:
        query = "is:unread in:inbox newer_than:1d"
    elif "week" in prompt or "7 days" in prompt:
        query = "is:unread in:inbox newer_than:7d"

    creds = _get_creds()
    service = build("gmail", "v1", credentials=creds)
    ids = _gmail_list_messages(service, query, GMAIL_MAX_RESULTS)
    if not ids:
        return "No unread emails 🎉"

    meta = [_gmail_get_message(service, mid) for mid in ids]
    return _summarize_messages(meta)


async def summarize_unread(state: Dict[str, Any]) -> str:
    """
    LangGraph tool entrypoint.
    Expects: state['prompt'] (string)
    Returns: short summary string
    """
    prompt = (state.get("prompt") or "").lower()
    try:
        return await asyncio.to_thread(_summarize_unread_sync, prompt)
    except HttpError as e:
        return f"Failed to access Gmail API: {e}"
    except Exception as e:
        return f"Email summary error: {e}"