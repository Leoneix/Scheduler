import ast
import base64
import hashlib
import json
import os
import re
import sys
import time
from datetime import datetime, timedelta

try:
    import fitz  # pymupdf
except ModuleNotFoundError as exc:
    raise ModuleNotFoundError(
        "PyMuPDF is not available or the wrong 'fitz' package is installed. "
        "Uninstall 'fitz' and install 'pymupdf' from requirements.txt."
    ) from exc
from openai import APIStatusError, OpenAI, RateLimitError
try:
    from tkinter import Tk, filedialog
    _TKINTER_AVAILABLE = True
except ImportError:
    _TKINTER_AVAILABLE = False


OPENROUTER_MODEL = os.environ.get("OPENROUTER_MODEL", "google/gemini-3-flash-preview")
_openrouter_client = None


def _get_openrouter_client() -> OpenAI:
    global _openrouter_client
    if _openrouter_client is not None:
        return _openrouter_client

    api_key = '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'
    if not api_key:
        raise RuntimeError("OPENROUTER_API_KEY is not set")

    _openrouter_client = OpenAI(api_key=api_key, base_url="https://openrouter.ai/api/v1")
    return _openrouter_client

SUPPORTED_IMAGES = [".jpg", ".jpeg", ".png"]
SUPPORTED_PDF = ".pdf"

from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
import os

SCOPES = ["https://www.googleapis.com/auth/calendar"]

def authenticate_google():

    flow = InstalledAppFlow.from_client_secrets_file(
        "credential.json",
        SCOPES
    )

    creds = flow.run_local_server(port=0)

    service = build("calendar", "v3", credentials=creds)

    return service

def select_file():
    if not _TKINTER_AVAILABLE:
        raise RuntimeError("tkinter is not available in this environment")
    root = Tk()
    root.withdraw()  # hide main tkinter window

    file_path = filedialog.askopenfilename(
        title="Select Schedule File",
        filetypes=[
            ("Schedule Files", "*.pdf *.jpg *.jpeg *.png"),
            ("PDF files", "*.pdf"),
            ("Image files", "*.jpg *.jpeg *.png"),
        ],
    )

    return file_path

def get_images_from_file(path):

    ext = os.path.splitext(path)[1].lower()

    if ext == SUPPORTED_PDF:

        doc = fitz.open(path)
        files = []

        for i, page in enumerate(doc):

            name = f"page_{i}.png"
            page.get_pixmap(dpi=150).save(name)
            files.append(name)

        return files

    elif ext in SUPPORTED_IMAGES:

        return [path]

    else:
        raise ValueError("Unsupported file format")


# from groq import Groq

# GROQ_MODEL = "llama-3.3-70b-versatile"

# groq_client = Groq(api_key=API_KEY1)

PARSE_PROMPT = """Look at this timetable/schedule image and extract all class events.

IMPORTANT: Return ONLY a valid JSON array, nothing else. No explanations, code, or text.

Return exactly this format:
[
{"day":"Monday","start_time":"09:00","end_time":"10:00","title":"Subject","slot":"A1","venue":"CB-524"},
{"day":"Tuesday","start_time":"10:00","end_time":"11:00","title":"Class","slot":"B2","venue":"AB1-543"}
]

For each event:
- day: Day name (Monday, Tuesday, etc.)
- start_time: HH:MM format
- end_time: HH:MM format
- title: Subject or class name
- slot: Slot identifier (e.g., L1, TA1, A1)
- venue: Room/venue name (Format: CB-G16, CB-524)
"""

# def _parse_schedule_groq(ocr_text: str) -> str:
#     """Parse schedule JSON from OCR text using Groq."""
#     completion = groq_client.chat.completions.create(
#         model=GROQ_MODEL,
#         messages=[
#             {
#                 "role": "user",
#                 "content": PARSE_PROMPT_TEMPLATE.format(ocr_text=ocr_text),
#             }
#         ],
#     )
#     return completion.choices[0].message.content


def _image_to_data_url(image_bytes: bytes, mime_type: str) -> str:
    encoded = base64.b64encode(image_bytes).decode("ascii")
    return f"data:{mime_type};base64,{encoded}"


