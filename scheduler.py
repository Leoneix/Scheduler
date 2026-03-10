import os
import json
import re
import sys
import ast
from pdf2image import convert_from_path
from PIL import Image
from google import genai
from tkinter import Tk, filedialog


API_KEY = "YOUR_API_KEY"
client = genai.Client(api_key=API_KEY)

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

        images = convert_from_path(path)
        files = []

        for i, img in enumerate(images):

            name = f"page_{i}.png"
            img.save(name)
            files.append(name)

        return files

    elif ext in SUPPORTED_IMAGES:

        return [path]

    else:
        raise ValueError("Unsupported file format")


import time
import base64
import google.genai as genai
from google.genai.errors import ClientError as GeminiClientError
# from groq import Groq
# from google.cloud import vision as cloud_vision
# from google.api_core.client_options import ClientOptions

GEMINI_MODEL = "gemini-3.1-flash-lite-preview"
# GROQ_MODEL = "llama-3.3-70b-versatile"

# groq_client = Groq(api_key=API_KEY1)
# _vision_client = cloud_vision.ImageAnnotatorClient(
#     client_options=ClientOptions(api_key=API_KEY)
# )

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


# def _ocr_image(image_bytes: bytes) -> str:
#     """Use Google Cloud Vision API to extract text from an image."""
#     image = cloud_vision.Image(content=image_bytes)
#     response = _vision_client.document_text_detection(image=image)
#     if response.error.message:
#         raise RuntimeError(f"Cloud Vision error: {response.error.message}")
#     return response.full_text_annotation.text or ""


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


def _parse_schedule_gemini(ocr_text: str) -> str:
    """Parse schedule JSON from OCR text using Gemini (fallback)."""
    max_retries = 3
    for attempt in range(max_retries):
        try:
            response = client.models.generate_content(
                model=GEMINI_MODEL,
                contents=[PARSE_PROMPT],
            )
            return response.text
        except GeminiClientError as e:
            if e.status_code == 429 and attempt < max_retries - 1:
                retry_delay = 10 * (attempt + 1)  # 10s, 20s
                print(f"Gemini rate limit hit, retrying in {retry_delay}s (attempt {attempt + 1}/{max_retries})...")
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

    max_retries = 3
    for attempt in range(max_retries):
        try:
            response = client.models.generate_content(
                model=GEMINI_MODEL,
                contents=[
                    PARSE_PROMPT,
                    genai.types.Part.from_bytes(data=image_bytes, mime_type=mime_type),
                ],
            )
            return response.text
        except GeminiClientError as e:
            if e.status_code == 429 and attempt < max_retries - 1:
                retry_delay = 10 * (attempt + 1)  # 10s, 20s
                print(f"Gemini rate limit hit, retrying in {retry_delay}s (attempt {attempt + 1}/{max_retries})...")
                time.sleep(retry_delay)
            else:
                raise
        except Exception:
            raise


REQUIRED_FIELDS = ["day", "start_time", "end_time", "title", "venue"]


def is_valid_event(event):
    for field in REQUIRED_FIELDS:
        value = event.get(field)
        if not isinstance(value, str) or not value.strip():
            return False
    return True


def parse_json(text):
    """Extract JSON array from text, handling mixed content."""
    
    # First, try to find a clean JSON array
    match = re.search(r"\[.*\]", text, re.S)
    
    if match:
        json_str = match.group()
        
        # Try to parse it as-is
        try:
            return json.loads(json_str)
        except json.JSONDecodeError:
            pass
        
        # If that fails, try to parse as Python literal
        try:
            parsed = ast.literal_eval(json_str)
            
            # Convert to proper JSON format if needed
            if isinstance(parsed, list):
                return parsed
            elif isinstance(parsed, dict):
                return [parsed]
        except (ValueError, SyntaxError):
            pass
    
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

        valid_events = [e for e in parsed if is_valid_event(e)]
        print(f"Found {len(valid_events)} valid events out of {len(parsed)} parsed events")
        
        events.extend(valid_events)

    return events

from datetime import datetime, timedelta

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
        day = normalize_day_name(e.get("day"))
        start_time = str(e.get("start_time") or "").strip()
        end_time = str(e.get("end_time") or "").strip()

        if not title:
            continue

        if not day:
            continue

        if not start_time:
            continue

        if not end_time:
            continue

        e["title"] = title
        e["day"] = day
        e["start_time"] = start_time
        e["end_time"] = end_time
        cleaned.append(e)

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
