import asyncio
import os
import datetime as dt
from typing import Any, Dict, List, Optional

from dateutil import tz
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials

CAL_SCOPES = ["https://www.googleapis.com/auth/calendar.readonly"]

CALENDAR_ID = os.getenv("GCAL_ID", "primary")

DEFAULT_TZ = os.getenv("LOCAL_TZ", "Europe/Helsinki")

LOOKAHEAD_HOURS = int(os.getenv("CAL_LOOKAHEAD_HOURS", "24"))


def _get_creds() -> Credentials:
    """
    Loads/refreshes OAuth credentials for Calendar.
    Use a separate token file so scopes don't collide with Gmail unless you unify them.
    """
    token_path = os.getenv("GCAL_TOKEN", "token_calendar.json")
    creds: Optional[Credentials] = None
    if os.path.exists(token_path):
        creds = Credentials.from_authorized_user_file(token_path, CAL_SCOPES)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            # credentials.json should be in your project root unless you set an env var for path
            cred_path = os.getenv("GOOGLE_CREDENTIALS", "credentials.json")
            flow = InstalledAppFlow.from_client_secrets_file(cred_path, CAL_SCOPES)
            creds = flow.run_local_server(port=0)
        with open(token_path, "w") as f:
            f.write(creds.to_json())
    return creds


def _iso(dt_naive_utc: dt.datetime) -> str:
    """Return RFC3339 with 'Z' for UTC."""
    if dt_naive_utc.tzinfo is None:
        dt_naive_utc = dt_naive_utc.replace(tzinfo=dt.timezone.utc)
    return dt_naive_utc.astimezone(dt.timezone.utc).isoformat().replace("+00:00", "Z")


def _format_time_span(start: dt.datetime, end: dt.datetime, local_tz: str) -> str:
    zone = tz.gettz(local_tz)
    s = start.astimezone(zone)
    e = end.astimezone(zone)
    return f"{s:%H:%M}–{e:%H:%M}"


def _summarize_events(items: List[Dict[str, Any]], local_tz: str) -> str:
    if not items:
        return "No events for today. 🗓️"

    zone = tz.gettz(local_tz)
    lines = []
    for ev in items[:10]:
        start_raw = ev.get("start", {})
        end_raw = ev.get("end", {})
        title = ev.get("summary", "(no title)")
        loc = ev.get("location")
        if "dateTime" in start_raw and "dateTime" in end_raw:
            s = dt.datetime.fromisoformat(start_raw["dateTime"].replace("Z", "+00:00"))
            e = dt.datetime.fromisoformat(end_raw["dateTime"].replace("Z", "+00:00"))
            span = _format_time_span(s, e, local_tz)
            suffix = f" @ {loc}" if loc else ""
            lines.append(f"{span} — {title}{suffix}")
        else:
            # all-day
            the_date = start_raw.get("date")
            if the_date:
                d_obj = dt.datetime.fromisoformat(the_date)
                d_local = d_obj.replace(tzinfo=dt.timezone.utc).astimezone(zone)
                lines.append(f"All day — {title} ({d_local:%Y-%m-%d})")
            else:
                lines.append(f"{title}")

    # Top summary
    first_start = items[0].get("start", {}).get("dateTime") or items[0].get("start", {}).get("date")
    top = f"{len(items)} event(s) today"
    if first_start:
        top += f"; first starts at {dt.datetime.fromisoformat(first_start.replace('Z','+00:00')).astimezone(zone):%H:%M}"
    return top + ". " + " | ".join(lines)


def _plan_day_sync(prompt: str, local_tz: str) -> str:
    # Compute today's window in UTC
    zone = tz.gettz(local_tz)
    now_local = dt.datetime.now(zone)
    start_local = now_local.replace(hour=0, minute=0, second=0, microsecond=0)
    # look until end of day or configured lookahead
    end_local = start_local + dt.timedelta(days=1)

    start_utc = start_local.astimezone(dt.timezone.utc).replace(tzinfo=None)
    end_utc = end_local.astimezone(dt.timezone.utc).replace(tzinfo=None)

    creds = _get_creds()
    service = build("calendar", "v3", credentials=creds)

    events_result = service.events().list(
        calendarId=CALENDAR_ID,
        timeMin=_iso(start_utc),
        timeMax=_iso(end_utc),
        singleEvents=True,
        orderBy="startTime",
        maxResults=100,
    ).execute()

    items: List[Dict[str, Any]] = events_result.get("items", [])
    return _summarize_events(items, local_tz)


async def plan_day(state: Dict[str, Any]) -> str:
    """
    LangGraph tool entrypoint.
    - Reads optional 'timezone' or 'tz' or 'location' from state
    - Returns a short summary string of today's events
    """
    prompt = (state.get("prompt") or "").lower()
    local_tz = state.get("timezone") or state.get("tz") or DEFAULT_TZ
    try:
        return await asyncio.to_thread(_plan_day_sync, prompt, local_tz)
    except HttpError as e:
        # Common cause: 403 due to consent screen / tester list
        return (
            "Calendar error: access denied (check OAuth consent, add your account as a Test user, "
            "enable Calendar API, then delete token_calendar.json and retry)."
        )
    except Exception as e:
        return f"Calendar error: {e}"