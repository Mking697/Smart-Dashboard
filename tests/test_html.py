"""Guard the two ways our own UI can render itself unreadable.

1. Streamlit renders markdown, and markdown turns any line indented by four or
   more spaces into a code block - so pretty-printed markup appears on screen as
   its own source code.
2. Streamlit wraps a button label in a <p>, so a global paragraph colour beats
   the button's own colour and the label vanishes into the background.
"""
import re
import os
import sys

# Run from anywhere: the project root is one level up from tests/.
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import st_stub  # noqa: E402

stub = st_stub.install()

rendered = []
stub.markdown = lambda body, **k: rendered.append((str(body), k))

import theme  # noqa: E402

print("=" * 74)
print("PART 1 — html() COLLAPSES INDENTED MARKUP")
print("=" * 74)
messy = """
    <div class="a">
        <div class="b">Hello</div>
    </div>
"""
clean = theme.html(messy)
print(f"  before: {messy!r}")
print(f"  after : {clean!r}")
assert "\n" not in clean, "newlines survived"
assert not clean.startswith(" "), "leading indent survived"
assert '<div class="b">Hello</div>' in clean, "content was mangled"

print("\n" + "=" * 74)
print("PART 2 — EVERY RENDERED BLOCK IS ONE LINE")
print("=" * 74)

rendered.clear()
theme.brand_header()
theme.hero()

INDENTED = re.compile(r"^ {4,}", re.MULTILINE)

for body, _kwargs in rendered:
    lines = body.count("\n")
    indented = bool(INDENTED.search(body))
    label = body.strip()[:54].replace("\n", " ")
    status = "OK" if lines == 0 and not indented else "WOULD RENDER AS CODE"
    print(f"  [{status:20}] lines={lines} indented={indented}  {label}…")
    assert lines == 0, f"multi-line HTML becomes a code block: {label}"
    assert not indented, f"indented HTML becomes a code block: {label}"

print(f"\n  blocks checked: {len(rendered)}")
assert len(rendered) >= 3, "expected the logo, the hero and the cards"

print("\n" + "=" * 74)
print("PART 3 — THE MARKUP IS STILL VALID")
print("=" * 74)
joined = " ".join(body for body, _ in rendered)
for tag in ["svg", "div", "h2", "p", "span"]:
    opens = len(re.findall(rf"<{tag}[\s>]", joined))
    closes = len(re.findall(rf"</{tag}>", joined))
    print(f"  <{tag}>{'':>{6 - len(tag)}} open={opens:3} close={closes:3}")
    assert opens == closes, f"unbalanced <{tag}>"

for needle in ['class="al-brand__name"', 'class="al-hero"', 'class="al-card"']:
    assert needle in joined, f"missing {needle}"
print("\n  brand, hero and cards all present")

print("\n" + "=" * 74)
print("PART 4 — NO EMOJI USED AS AN ICON IN THE MARKUP")
print("=" * 74)
emoji = re.findall(r"[\U0001F300-\U0001FAFF\u2600-\u27BF]", joined)
print(f"  emoji found in rendered HTML: {emoji or 'none'}")
assert not emoji, "the design system asks for SVG glyphs, not emoji"

print("\n" + "=" * 74)
print("PART 5 — BUTTON LABELS MUST BE READABLE")
print("=" * 74)

css = theme._css()

required = {
    "label colour stated on button children": ".stButton > button *",
    "download button covered":                '[data-testid="stDownloadButton"] > button',
    "form submit button covered":             '[data-testid="stFormSubmitButton"] > button',
    "primary label forced white":             '.stButton > button[kind="primary"] *',
    "sidebar buttons get their own colour":   '[data-testid="stSidebar"] .stButton > button *',
}
for label, needle in required.items():
    present = needle in css
    print(f"  [{'OK' if present else 'MISSING':7}] {label}")
    assert present, f"CSS is missing: {needle}"

# A blanket colour on every sidebar descendant repaints button labels too -
# that is what made the white "Log out" button unreadable.
blanket = '[data-testid="stSidebar"] * {'
print(f"\n  blanket sidebar colour rule present: {blanket in css}")
assert blanket not in css, "a blanket sidebar * rule will repaint button labels again"

print("  white-on-gradient and dark-on-white both stated explicitly")

print("\nALL HTML RENDER CHECKS PASSED")
