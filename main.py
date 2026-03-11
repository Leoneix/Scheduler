import os
import tempfile
import contextlib
from pathlib import Path
from typing import List, Optional

from fastapi import FastAPI, File, UploadFile, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, RedirectResponse
from pydantic import BaseModel

from google_auth_oauthlib.flow import Flow
import json as _json
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request as GoogleAuthRequest
from googleapiclient.discovery import build

from google.genai.errors import ServerError as GeminiServerError, ClientError as GeminiClientError

from scheduler import (
    extract_schedule,
    parse_json,
    is_valid_event,
    clean_events,
    create_calendar_event,
)
import fitz  # pymupdf

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

SCOPES = ["https://www.googleapis.com/auth/calendar"]
TOKEN_FILE = "token.json"
USER_EMAIL_FILE = "user_email.txt"
CREDENTIAL_FILE = "credential.json"
APP_URL = os.environ.get("APP_URL", "http://localhost:8000")
REDIRECT_URI = f"{APP_URL}/auth/callback"
SUPPORTED_EXTENSIONS = {".pdf", ".jpg", ".jpeg", ".png"}

# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------

@contextlib.asynccontextmanager
async def lifespan(app):
    # Reset auth state on every server start
    for f in (TOKEN_FILE, USER_EMAIL_FILE):
        if os.path.exists(f):
            os.remove(f)
    # On cloud deployments, seed token from environment variable so auth
    # survives container restarts without requiring re-authentication.
    token_env = os.environ.get("GOOGLE_TOKEN_JSON")
    if token_env:
        with open(TOKEN_FILE, "w") as f:
            f.write(token_env)
    yield


