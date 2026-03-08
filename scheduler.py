import os
import json
import re
from pdf2image import convert_from_path
from PIL import Image
from google import genai

client = genai.Client()

SUPPORTED_IMAGES = [".jpg", ".jpeg", ".png"]
SUPPORTED_PDF = ".pdf"

def pdf_to_images(path):
    ext = os.path.splitext(path)[1].lower()

    if(ext == SUPPORTED_PDF):
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
    