def _parse_schedule_openrouter(image_bytes: bytes, mime_type: str) -> str:
    """Parse schedule JSON from an uploaded timetable image using OpenRouter."""
    client = _get_openrouter_client()
    max_retries = 3
    for attempt in range(max_retries):
        try:
            response = client.chat.completions.create(
                model=OPENROUTER_MODEL,
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": PARSE_PROMPT},
                            {
                                "type": "image_url",
                                "image_url": {"url": _image_to_data_url(image_bytes, mime_type)},
                            },
                        ],
                    }
                ],
                temperature=0,
                max_tokens=1200,
            )
            return response.choices[0].message.content or ""
        except (RateLimitError, APIStatusError) as e:
            if getattr(e, "status_code", None) == 429 and attempt < max_retries - 1:
                retry_delay = 10 * (attempt + 1)  # 10s, 20s
                print(
                    f"OpenRouter rate limit hit, retrying in {retry_delay}s (attempt {attempt + 1}/{max_retries})..."
                )
                time.sleep(retry_delay)
            else:
                raise
        except Exception:
            raise


_MIME_MAP = {".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png"}

def extract_schedule(image_path):
    mime_type = _MIME_MAP.get(os.path.splitext(image_path)[1].lower(), "image/png")

    with open(image_path, "rb") as f:
        image_bytes = f.read()

    return _parse_schedule_openrouter(image_bytes, mime_type)


REQUIRED_FIELDS = ["day", "start_time", "end_time", "title", "venue"]


def is_valid_event(event):
    for field in REQUIRED_FIELDS:
        value = event.get(field)
        if not isinstance(value, str) or not value.strip():
            return False
    return True


def normalize_extracted_event(event):
    """Normalize model event keys/values before validation."""
    if not isinstance(event, dict):
        return {}

    normalized = dict(event)

    day = str(
        normalized.get("day")
        or normalized.get("weekday")
        or normalized.get("days")
        or normalized.get("date")
        or ""
    ).strip()

    title = str(
        normalized.get("title")
        or normalized.get("subject")
        or normalized.get("course")
        or normalized.get("class")
        or normalized.get("name")
        or ""
    ).strip()

    start_time = str(
        normalized.get("start_time")
        or normalized.get("start")
        or normalized.get("from")
        or normalized.get("startTime")
        or ""
    ).strip()

    end_time = str(
        normalized.get("end_time")
        or normalized.get("end")
        or normalized.get("to")
        or normalized.get("endTime")
        or ""
    ).strip()

    if not start_time or not end_time:
        time_range = str(
            normalized.get("time_range")
            or normalized.get("time")
            or normalized.get("timing")
            or ""
        ).strip()
        m = re.match(
            r"^\s*(\d{1,2}(?::\d{2})?\s*(?:[AaPp][Mm])?)\s*(?:-|to|–|—)\s*(\d{1,2}(?::\d{2})?\s*(?:[AaPp][Mm])?)\s*$",
            time_range,
        )
        if m:
            if not start_time:
                start_time = m.group(1).strip()
            if not end_time:
                end_time = m.group(2).strip()

    normalized["day"] = day
    normalized["start_time"] = start_time
    normalized["end_time"] = end_time
    normalized["title"] = title
    normalized["slot"] = str(
        normalized.get("slot")
        or normalized.get("section")
        or normalized.get("batch")
        or ""
    ).strip()

    venue = str(
        normalized.get("venue")
        or normalized.get("location")
        or normalized.get("room")
        or ""
    ).strip()
    normalized["venue"] = venue or "TBD"

    return normalized


def _coerce_events_payload(payload):
    if isinstance(payload, list):
        return [e for e in payload if isinstance(e, dict)]

    if isinstance(payload, dict):
        # Support common wrappers returned by models.
        for key in ("events", "schedule", "classes", "items", "data", "result"):
            value = payload.get(key)
            if isinstance(value, list):
                return [e for e in value if isinstance(e, dict)]
        return [payload]

    return []


