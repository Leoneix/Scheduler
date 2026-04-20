import os
import json
import re
import base64
import time
from pdf2image import convert_from_path
from PIL import Image
from openai import OpenAI
from tkinter import Tk, filedialog


API_KEY = os.environ.get("OPENROUTER_API_KEY")
client = OpenAI(api_key=API_KEY, base_url="https://openrouter.ai/api/v1")

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


def extract_schedule(image_path):

    with open(image_path, "rb") as f:
        image_bytes = f.read()

    prompt = """
This image contains a weekly timetable.

Interpret the table and extract all events.

Return ONLY JSON in this format:
Omit JSON where any of the fields are empty or NULL

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

    data_url = f"data:image/png;base64,{base64.b64encode(image_bytes).decode('ascii')}"

    response = client.chat.completions.create(
        model=os.environ.get("OPENROUTER_MODEL", "google/gemini-2.5-flash"),
        messages=[
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {"type": "image_url", "image_url": {"url": data_url}},
                ],
            }
        ],
        temperature=0,
        max_tokens=1200,
    )

    return response.choices[0].message.content or ""


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

def main():

    file_path = select_file()

    events = decipher_schedule(file_path)

    print("\nParsed Schedule:\n")

    for e in events:
        print(f"{e['day']}  {e['start_time']} - {e['end_time']}  {e['title']}")


if __name__ == "__main__":
    main()
