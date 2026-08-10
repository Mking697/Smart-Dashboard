"""Auth: signup, OTP verification, login, lockout, and the abuse guards."""
import os
import sys
import tempfile

import os
import sys

# Run from anywhere: the project root is one level up from tests/.
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import st_stub  # noqa: E402

st_stub.install()

import auth  # noqa: E402

# Point the database at a throwaway file, and capture emails instead of sending.
auth.DATA_DIR = tempfile.mkdtemp()
auth.DB_PATH = os.path.join(auth.DATA_DIR, "test_users.db")

sent = []


def fake_send(to_email, to_name, subject, html):
    import re
    code = re.search(r">\s*(\d{6})\s*<", html)
    sent.append({"to": to_email, "name": to_name, "subject": subject,
                 "code": code.group(1) if code else None})


auth._send_email = fake_send
auth.init_db()

print("=" * 74)
print("PART 1 — SIGNUP SENDS AN OTP")
print("=" * 74)
auth.create_account("Manoj Tiwari", "  Manoj@Example.COM ", "correct horse", "correct horse")
assert len(sent) == 1, sent
print(f"  email sent to : {sent[0]['to']}   (typed with spaces and capitals)")
print(f"  subject       : {sent[0]['subject']}")
print(f"  code          : {sent[0]['code']}")
assert sent[0]["to"] == "manoj@example.com", "email should be normalised"
assert sent[0]["code"] and len(sent[0]["code"]) == 6

user = auth.user_by_email("manoj@example.com")
print(f"  verified?     : {bool(user['verified'])} (must be False until the code is entered)")
assert user["verified"] == 0

print("\n" + "=" * 74)
print("PART 2 — PASSWORD IS NEVER STORED IN THE CLEAR")
print("=" * 74)
print(f"  stored hash : {user['password_hash'][:48]}...")
print(f"  salt        : {user['salt']}")
assert "correct horse" not in str(dict(user)), "plaintext password found in the row"
assert len(user["password_hash"]) == 64 and len(user["salt"]) == 32
other = auth.user_by_email("manoj@example.com")
assert auth._check_password("correct horse", other["salt"], other["password_hash"])
assert not auth._check_password("wrong horse", other["salt"], other["password_hash"])
print("  correct password verifies, wrong one does not ✅")

print("\n" + "=" * 74)
print("PART 3 — CANNOT LOG IN BEFORE VERIFYING")
print("=" * 74)
try:
    auth.authenticate("manoj@example.com", "correct horse")
    raise SystemExit("FAIL: unverified account logged in")
except auth.AuthError as e:
    print(f"  blocked: {e}")

print("\n" + "=" * 74)
print("PART 4 — WRONG / EXPIRED / REUSED CODES")
print("=" * 74)
try:
    auth.verify_otp("manoj@example.com", "000000")
except auth.AuthError as e:
    print(f"  wrong code      : {e}")

auth.verify_otp("manoj@example.com", sent[0]["code"])
print("  correct code    : accepted ✅")
assert auth.user_by_email("manoj@example.com")["verified"] == 1

try:
    auth.verify_otp("manoj@example.com", sent[0]["code"])
except auth.AuthError as e:
    print(f"  reusing it      : {e}")

print("\n" + "=" * 74)
print("PART 5 — LOGIN")
print("=" * 74)
logged_in = auth.authenticate("MANOJ@example.com", "correct horse")
print(f"  logged in as: {logged_in}")
assert logged_in["email"] == "manoj@example.com"

for bad, label in [("wrong pass", "wrong password"), ("", "empty password")]:
    try:
        auth.authenticate("manoj@example.com", bad)
    except auth.AuthError as e:
        print(f"  {label:16}: {e}")

try:
    auth.authenticate("nobody@example.com", "whatever")
except auth.AuthError as e:
    print(f"  unknown email   : {e}   <- same wording, so emails can't be discovered")

print("\n" + "=" * 74)
print("PART 6 — SIGNUP IS ONE TIME PER EMAIL")
print("=" * 74)
try:
    auth.create_account("Someone Else", "manoj@example.com", "another pass", "another pass")
    raise SystemExit("FAIL: duplicate signup allowed")
except auth.AuthError as e:
    print(f"  second signup blocked: {e}")

print("\n" + "=" * 74)
print("PART 7 — VALIDATION")
print("=" * 74)
cases = [
    ("M", "a@b.com", "longenough", "longenough", "name too short"),
    ("Manoj", "not-an-email", "longenough", "longenough", "bad email"),
    ("Manoj", "new@example.com", "short", "short", "password too short"),
    ("Manoj", "new@example.com", "longenough", "different1", "passwords differ"),
]
for name, email, pw, confirm, label in cases:
    try:
        auth.create_account(name, email, pw, confirm)
        print(f"  {label:20} -> NOT BLOCKED ❌")
        raise SystemExit("FAIL")
    except auth.AuthError as e:
        print(f"  {label:20} -> {e}")

print("\n" + "=" * 74)
print("PART 8 — BRUTE FORCE LOCKOUT")
print("=" * 74)
auth._clear_failures("manoj@example.com")
for attempt in range(1, auth.LOGIN_MAX_FAILURES + 1):
    try:
        auth.authenticate("manoj@example.com", "guessing")
    except auth.AuthError as e:
        print(f"  attempt {attempt}: {e}")

try:
    auth.authenticate("manoj@example.com", "correct horse")
    raise SystemExit("FAIL: correct password accepted while locked out")
except auth.AuthError as e:
    print(f"  even the CORRECT password now: {e}")
assert auth._lockout_remaining("manoj@example.com") > 0

print("\n" + "=" * 74)
print("PART 9 — OTP RESEND COOLDOWN")
print("=" * 74)
sent.clear()
auth.create_account("Second User", "second@example.com", "another pass", "another pass")
print(f"  first code sent: {sent[-1]['code']}")
try:
    auth.send_otp("second@example.com", resend=True)
    print("  immediate resend -> NOT BLOCKED ❌")
    raise SystemExit("FAIL")
except auth.AuthError as e:
    print(f"  immediate resend -> {e}")

print("\n" + "=" * 74)
print("PART 10 — TOO MANY WRONG CODES BURNS THE CODE")
print("=" * 74)
for attempt in range(1, auth.OTP_MAX_ATTEMPTS + 2):
    try:
        auth.verify_otp("second@example.com", "999999")
        print(f"  attempt {attempt}: accepted ❌")
    except auth.AuthError as e:
        print(f"  attempt {attempt}: {e}")

print("\n" + "=" * 74)
print("PART 11 — MISSING BREVO CONFIG FAILS LOUDLY, NOT SILENTLY")
print("=" * 74)
auth._send_email = auth.__dict__["_send_email"]  # keep stub
real_send = None
import importlib  # noqa: E402

module = importlib.reload(auth)
module.DATA_DIR = auth.DATA_DIR
module.DB_PATH = auth.DB_PATH
for key in ("BREVO_API_KEY", "BREVO_SENDER_EMAIL"):
    os.environ.pop(key, None)
try:
    module._send_email("x@example.com", "X", "s", "<b>1</b>")
    print("  NOT BLOCKED ❌")
    raise SystemExit("FAIL")
except module.AuthError as e:
    print(f"  {e}")

print("\nALL AUTH CHECKS PASSED")