def _salvage_events_from_array_text(text):
    """Recover event dicts from partially valid JSON array text.

    This handles common model failure modes where the output starts as a valid
    array of objects but is truncated before the final closing tokens.
    """
    if not isinstance(text, str) or "[" not in text:
        return []

    start = text.find("[")
    segment = text[start:]

    # If the array is truncated, synthesize a closing bracket for decoding.
    if "]" in segment:
        segment = segment[: segment.rfind("]") + 1]
    else:
        segment = segment + "]"

    decoder = json.JSONDecoder()
    idx = 0
    events = []

    # Skip opening bracket.
    while idx < len(segment) and segment[idx] != "[":
        idx += 1
    if idx >= len(segment):
        return []
    idx += 1

    while idx < len(segment):
        # Skip whitespace and commas between objects.
        while idx < len(segment) and segment[idx] in " \t\r\n,":
            idx += 1

        if idx >= len(segment) or segment[idx] == "]":
            break

        # Seek the next object start.
        if segment[idx] != "{":
            next_obj = segment.find("{", idx)
            if next_obj == -1:
                break
            idx = next_obj

        try:
            obj, next_idx = decoder.raw_decode(segment, idx)
        except json.JSONDecodeError:
            # Unable to decode further object (likely truncation near the end).
            break

        if isinstance(obj, dict):
            events.append(obj)

        idx = next_idx

    return events


def parse_json(text):
    """Extract schedule events from model output with tolerant parsing."""
    if not isinstance(text, str) or not text.strip():
        return []

    candidates = []

    # Prefer fenced json blocks when present.
    for block in re.findall(r"```(?:json)?\s*([\s\S]*?)```", text, re.IGNORECASE):
        candidates.append(block.strip())

    # Also try the whole response.
    candidates.append(text.strip())

    # Finally, try bracket/object substrings.
    array_match = re.search(r"\[[\s\S]*\]", text)
    object_match = re.search(r"\{[\s\S]*\}", text)
    if array_match:
        candidates.append(array_match.group(0).strip())
    if object_match:
        candidates.append(object_match.group(0).strip())

    for candidate in candidates:
        if not candidate:
            continue

        try:
            parsed = json.loads(candidate)
            events = _coerce_events_payload(parsed)
            if events:
                return events
        except json.JSONDecodeError:
            pass

        # Fallback for single quotes / Python-like literals.
        try:
            parsed = ast.literal_eval(candidate)
            events = _coerce_events_payload(parsed)
            if events:
                return events
        except (ValueError, SyntaxError):
            pass

    # Final fallback: salvage complete objects from a partially malformed array.
    salvaged = _salvage_events_from_array_text(text)
    if salvaged:
        return salvaged

    return []

def decipher_schedule(file_path):
    images = get_images_from_file(file_path)
    events = []

    for img in images:
        print("Processing:", img)

        raw = extract_schedule(img)

        print("\nModel Output:\n", raw[:500], "..." if len(raw) > 500 else "")  # Print first 500 chars

        parsed = parse_json(raw)

        if not parsed:
            print(f"Warning: No valid JSON found in model output for {img}")
            continue

        normalized_events = [normalize_extracted_event(e) for e in parsed]
        valid_events = [e for e in normalized_events if is_valid_event(e)]
        print(f"Found {len(valid_events)} valid events out of {len(parsed)} parsed events")
        
        events.extend(valid_events)

    return events

def normalize_day_name(day_name):
    value = str(day_name or "").strip().lower()

    day_map = {
        "mon": "Monday",
        "monday": "Monday",
        "tue": "Tuesday",
        "tues": "Tuesday",
        "tuesday": "Tuesday",
        "wed": "Wednesday",
        "wednesday": "Wednesday",
        "thu": "Thursday",
        "thur": "Thursday",
        "thurs": "Thursday",
        "thursday": "Thursday",
        "fri": "Friday",
        "friday": "Friday",
        "sat": "Saturday",
        "saturday": "Saturday",
        "sun": "Sunday",
        "sunday": "Sunday",
    }

    return day_map.get(value, "")


def extract_days(day_value):
    """Extract one or more canonical weekday names from free-form day text."""
    raw = str(day_value or "").strip()
    if not raw:
        return []

    direct = normalize_day_name(raw)
    if direct:
        return [direct]

    lowered = raw.lower()
    days = []

    day_patterns = [
        (r"\bmonday\b|\bmon\b", "Monday"),
        (r"\btuesday\b|\btues\b|\btue\b", "Tuesday"),
        (r"\bwednesday\b|\bwed\b", "Wednesday"),
        (r"\bthursday\b|\bthurs\b|\bthur\b|\bthu\b", "Thursday"),
        (r"\bfriday\b|\bfri\b", "Friday"),
        (r"\bsaturday\b|\bsat\b", "Saturday"),
        (r"\bsunday\b|\bsun\b", "Sunday"),
    ]

    for pattern, canonical in day_patterns:
        if re.search(pattern, lowered):
            days.append(canonical)

    # Handle compact codes like "MWF", "TR", "M T W".
    cleaned_codes = re.sub(r"[^A-Za-z]", "", raw).upper()
    compact_map = {
        "M": "Monday",
        "T": "Tuesday",
        "W": "Wednesday",
        "R": "Thursday",
        "F": "Friday",
        "S": "Saturday",
        "U": "Sunday",
    }
    for char in cleaned_codes:
        mapped = compact_map.get(char)
        if mapped and mapped not in days:
            days.append(mapped)

    return days