app = FastAPI(title="Schedule Importer", version="1.0.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Serve the frontend
app.mount("/static", StaticFiles(directory="static"), name="static")


@app.get("/", include_in_schema=False)
def root():
    return FileResponse("static/index.html")

# ---------------------------------------------------------------------------
# Pydantic models
# ---------------------------------------------------------------------------

class ScheduleEvent(BaseModel):
    day: str
    start_time: str
    end_time: str
    title: str
    slot: Optional[str] = ""
    venue: Optional[str] = ""


class ExtractResponse(BaseModel):
    events: List[ScheduleEvent]
    count: int


class ScheduleResponse(BaseModel):
    message: str
    events: List[ScheduleEvent]

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _load_credential_config() -> dict:
    """Load OAuth client config from GOOGLE_CREDENTIAL_JSON env var or credential.json file."""
    cred_env = os.environ.get("GOOGLE_CREDENTIAL_JSON")
    if cred_env:
        return _json.loads(cred_env)
    if os.path.exists(CREDENTIAL_FILE):
        with open(CREDENTIAL_FILE) as f:
            return _json.load(f)
    raise HTTPException(
        status_code=500,
        detail=f"Google credentials not found. Set GOOGLE_CREDENTIAL_JSON env var or add '{CREDENTIAL_FILE}'.",
    )


def _get_calendar_service():
    """Return an authenticated Google Calendar service using a stored token."""
    creds = None

    if os.path.exists(TOKEN_FILE):
        creds = Credentials.from_authorized_user_file(TOKEN_FILE, SCOPES)

    if creds and creds.expired and creds.refresh_token:
        creds.refresh(GoogleAuthRequest())
        with open(TOKEN_FILE, "w") as f:
            f.write(creds.to_json())

    if not creds or not creds.valid:
        raise HTTPException(
            status_code=401,
            detail="Not authenticated with Google Calendar. Call POST /auth first.",
        )

    return build("calendar", "v3", credentials=creds)


def _images_from_upload(tmp_path: str, suffix: str) -> List[str]:
    """Convert an uploaded file to a list of image paths inside a temp dir."""
    tmp_dir = tempfile.mkdtemp()

    if suffix == ".pdf":
        doc = fitz.open(tmp_path)
        paths = []
        for i, page in enumerate(doc):
            img_path = os.path.join(tmp_dir, f"page_{i}.png")
            page.get_pixmap(dpi=150).save(img_path)
            paths.append(img_path)
        return paths

    # Image file — copy into tmp_dir so cleanup is consistent
    dest = os.path.join(tmp_dir, f"upload{suffix}")
    import shutil
    shutil.copy2(tmp_path, dest)
    return [dest]


def _extract_events_from_upload(file: UploadFile) -> List[dict]:
    """Save upload to a temp file, extract events, clean up, return events."""
    suffix = Path(file.filename).suffix.lower()

    # Write upload to a temp file
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
        tmp.write(file.file.read())
        tmp_path = tmp.name

    tmp_dir = None
    try:
        img_paths = _images_from_upload(tmp_path, suffix)
        tmp_dir = os.path.dirname(img_paths[0]) if img_paths else None

        events: List[dict] = []
        for img in img_paths:
            try:
                raw = extract_schedule(img)
            except GeminiClientError as e:
                if e.status_code == 429:
                    raise HTTPException(
                        status_code=429,
                        detail="AI API rate limit exceeded. Please wait a minute and try again.",
                    )
                raise HTTPException(status_code=502, detail=f"Gemini API error: {e}")
            except GeminiServerError as e:
                raise HTTPException(
                    status_code=503,
                    detail=f"Gemini AI is temporarily unavailable (high demand). Please try again in a moment. [{e}]",
                )
            parsed = parse_json(raw)
            events.extend(e for e in parsed if is_valid_event(e))

        return clean_events(events)
    finally:
        os.unlink(tmp_path)
        if tmp_dir and os.path.isdir(tmp_dir):
            import shutil
            shutil.rmtree(tmp_dir, ignore_errors=True)

# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@app.get("/health", tags=["Utility"])
def health():
    """Liveness check."""
    return {"status": "ok"}


def _read_user_email() -> str:
    if os.path.exists(USER_EMAIL_FILE):
        with open(USER_EMAIL_FILE) as f:
            return f.read().strip()
    return ""


def _fetch_and_save_email(creds) -> str:
    """Fetch the user's primary calendar ID (their Google account email)."""
    try:
        service = build("calendar", "v3", credentials=creds)
        primary = service.calendars().get(calendarId="primary").execute()
        email = primary.get("id", "")
        if email:
            with open(USER_EMAIL_FILE, "w") as f:
                f.write(email)
        return email
    except Exception:
        return ""


@app.get("/auth/status", tags=["Auth"])
def auth_status():
    """Return whether the server currently holds valid Google Calendar credentials."""
    if not os.path.exists(TOKEN_FILE):
        return {"authenticated": False, "email": ""}
    try:
        creds = Credentials.from_authorized_user_file(TOKEN_FILE, SCOPES)
        if creds and creds.valid:
            return {"authenticated": True, "email": _read_user_email()}
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(GoogleAuthRequest())
            with open(TOKEN_FILE, "w") as f:
                f.write(creds.to_json())
            return {"authenticated": True, "email": _read_user_email()}
    except Exception:
        pass
    return {"authenticated": False, "email": ""}


@app.get("/auth/login", tags=["Auth"])
def auth_login():
    """Return the Google OAuth2 authorization URL. The client should redirect the user to it."""
    cred_config = _load_credential_config()
    flow = Flow.from_client_config(cred_config, SCOPES, redirect_uri=REDIRECT_URI)
    auth_url, _ = flow.authorization_url(
        access_type="offline",
        include_granted_scopes="true",
        prompt="select_account",
    )
    return {"auth_url": auth_url}


@app.get("/auth/callback", tags=["Auth"])
def auth_callback(request: Request):
    """Handle the Google OAuth2 redirect callback."""
    import traceback
    try:
        cred_config = _load_credential_config()
        flow = Flow.from_client_config(cred_config, SCOPES, redirect_uri=REDIRECT_URI)
        # Use the full callback URL so oauthlib can parse code + scope correctly
        os.environ.setdefault("OAUTHLIB_RELAX_TOKEN_SCOPE", "1")
        flow.fetch_token(authorization_response=str(request.url))
        creds = flow.credentials

        with open(TOKEN_FILE, "w") as f:
            f.write(creds.to_json())

        email = _fetch_and_save_email(creds)
        return RedirectResponse(url=f"/?auth=success&email={email}")
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"OAuth callback failed: {exc}\n{traceback.format_exc()}")


@app.post("/extract", response_model=ExtractResponse, tags=["Schedule"])
def extract(file: UploadFile = File(...)):
    """
    Upload a timetable image (JPG/PNG) or PDF.
    Returns the extracted schedule events as JSON — no calendar changes.
    """
    suffix = Path(file.filename).suffix.lower()
    if suffix not in SUPPORTED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file type '{suffix}'. Allowed: {sorted(SUPPORTED_EXTENSIONS)}",
        )

    events = _extract_events_from_upload(file)
    return {"events": events, "count": len(events)}


@app.post("/schedule", response_model=ScheduleResponse, tags=["Schedule"])
def schedule(file: UploadFile = File(...)):
    """
    Upload a timetable image (JPG/PNG) or PDF.
    Extracts events and creates recurring weekly entries in Google Calendar.
    Requires prior authentication via POST /auth.
    """
    suffix = Path(file.filename).suffix.lower()
    if suffix not in SUPPORTED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file type '{suffix}'. Allowed: {sorted(SUPPORTED_EXTENSIONS)}",
        )

    events = _extract_events_from_upload(file)
    if not events:
        raise HTTPException(status_code=422, detail="No valid events could be extracted from the file.")

    service = _get_calendar_service()
    for e in events:
        create_calendar_event(service, e)

    return {
        "message": f"{len(events)} events added to Google Calendar.",
        "events": events,
    }


# ---------------------------------------------------------------------------
# Entry point (python main.py)
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
