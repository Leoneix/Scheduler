import os
import json
import re
from pdf2image import convert_from_path
from PIL import Image
from google import genai
from tkinter import Tk, filedialog


API_KEY = "AIzaSyDUpQa9tYHQEiNmgBfj9nAGccggRotqP9Q"
client = genai.Client(api_key=API_KEY)

SUPPORTED_IMAGES = [".jpg", ".jpeg", ".png"]
SUPPORTED_PDF = ".pdf"

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


REQUIRED_FIELDS = ["day", "start_time", "end_time", "title", "venue"]


def is_valid_event(event):
    for field in REQUIRED_FIELDS:
        value = event.get(field)
        if not isinstance(value, str) or not value.strip():
            return False
    return True


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

        events.extend(e for e in parsed if is_valid_event(e))

    return events

def main():

    file_path = select_file()

    events = decipher_schedule(file_path)

    print("\nParsed Schedule:\n")

    for e in events:
        print(f"{e['day']}  {e['start_time']} - {e['end_time']}  {e['title']}")


if __name__ == "__main__":
    main()
