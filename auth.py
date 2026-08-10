"""Signup, email OTP verification and login for the dashboard.

One account per email address. A new user signs up once with their name, email
and password, confirms a six-digit code sent to that address, and from then on
simply logs in.

Storage is a local SQLite file - no extra service to run, and it survives
restarts and redeploys. Verification codes go out through Brevo's transactional
email API.

Passwords are never stored. What is stored is a PBKDF2-HMAC-SHA256 hash with a
per-user random salt, at the iteration count OWASP currently recommends. PBKDF2
ships with Python, so there is no compiled dependency that can fail to build on a
small server - the thing most likely to break a deployment at 2am.
"""

import hashlib
import hmac
import os
import re
import secrets
import sqlite3
import textwrap
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone

import requests
import streamlit as st

import theme

DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
DB_PATH = os.path.join(DATA_DIR, "users.db")

BREVO_ENDPOINT = "https://api.brevo.com/v3/smtp/email"
BREVO_TIMEOUT = 20

PBKDF2_ITERATIONS = 600_000          # OWASP guidance for PBKDF2-HMAC-SHA256
MIN_PASSWORD_LENGTH = 8

OTP_LENGTH = 6
OTP_VALID_MINUTES = 10
OTP_MAX_ATTEMPTS = 5
OTP_RESEND_SECONDS = 60

LOGIN_MAX_FAILURES = 5
LOGIN_LOCKOUT_MINUTES = 15

EMAIL_PATTERN = re.compile(r"^[^@\s]+@[^@\s]+\.[a-zA-Z]{2,}$")


class AuthError(Exception):
    """Something the user can read and act on."""


# --------------------------------------------------------------------------- #
# Storage
# --------------------------------------------------------------------------- #

@contextmanager
def _connect():
    os.makedirs(DATA_DIR, exist_ok=True)
    connection = sqlite3.connect(DB_PATH, timeout=10)
    connection.row_factory = sqlite3.Row
    try:
        yield connection
        connection.commit()
    finally:
        connection.close()


