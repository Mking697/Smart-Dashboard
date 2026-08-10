"""Google Sheets connector for the AI Smart Dashboard.

The app treats a Google Spreadsheet exactly like an uploaded Excel workbook, so
every fetch here returns the same shape: ``{worksheet_name: raw DataFrame}``.
Header cleaning is NOT done here - that stays with ``auto_fix_headers`` in app.py.

Two access modes are supported:

1. Public / "Anyone with the link" sheets -> no credentials needed. We hit the
   XLSX export endpoint, which returns every worksheet in one shot.
2. Private sheets -> a Google service account (read-only) via the Sheets API v4.
   The user shares the sheet with the service account email, like a teammate.

Both paths raise ``SheetAccessError`` with a human-readable ``hint`` so the UI can
tell the user exactly what to fix instead of dumping a stack trace.
"""

import io
import json
import re

import pandas as pd
import requests

# Public export endpoints (no auth). The /d/e/ form is for File > Share > Publish.
_EXPORT_URL = "https://docs.google.com/spreadsheets/d/{sheet_id}/export?format=xlsx"
_PUBLISHED_URL = "https://docs.google.com/spreadsheets/d/e/{sheet_id}/pub?output=xlsx"

_SCOPES = ["https://www.googleapis.com/auth/spreadsheets.readonly"]

_REQUEST_TIMEOUT = 45  # seconds
_MAX_DOWNLOAD_BYTES = 60 * 1024 * 1024  # 60 MB guard so a huge sheet can't OOM us


class SheetAccessError(Exception):
    """Raised when a sheet cannot be reached. ``hint`` is shown to the user."""

    def __init__(self, message, hint=""):
        super().__init__(message)
        self.hint = hint


# --------------------------------------------------------------------------- #
# URL / ID parsing
# --------------------------------------------------------------------------- #

def extract_sheet_id(url_or_id):
    """Pull the spreadsheet key out of any Google Sheets URL (or a bare ID).

    Returns ``(sheet_id, is_published)``. ``is_published`` is True for the
    /spreadsheets/d/e/2PACX-.../pubhtml style links, which use a different
    export endpoint.
    """
    if not url_or_id or not str(url_or_id).strip():
        raise SheetAccessError(
            "No Google Sheet link provided.",
            hint="Paste the full sheet URL from your browser address bar.",
        )

    text = str(url_or_id).strip()

    published = re.search(r"/spreadsheets/d/e/([a-zA-Z0-9-_]+)", text)
    if published:
        return published.group(1), True

    standard = re.search(r"/spreadsheets/d/([a-zA-Z0-9-_]+)", text)
    if standard:
        return standard.group(1), False

    # A bare ID pasted directly - Google keys are long and have no spaces/slashes.
    if re.fullmatch(r"[a-zA-Z0-9-_]{20,}", text):
        return text, False

    raise SheetAccessError(
        "That does not look like a Google Sheet link.",
        hint="Expected something like https://docs.google.com/spreadsheets/d/<ID>/edit",
    )


def extract_gid(url_or_id):
    """Return the ``gid`` (worksheet id) from a URL, or None if absent."""
    match = re.search(r"[#&?]gid=([0-9]+)", str(url_or_id or ""))
    return match.group(1) if match else None


# --------------------------------------------------------------------------- #
# Public sheets - XLSX export, zero credentials
# --------------------------------------------------------------------------- #

def fetch_public_workbook(sheet_id, is_published=False):
    """Download a link-shared sheet as XLSX and parse every worksheet."""
    url = (_PUBLISHED_URL if is_published else _EXPORT_URL).format(sheet_id=sheet_id)

    try:
        response = requests.get(url, timeout=_REQUEST_TIMEOUT, allow_redirects=True)
    except requests.exceptions.RequestException as exc:
        raise SheetAccessError(
            f"Could not reach Google Sheets: {exc}",
            hint="Check your internet connection or proxy settings and try again.",
        )

    if response.status_code in (401, 403):
        raise SheetAccessError(
            "This sheet is private.",
            hint="Either set sharing to 'Anyone with the link -> Viewer', or connect "
                 "a service account below and share the sheet with it.",
        )
    if response.status_code == 404:
        raise SheetAccessError(
            "Sheet not found (404).",
            hint="Double-check the link - the spreadsheet may have been deleted or the ID is wrong.",
        )
    if response.status_code != 200:
        raise SheetAccessError(
            f"Google returned HTTP {response.status_code}.",
            hint="Try again in a moment, or use the service account route.",
        )

    # A private sheet redirects to the Google login page: HTML, not a workbook.
    content_type = response.headers.get("Content-Type", "").lower()
    if "html" in content_type:
        raise SheetAccessError(
            "This sheet is private (Google asked us to sign in).",
            hint="Set sharing to 'Anyone with the link -> Viewer', or connect a "
                 "service account below and share the sheet with its email.",
        )

    if len(response.content) > _MAX_DOWNLOAD_BYTES:
        raise SheetAccessError(
            "This spreadsheet is too large to sync (over 60 MB).",
            hint="Split it into smaller sheets, or filter the data before syncing.",
        )

    try:
        workbook = pd.read_excel(io.BytesIO(response.content), sheet_name=None)
    except Exception as exc:
        raise SheetAccessError(
            f"Downloaded the sheet but could not read it: {exc}",
            hint="The file may be corrupt or use an unsupported format.",
        )

    return _drop_empty_sheets(workbook)


# --------------------------------------------------------------------------- #
# Private sheets - service account + Sheets API v4
# --------------------------------------------------------------------------- #

