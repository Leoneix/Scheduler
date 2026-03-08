import os
import json
import re
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


import google.genai as genai
from google.genai import types

def extract_schedule(image_path):

    with open(image_path, "rb") as f:
        image_bytes = f.read()

    prompt = """
This image contains a weekly timetable.

Interpret the table and extract all events.

Return ONLY JSON in this format:

[
 {
  "day": "Monday",
  "start_time": "09:00",
  "end_time": "10:00",
  "title": "Subject"
  "slot": "A1"
  "venue": "CB-G16"
 }
]
"""

    response = client.models.generate_content(
        model="gemini-2.5-flash",
        contents=[
            prompt,
            types.Part.from_bytes(
                data=image_bytes,
                mime_type="image/png"
            )
        ],
    )

    return response.text


def parse_json(text):

    match = re.search(r"\[.*\]", text, re.S)

    if match:
        return json.loads(match.group())

    return []

def decipher_schedule(file_path):
    images = get_images_from_file(file_path)
    events = []

    for img in images:
        print("Processing:", img)

        raw = extract_schedule(img)

        print("\nModel Output:\n", raw)

        parsed = parse_json(raw)

        events.extend(parsed)

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

def create_calendar_event(service, event):

    start_date = get_next_weekday(event["day"])

    start_time = f"{start_date.date()}T{event['start_time']}:00"
    end_time = f"{start_date.date()}T{event['end_time']}:00"

    body = {
        "summary": event["title"],
        "start": {
            "dateTime": start_time,
            "timeZone": "Asia/Kolkata"
        },
        "end": {
            "dateTime": end_time,
            "timeZone": "Asia/Kolkata"
        },
        "recurrence": [
            "RRULE:FREQ=WEEKLY"
        ]
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
    file_path = select_file()
    events = decipher_schedule(file_path)
    events = clean_events(events)

    print("\nParsed Schedule:\n")
    for e in events:
        print(f"{e['day']}  {e['start_time']} - {e['end_time']}  {e['title']}")

    service = authenticate_google()
    for e in events:
        create_calendar_event(service, e)

    print("Events added to Google Calendar")


if __name__ == "__main__":
    main()
