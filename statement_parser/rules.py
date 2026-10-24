"""Category rules: text found in a transaction → category. Saved in category_rules.json."""

import json
from pathlib import Path

RULES_FILE = Path(__file__).parent.parent / "category_rules.json"

CATEGORIES = [
    "Housing", "Transportation", "Utility", "Grocery", "Drinks and Restaurants", "Clothing",
    "Medical", "Subscription", "Insurance", "Household", "Personal", "Education", "Gifts",
    "Entertainment", "Vacation", "Other expense", "Freelance subscriptions", "Dad",
    "Salary", "Other income", "Investment",
]
# Set by hand or by the app only; never learned as rules.
SPECIAL_CATEGORIES = ["Starting Balance", "Exclude"]


def load() -> dict:
    try:
        return json.loads(RULES_FILE.read_text())
    except FileNotFoundError:
        return {}


def save(rules: dict):
    ordered = dict(sorted(rules.items(), key=lambda kv: kv[0].upper()))
    RULES_FILE.write_text(json.dumps(ordered, indent=2, ensure_ascii=False) + "\n")


def guess(key: str, description: str, rules: dict) -> str:
    """The category of the longest rule text found in the transaction, or ''.
    Spaces are ignored, as OCR sometimes drops or adds them."""
    haystack = _squash(f"{key} {description}")
    hits = [text for text in rules if text.strip() and _squash(text) in haystack]
    return rules[max(hits, key=len)] if hits else ""


def _squash(text: str) -> str:
    return "".join(text.split()).upper()


def learn(pairs, rules: dict) -> int:
    """Adds or updates a rule for each (key, category). Returns how many rules changed."""
    changed = 0
    for key, category in pairs:
        key = (key or "").strip()
        if not key or category not in CATEGORIES or guess(key, "", rules) == category:
            continue  # nothing to learn, or an existing rule already gives this category
        existing = next((k for k in rules if k.upper() == key.upper()), None)
        if existing is None or rules[existing] != category:
            rules.pop(existing, None)
            rules[key] = category
            changed += 1
    return changed