def parse_credentials(creds_json):
    """Validate a service account JSON key and return it as a dict."""
    if not creds_json:
        raise SheetAccessError(
            "No service account credentials loaded.",
            hint="Upload your service account JSON key to read private sheets.",
        )
    try:
        data = json.loads(creds_json) if isinstance(creds_json, str) else dict(creds_json)
    except (ValueError, TypeError):
        raise SheetAccessError(
            "The credentials file is not valid JSON.",
            hint="Download a fresh key from Google Cloud Console > IAM > Service Accounts > Keys.",
        )

    if data.get("type") != "service_account" or "client_email" not in data:
        raise SheetAccessError(
            "That JSON is not a service account key.",
            hint="Use the key generated for a Service Account, not an OAuth client secret.",
        )
    return data


def service_account_email(creds_json):
    """Convenience helper for the UI: which email must the sheet be shared with."""
    try:
        return parse_credentials(creds_json).get("client_email", "")
    except SheetAccessError:
        return ""


def fetch_private_workbook(sheet_id, creds_json):
    """Read every worksheet of a private sheet using a read-only service account."""
    info = parse_credentials(creds_json)

    try:
        from google.oauth2.service_account import Credentials
        from googleapiclient.discovery import build
        from googleapiclient.errors import HttpError
    except ImportError:
        raise SheetAccessError(
            "Google API client libraries are missing.",
            hint="Run: pip install google-api-python-client google-auth",
        )

    try:
        credentials = Credentials.from_service_account_info(info, scopes=_SCOPES)
        service = build("sheets", "v4", credentials=credentials, cache_discovery=False)

        meta = service.spreadsheets().get(
            spreadsheetId=sheet_id, fields="sheets.properties.title"
        ).execute()
        titles = [s["properties"]["title"] for s in meta.get("sheets", [])]

        if not titles:
            raise SheetAccessError(
                "This spreadsheet has no worksheets.",
                hint="Add at least one tab with data and sync again.",
            )

        # UNFORMATTED_VALUE keeps numbers numeric; FORMATTED_STRING keeps dates readable.
        batch = service.spreadsheets().values().batchGet(
            spreadsheetId=sheet_id,
            ranges=titles,
            valueRenderOption="UNFORMATTED_VALUE",
            dateTimeRenderOption="FORMATTED_STRING",
        ).execute()

    except HttpError as exc:
        status = getattr(getattr(exc, "resp", None), "status", None)
        if status == 403:
            raise SheetAccessError(
                "The service account is not allowed to open this sheet.",
                hint=f"Open the sheet > Share > add {info.get('client_email')} as Viewer. "
                     "Also make sure the Google Sheets API is enabled in your Cloud project.",
            )
        if status == 404:
            raise SheetAccessError(
                "Sheet not found (404).",
                hint="Check the link - the spreadsheet ID may be wrong or it was deleted.",
            )
        if status == 429:
            raise SheetAccessError(
                "Google rate-limited this project.",
                hint="Wait a minute before syncing again, or raise your Sheets API quota.",
            )
        raise SheetAccessError(
            f"Google Sheets API error: {exc}",
            hint="Verify the service account key and that the Sheets API is enabled.",
        )
    except SheetAccessError:
        raise
    except Exception as exc:
        raise SheetAccessError(
            f"Could not authenticate with Google: {exc}",
            hint="Re-download the service account key and check the system clock is correct.",
        )

    workbook = {}
    for title, value_range in zip(titles, batch.get("valueRanges", [])):
        workbook[title] = _rows_to_dataframe(value_range.get("values", []))

    return _drop_empty_sheets(workbook)


# --------------------------------------------------------------------------- #
# Dispatcher
# --------------------------------------------------------------------------- #

def load_workbook(url_or_id, creds_json=None):
    """Fetch a Google Sheet as ``{worksheet_name: DataFrame}``.

    Uses the service account when credentials are supplied, otherwise falls back
    to the public export endpoint.
    """
    sheet_id, is_published = extract_sheet_id(url_or_id)

    if creds_json:
        if is_published:
            # Published-to-web links expose no real spreadsheet ID for the API.
            return fetch_public_workbook(sheet_id, is_published=True)
        return fetch_private_workbook(sheet_id, creds_json)

    return fetch_public_workbook(sheet_id, is_published=is_published)


# --------------------------------------------------------------------------- #
# Internals
# --------------------------------------------------------------------------- #

def _rows_to_dataframe(rows):
    """Turn raw Sheets API rows into a DataFrame shaped like ``pd.read_excel``.

    Sheets returns ragged rows, so we pad them, and we name blank headers
    ``Unnamed: N`` on purpose - that is the marker ``auto_fix_headers`` looks for
    when it hunts for the real header row in a messy sheet.
    """
    if not rows:
        return pd.DataFrame()

    width = max(len(row) for row in rows)
    padded = [list(row) + [None] * (width - len(row)) for row in rows]

    header, body = padded[0], padded[1:]

    columns, seen = [], {}
    for index, raw_name in enumerate(header):
        name = "" if raw_name is None else str(raw_name).strip()
        name = name or f"Unnamed: {index}"
        if name in seen:
            seen[name] += 1
            name = f"{name}.{seen[name]}"
        else:
            seen[name] = 0
        columns.append(name)

    frame = pd.DataFrame(body, columns=columns)
    # Empty cells arrive as "" - make them real nulls so null counts stay honest.
    return frame.replace({"": None})


def _drop_empty_sheets(workbook):
    """Discard worksheets that carry no usable data."""
    cleaned = {
        name: frame
        for name, frame in workbook.items()
        if frame is not None and not frame.empty and not frame.dropna(how="all").empty
    }

    if not cleaned:
        raise SheetAccessError(
            "The spreadsheet opened fine but every tab is empty.",
            hint="Add some rows to the sheet, then sync again.",
        )
    return cleaned