def normalize_time_string(value):
    """Normalize common time formats to HH:MM (24h)."""
    text = str(value or "").strip()
    if not text:
        return ""

    # Already 24h HH:MM or H:MM.
    m = re.match(r"^(\d{1,2}):(\d{2})$", text)
    if m:
        hour = int(m.group(1))
        minute = int(m.group(2))
        if 0 <= hour <= 23 and 0 <= minute <= 59:
            return f"{hour:02d}:{minute:02d}"

    # Handle 12h formats like "9 AM", "9:30pm" and loose separators.
    compact = text.lower().replace(".", "").replace(" ", "")
    m = re.match(r"^(\d{1,2})(?::?(\d{2}))?(am|pm)$", compact)
    if m:
        hour = int(m.group(1))
        minute = int(m.group(2) or "00")
        meridian = m.group(3)
        if 1 <= hour <= 12 and 0 <= minute <= 59:
            if meridian == "am":
                hour = 0 if hour == 12 else hour
            else:
                hour = hour if hour == 12 else hour + 12
            return f"{hour:02d}:{minute:02d}"

    return text

def get_next_weekday(day_name):

    days = [
        "Monday","Tuesday","Wednesday",
        "Thursday","Friday","Saturday","Sunday"
    ]

    normalized_day = normalize_day_name(day_name)
    if not normalized_day:
        raise ValueError(f"Invalid day name: {day_name}")

    today = datetime.now()

    target = days.index(normalized_day)

    delta = (target - today.weekday()) % 7

    return today + timedelta(days=delta)

import hashlib

def get_color_from_title(title):
    # create deterministic hash from title
    h = int(hashlib.md5(title.encode()).hexdigest(), 16)
    
    # map to Google Calendar color range (1–11)
    return str((h % 11) + 1)


def create_calendar_event(service, event):

    start_date = get_next_weekday(event["day"])

    start_time = f"{start_date.date()}T{event['start_time']}:00"
    end_time = f"{start_date.date()}T{event['end_time']}:00"

    color = get_color_from_title(event["title"])

    body = {
        "summary": event["title"],
        "location": event["venue"],
        "start": {
            "dateTime": start_time,
            "timeZone": "Asia/Kolkata"
        },
        "end": {
            "dateTime": end_time,
            "timeZone": "Asia/Kolkata"
        },
        "recurrence": [
            "RRULE:FREQ=WEEKLY;COUNT=10"
        ],
        "colorId": color
    }

    service.events().insert(
        calendarId="primary",
        body=body
    ).execute()

def clean_events(events):

    cleaned = []

    for e in events:
        if not isinstance(e, dict):
            continue

        title = str(e.get("title") or "").strip()
        days = extract_days(e.get("day"))
        start_time = normalize_time_string(e.get("start_time"))
        end_time = normalize_time_string(e.get("end_time"))

        if not title:
            continue

        if not days:
            continue

        if not start_time:
            continue

        if not end_time:
            continue

        slot = str(e.get("slot") or "").strip()
        venue = str(e.get("venue") or "").strip()

        for day in days:
            cleaned.append(
                {
                    **e,
                    "title": title,
                    "day": day,
                    "start_time": start_time,
                    "end_time": end_time,
                    "slot": slot,
                    "venue": venue,
                }
            )

    return cleaned

def main():
    # Check if file path is provided as command-line argument
    if len(sys.argv) > 1:
        file_path = sys.argv[1]
    else:
        file_path = select_file()
    
    if not file_path:
        print("No file selected. Exiting.")
        return
    
    events = decipher_schedule(file_path)
    events = clean_events(events)

    print("\nParsed Schedule:\n")
    for e in events:
        print(f"{e['day']}  {e['start_time']} - {e['end_time']}  {e['title']} {e['slot']} {e['venue']}")

    service = authenticate_google()
    for e in events:
        create_calendar_event(service, e)

    print("Events added to Google Calendar")


if __name__ == "__main__":
    main()