def init_db():
    """Create the tables on first run. Safe to call on every rerun."""
    with _connect() as connection:
        connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS users (
                id            INTEGER PRIMARY KEY AUTOINCREMENT,
                name          TEXT NOT NULL,
                email         TEXT NOT NULL UNIQUE COLLATE NOCASE,
                password_hash TEXT NOT NULL,
                salt          TEXT NOT NULL,
                verified      INTEGER NOT NULL DEFAULT 0,
                created_at    TEXT NOT NULL,
                last_login_at TEXT
            );

            CREATE TABLE IF NOT EXISTS otps (
                email      TEXT PRIMARY KEY COLLATE NOCASE,
                code_hash  TEXT NOT NULL,
                expires_at TEXT NOT NULL,
                sent_at    TEXT NOT NULL,
                attempts   INTEGER NOT NULL DEFAULT 0
            );

            CREATE TABLE IF NOT EXISTS login_attempts (
                email        TEXT PRIMARY KEY COLLATE NOCASE,
                failures     INTEGER NOT NULL DEFAULT 0,
                locked_until TEXT
            );
            """
        )


def _now():
    return datetime.now(timezone.utc)


def _stamp(moment):
    return moment.isoformat()


def _parse(stamp):
    return datetime.fromisoformat(stamp) if stamp else None


# --------------------------------------------------------------------------- #
# Passwords
# --------------------------------------------------------------------------- #

def _hash_password(password, salt):
    return hashlib.pbkdf2_hmac(
        "sha256", password.encode("utf-8"), bytes.fromhex(salt), PBKDF2_ITERATIONS
    ).hex()


def _check_password(password, salt, expected_hash):
    return hmac.compare_digest(_hash_password(password, salt), expected_hash)


# --------------------------------------------------------------------------- #
# Validation
# --------------------------------------------------------------------------- #

def _clean_email(email):
    email = (email or "").strip().lower()
    if not EMAIL_PATTERN.match(email):
        raise AuthError("That email address doesn't look right. Check it and try again.")
    return email


def _validate_signup(name, email, password, confirm):
    name = (name or "").strip()
    if len(name) < 2:
        raise AuthError("Please enter your name.")

    email = _clean_email(email)

    if len(password or "") < MIN_PASSWORD_LENGTH:
        raise AuthError(f"Password must be at least {MIN_PASSWORD_LENGTH} characters long.")
    if password != confirm:
        raise AuthError("The two passwords don't match.")

    return name, email


# --------------------------------------------------------------------------- #
# Email delivery (Brevo)
# --------------------------------------------------------------------------- #

def _brevo_config():
    return (
        os.getenv("BREVO_API_KEY", "").strip(),
        os.getenv("BREVO_SENDER_EMAIL", "").strip(),
        os.getenv("BREVO_SENDER_NAME", "AI Smart Dashboard").strip(),
    )


def _otp_email_html(name, code):
    return f"""
    <div style="font-family:-apple-system,Segoe UI,Roboto,sans-serif;max-width:520px;margin:auto;
                padding:32px;color:#10233b">
      <h2 style="margin:0 0 8px">Confirm your email</h2>
      <p style="color:#47576d;margin:0 0 24px">Hi {name}, here is your verification code.</p>
      <div style="font-size:34px;font-weight:700;letter-spacing:8px;text-align:center;
                  background:#eef3f9;border-radius:10px;padding:20px 0;margin-bottom:24px">
        {code}
      </div>
      <p style="color:#47576d;margin:0 0 8px">
        It expires in {OTP_VALID_MINUTES} minutes.
      </p>
      <p style="color:#7b8798;font-size:13px;margin:24px 0 0">
        If you didn't create this account, you can ignore this email — nothing has been activated.
      </p>
    </div>
    """


def _send_email(to_email, to_name, subject, html):
    """Send through Brevo. Raises AuthError with something the user can act on."""
    api_key, sender_email, sender_name = _brevo_config()

    if not api_key or not sender_email:
        raise AuthError(
            "Email delivery is not configured yet, so verification codes can't be sent. "
            "The administrator needs to set BREVO_API_KEY and BREVO_SENDER_EMAIL."
        )

    payload = {
        "sender": {"email": sender_email, "name": sender_name},
        "to": [{"email": to_email, "name": to_name}],
        "subject": subject,
        "htmlContent": html,
    }

    try:
        response = requests.post(
            BREVO_ENDPOINT,
            json=payload,
            headers={"api-key": api_key, "content-type": "application/json"},
            timeout=BREVO_TIMEOUT,
        )
    except requests.exceptions.RequestException:
        raise AuthError("Could not reach the email service. Check your connection and try again.")

    if response.status_code in (200, 201, 202):
        return

    if response.status_code in (401, 403):
        raise AuthError("The email service rejected our credentials. The administrator needs to "
                        "check the Brevo API key and that the sender address is verified.")

    detail = ""
    try:
        detail = response.json().get("message", "")
    except ValueError:
        pass
    raise AuthError(f"The email could not be sent{': ' + detail if detail else ''}.")


# --------------------------------------------------------------------------- #
# Signup and verification
# --------------------------------------------------------------------------- #

def user_by_email(email):
    with _connect() as connection:
        row = connection.execute(
            "SELECT * FROM users WHERE email = ?", (email,)
        ).fetchone()
    return dict(row) if row else None


def create_account(name, email, password, confirm):
    """Create an unverified account and email its verification code."""
    name, email = _validate_signup(name, email, password, confirm)

    existing = user_by_email(email)
    if existing and existing["verified"]:
        raise AuthError("An account with this email already exists. Please log in instead.")

    salt = secrets.token_hex(16)
    password_hash = _hash_password(password, salt)

    with _connect() as connection:
        if existing:
            # Signed up before but never confirmed - let them start over rather
            # than locking the address forever.
            connection.execute(
                "UPDATE users SET name = ?, password_hash = ?, salt = ?, created_at = ? "
                "WHERE email = ?",
                (name, password_hash, salt, _stamp(_now()), email),
            )
        else:
            connection.execute(
                "INSERT INTO users (name, email, password_hash, salt, verified, created_at) "
                "VALUES (?, ?, ?, ?, 0, ?)",
                (name, email, password_hash, salt, _stamp(_now())),
            )

    send_otp(email)
    return email


def send_otp(email, resend=False):
    """Generate a fresh code, store only its hash, and email the code."""
    email = _clean_email(email)

    account = user_by_email(email)
    if not account:
        raise AuthError("No signup found for this email. Please sign up first.")
    if account["verified"]:
        raise AuthError("This email is already verified. Please log in.")

    with _connect() as connection:
        row = connection.execute(
            "SELECT sent_at FROM otps WHERE email = ?", (email,)
        ).fetchone()

    if resend and row:
        since = (_now() - _parse(row["sent_at"])).total_seconds()
        if since < OTP_RESEND_SECONDS:
            wait = int(OTP_RESEND_SECONDS - since)
            raise AuthError(f"A code was just sent. Please wait {wait} more second(s) before asking for another.")

    code = "".join(secrets.choice("0123456789") for _ in range(OTP_LENGTH))
    now = _now()

    with _connect() as connection:
        connection.execute(
            "INSERT INTO otps (email, code_hash, expires_at, sent_at, attempts) "
            "VALUES (?, ?, ?, ?, 0) "
            "ON CONFLICT(email) DO UPDATE SET code_hash = excluded.code_hash, "
            "expires_at = excluded.expires_at, sent_at = excluded.sent_at, attempts = 0",
            (
                email,
                hashlib.sha256(code.encode()).hexdigest(),
                _stamp(now + timedelta(minutes=OTP_VALID_MINUTES)),
                _stamp(now),
            ),
        )

    _send_email(
        email,
        account["name"],
        "Your verification code",
        _otp_email_html(account["name"], code),
    )


def verify_otp(email, code):
    """Confirm the code and activate the account.

    The outcome is decided inside the transaction but raised outside it. Raising
    while the connection is open skips the commit, which would roll back the
    attempt counter and leave a six-digit code open to unlimited guessing.
    """
    email = _clean_email(email)
    code = (code or "").strip()

    problem = None

    with _connect() as connection:
        row = connection.execute("SELECT * FROM otps WHERE email = ?", (email,)).fetchone()

        if not row:
            problem = "No code is pending for this email. Please request a new one."

        elif _now() > _parse(row["expires_at"]):
            connection.execute("DELETE FROM otps WHERE email = ?", (email,))
            problem = "That code has expired. Please request a new one."

        elif row["attempts"] >= OTP_MAX_ATTEMPTS:
            connection.execute("DELETE FROM otps WHERE email = ?", (email,))
            problem = "Too many incorrect attempts. Please request a new code."

        elif not hmac.compare_digest(hashlib.sha256(code.encode()).hexdigest(), row["code_hash"]):
            connection.execute("UPDATE otps SET attempts = attempts + 1 WHERE email = ?", (email,))
            left = OTP_MAX_ATTEMPTS - (row["attempts"] + 1)
            if left > 0:
                problem = f"That code is not correct. {left} attempt(s) left."
            else:
                connection.execute("DELETE FROM otps WHERE email = ?", (email,))
                problem = "Too many incorrect attempts. Please request a new code."

        else:
            connection.execute("UPDATE users SET verified = 1 WHERE email = ?", (email,))
            connection.execute("DELETE FROM otps WHERE email = ?", (email,))

    if problem:
        raise AuthError(problem)


# --------------------------------------------------------------------------- #
# Login
# --------------------------------------------------------------------------- #

def _lockout_remaining(email):
    with _connect() as connection:
        row = connection.execute(
            "SELECT locked_until FROM login_attempts WHERE email = ?", (email,)
        ).fetchone()

    if not row or not row["locked_until"]:
        return 0

    remaining = (_parse(row["locked_until"]) - _now()).total_seconds()
    return max(0, int(remaining))


def _record_failure(email):
    with _connect() as connection:
        row = connection.execute(
            "SELECT failures FROM login_attempts WHERE email = ?", (email,)
        ).fetchone()
        failures = (row["failures"] if row else 0) + 1

        locked_until = None
        if failures >= LOGIN_MAX_FAILURES:
            locked_until = _stamp(_now() + timedelta(minutes=LOGIN_LOCKOUT_MINUTES))
            failures = 0

        connection.execute(
            "INSERT INTO login_attempts (email, failures, locked_until) VALUES (?, ?, ?) "
            "ON CONFLICT(email) DO UPDATE SET failures = excluded.failures, "
            "locked_until = excluded.locked_until",
            (email, failures, locked_until),
        )


def _clear_failures(email):
    with _connect() as connection:
        connection.execute("DELETE FROM login_attempts WHERE email = ?", (email,))


def authenticate(email, password):
    """Return the user on success. Raises AuthError with a readable reason."""
    email = _clean_email(email)

    locked = _lockout_remaining(email)
    if locked:
        raise AuthError(f"Too many failed attempts. Try again in {locked // 60 + 1} minute(s).")

    account = user_by_email(email)

    # Same message whether the address is unknown or the password is wrong, so
    # the form cannot be used to discover which emails are registered.
    if not account or not _check_password(password or "", account["salt"], account["password_hash"]):
        _record_failure(email)
        raise AuthError("Email or password is incorrect.")

    if not account["verified"]:
        raise AuthError("This email is not verified yet. Enter the code we sent you.")

    _clear_failures(email)
    with _connect() as connection:
        connection.execute(
            "UPDATE users SET last_login_at = ? WHERE email = ?", (_stamp(_now()), email)
        )

    return {"id": account["id"], "name": account["name"], "email": account["email"]}


# --------------------------------------------------------------------------- #
# Streamlit UI
# --------------------------------------------------------------------------- #

def current_user():
    return st.session_state.get("auth_user")


def logout():
    st.session_state.pop("auth_user", None)
    st.session_state["auth_mode"] = "login"


def _pitch():
    with st.expander("📘 What is this?"):
        st.markdown(textwrap.dedent(
            """
            Upload an Excel file or connect a Google Sheet, and this builds the reports
            for you — no formulas, no pivot tables, no chart settings.

            - **8 ready-made reports**, each answering one business question
            - Every chart comes with **how to read it** and **what it means**
            - Messy sheets are cleaned first: blank rows, stray spaces and placeholder text
            - Your data is drawn on a **real map**, India included properly
            """
        ))


def _signup_form():
    st.subheader("Create your account")
    st.caption("You only sign up once. After that, just log in with your email and password.")

    with st.form("signup_form"):
        name = st.text_input("Your name", placeholder="Manoj Tiwari")
        email = st.text_input("Email", placeholder="you@company.com")
        password = st.text_input("Password", type="password",
                                 help=f"At least {MIN_PASSWORD_LENGTH} characters")
        confirm = st.text_input("Confirm password", type="password")
        submitted = st.form_submit_button("Create account", use_container_width=True, type="primary")

    if submitted:
        try:
            with st.spinner("Creating your account and sending your code..."):
                created_email = create_account(name, email, password, confirm)
            st.session_state["auth_pending_email"] = created_email
            st.session_state["auth_mode"] = "verify"
            st.rerun()
        except AuthError as error:
            st.error(str(error))

    if st.button("I already have an account", key="to_login_from_signup"):
        st.session_state["auth_mode"] = "login"
        st.rerun()


def _verify_form():
    email = st.session_state.get("auth_pending_email", "")

    st.subheader("Check your email")
    st.caption(f"We sent a {OTP_LENGTH}-digit code to **{email}**. It is valid for {OTP_VALID_MINUTES} minutes.")

    with st.form("verify_form"):
        code = st.text_input("Verification code", max_chars=OTP_LENGTH, placeholder="123456")
        submitted = st.form_submit_button("Verify and continue", use_container_width=True, type="primary")

    if submitted:
        try:
            verify_otp(email, code)
            st.success("Email verified. You can log in now.")
            st.session_state["auth_mode"] = "login"
            st.session_state.pop("auth_pending_email", None)
            st.rerun()
        except AuthError as error:
            st.error(str(error))

    left, right = st.columns(2)
    with left:
        if st.button("Resend code", use_container_width=True):
            try:
                send_otp(email, resend=True)
                st.success("A new code is on its way.")
            except AuthError as error:
                st.warning(str(error))
    with right:
        if st.button("Use a different email", use_container_width=True):
            st.session_state["auth_mode"] = "signup"
            st.session_state.pop("auth_pending_email", None)
            st.rerun()

    st.caption("Nothing arrived? Check your spam folder — verification emails often land there.")


def _login_form():
    st.subheader("Log in")

    with st.form("login_form"):
        email = st.text_input("Email", placeholder="you@company.com")
        password = st.text_input("Password", type="password")
        submitted = st.form_submit_button("Log in", use_container_width=True, type="primary")

    if submitted:
        try:
            st.session_state["auth_user"] = authenticate(email, password)
            st.rerun()
        except AuthError as error:
            st.error(str(error))
            if "not verified" in str(error):
                st.session_state["auth_pending_email"] = (email or "").strip().lower()
                if st.button("Enter my code"):
                    st.session_state["auth_mode"] = "verify"
                    st.rerun()

    if st.button("Create a new account", key="to_signup_from_login"):
        st.session_state["auth_mode"] = "signup"
        st.rerun()


def require_login():
    """Gate the app. Returns the logged-in user, or renders the gate and stops."""
    init_db()

    user = current_user()
    if user:
        return user

    st.session_state.setdefault("auth_mode", "login")

    left_margin, panel, right_margin = st.columns([1, 2, 1])
    with panel:
        st.write("")
        theme.brand_header()
        st.write("")
        _pitch()
        st.divider()

        mode = st.session_state["auth_mode"]
        if mode == "signup":
            _signup_form()
        elif mode == "verify":
            _verify_form()
        else:
            _login_form()

    st.stop()


def render_account_sidebar(user):
    """Who is logged in, and the way out."""
    st.sidebar.markdown(f"👤 **{user['name']}**")
    st.sidebar.caption(user["email"])
    st.sidebar.button("Log out", use_container_width=True, on_click=logout, key="logout_button")
    st.sidebar.divider()
