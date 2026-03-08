#  Schedule to Google Calendar
![GitHub last commit](https://img.shields.io/github/last-commit/Leoneix/Scheduler)[![MIT License](https://img.shields.io/badge/License-MIT-green.svg)](https://choosealicense.com/licenses/mit/)![Python](https://img.shields.io/badge/Python-3.10+-3776AB?logo=python&logoColor=white)![Gemini](https://img.shields.io/badge/AI-Gemini-ff6f00)![Google Calendar](https://img.shields.io/badge/Google%20Calendar-API-4285F4?logo=googlecalendar&logoColor=white)![Status](https://img.shields.io/badge/Project-MVP-yellow)![Maintained](https://img.shields.io/badge/Maintained-Yes-brightgreen)![Open Source](https://img.shields.io/badge/Open%20Source-Yes-blue)

A Python tool that converts **weekly schedules from images or PDFs into Google Calendar events automatically** using AI.

Instead of manually typing schedules into your calendar, simply upload a screenshot or PDF of your timetable and the tool will:

1. Extract events using **Gemini Vision**
2. Let you **review/edit detected events**
3. Automatically create **recurring Google Calendar events**

---

##  Features

-  **File Support:** Upload PDF, PNG, JPG, or JPEG schedules.
-  **AI Parsing:** Automatically extracts the timetable structure using Gemini Vision.
-  **Human-in-the-loop:** Interactive JSON correction interface before syncing.
-  **Smart Filtering:** Filters out invalid or empty events.
-  **Automation:** Creates weekly recurring Google Calendar events.
-  **Secure:** Uses official Google OAuth authentication.
-  **Smart Dates:** Automatically detects the next weekday occurrence for the initial event.

---

## Installation

Install my-project with npm

```bash
  pip install google-genai pdf2image pillow google-api-python-client google-auth-httplib2 google-auth-oauthlib
```

### 1. Get a **Gemini API Key**

Create a **free API key at Google AI Studio**.

Add it directly to your script (or set it as an environment variable):

```bash
API_KEY="YOUR_API_KEY"
```

---

### 2. Enable the **Google Calendar API**

1. Open the **Google Cloud Console**.
2. Navigate to **APIs & Services → Library**.
3. Search for **Google Calendar API**.
4. Click **Enable**.

---

### 3. Create **OAuth Credentials**

1. Navigate to **APIs & Services → Credentials**.
2. Click **Create Credentials → OAuth Client ID**.
3. Select **Desktop Application** as the application type.
4. Download the resulting JSON file.
5. Rename it to:

```bash
credentials.json
```

6. Place it in your **project root folder**.
    
