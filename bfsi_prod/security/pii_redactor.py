"""
pii_redactor.py — Redacts PII (Aadhaar, PAN, card numbers, CVV) from complaint
text before it is ever stored in the database.

Two-pass approach:
  1. Regex pass — deterministic, catches well-known formats with certainty.
  2. LLM pass    — catches anything regex missed (PII written in unusual
                    ways, spelled out, OCR'd, etc.), using the same vLLM
                    client setup as classifier.py.

Masking rule: partial mask showing only the last 4 digits, e.g.
    "1234 5678 9012 3456"  ->  "XXXXXXXXXXXX3456"
    "ABCDE1234F"            ->  "XXXXXX234F"
CVV is always fully masked (showing the last 4 digits of a 3-digit CVV
makes no sense) -> "XXX"
"""

import re
import json
from openai import OpenAI
from config import VLLM_BASE_URL, VLLM_MODEL, VLLM_API_KEY

_client: OpenAI = None


def get_client() -> OpenAI:
    """Lazy-init OpenAI client — created once, reused across calls."""
    global _client
    if _client is None:
        _client = OpenAI(base_url=VLLM_BASE_URL, api_key=VLLM_API_KEY)
    return _client


# ── Pass 1: Regex ───────────────────────────────────────────────────────────

# Aadhaar: 12 digits, optionally grouped 4-4-4 with spaces or dashes
_AADHAAR_RE = re.compile(r"\b\d{4}[\s-]?\d{4}[\s-]?\d{4}\b")

# PAN: 5 letters, 4 digits, 1 letter (e.g. ABCDE1234F)
_PAN_RE = re.compile(r"\b[A-Za-z]{5}\d{4}[A-Za-z]\b")

# Card number: 13-19 digits, optionally grouped in 4s with spaces or dashes
_CARD_RE = re.compile(r"\b(?:\d[\s-]?){12,18}\d\b")

# CVV: explicit mention of "cvv" followed by 3-4 digits
_CVV_RE = re.compile(r"\bcvv\s*[:\-]?\s*\d{3,4}\b", re.IGNORECASE)


def _mask_keep_last4(match_text: str) -> str:
    """Strip non-alnum, mask all but the last 4 characters."""
    digits_only = re.sub(r"[\s-]", "", match_text)
    if len(digits_only) <= 4:
        return "X" * len(digits_only)
    return "X" * (len(digits_only) - 4) + digits_only[-4:]


def _mask_cvv(match_text: str) -> str:
    """CVV is always fully masked — partial reveal of a 3-4 digit code is meaningless."""
    return re.sub(r"\d", "X", match_text)


def regex_redact(text: str) -> tuple[str, list[str]]:
    """
    Apply regex-based redaction. Returns (redacted_text, types_found).
    Order matters: CVV and PAN are checked before the generic card-number
    regex, since PAN/CVV patterns could otherwise be partially swallowed
    by the broader digit-sequence card regex.
    """
    types_found = []

    def _cvv_sub(m):
        types_found.append("CVV")
        return _mask_cvv(m.group(0))

    def _pan_sub(m):
        types_found.append("PAN")
        return _mask_keep_last4(m.group(0))

    def _aadhaar_sub(m):
        types_found.append("Aadhaar")
        return _mask_keep_last4(m.group(0))

    def _card_sub(m):
        types_found.append("Card")
        return _mask_keep_last4(m.group(0))

    text = _CVV_RE.sub(_cvv_sub, text)
    text = _PAN_RE.sub(_pan_sub, text)
    text = _AADHAAR_RE.sub(_aadhaar_sub, text)
    text = _CARD_RE.sub(_card_sub, text)

    return text, types_found


# ── Pass 2: LLM second pass ──────────────────────────────────────────────────

_PII_SYSTEM_PROMPT = """You are a PII detection assistant for a bank complaint system.
The text below has ALREADY had common PII patterns (Aadhaar, PAN, card numbers, CVV)
redacted by a regex pass. Your job is to find any REMAINING PII that the regex missed —
for example, numbers spelled out in words, PII split across the text unusually, phone
numbers, bank account numbers, or any other sensitive identifying number.

Rules:
- Only flag genuine PII (numbers/codes that identify a specific account, document, or person).
- Do NOT flag complaint IDs, dates, amounts of money, or generic numbers (e.g. "I called 3 times").
- For each PII item found, return the exact substring as it appears in the text and its type.
- If no additional PII is found, return an empty list.

Respond ONLY with JSON in this exact format, no other text:
{"found": [{"text": "<exact substring>", "type": "<Aadhaar|PAN|Card|Phone|Account|Other>"}]}
"""


def llm_redact(text: str) -> tuple[str, list[str]]:
    """
    Second pass — ask the LLM to find any PII the regex pass missed.
    Returns (redacted_text, types_found). Falls back to returning the
    input unchanged if the LLM call fails or returns unparseable output —
    redaction should never crash complaint submission.
    """
    types_found = []
    try:
        client = get_client()
        response = client.chat.completions.create(
            model=VLLM_MODEL,
            messages=[
                {"role": "system", "content": _PII_SYSTEM_PROMPT},
                {"role": "user", "content": text},
            ],
            temperature=0,
            max_tokens=512,
        )
        raw = response.choices[0].message.content.strip()
        # strip markdown code fences if present
        raw = re.sub(r"^```(?:json)?|```$", "", raw, flags=re.MULTILINE).strip()
        parsed = json.loads(raw)
        found = parsed.get("found", [])

        for item in found:
            snippet = item.get("text", "")
            ptype   = item.get("type", "Other")
            if not snippet or snippet not in text:
                continue
            masked = _mask_keep_last4(snippet) if len(re.sub(r"\D", "", snippet)) > 4 else "X" * len(snippet)
            text = text.replace(snippet, masked)
            types_found.append(ptype)

    except Exception as e:
        print(f"[pii_redactor] LLM pass failed, continuing with regex-only result: {e}")

    return text, types_found


# ── Combined entry point ──────────────────────────────────────────────────────

def redact_pii(text: str, use_llm: bool = True) -> dict:
    """
    Full two-pass redaction. Returns:
        {
            "redacted_text": str,
            "pii_found": bool,
            "types_found": list[str],   # e.g. ["Aadhaar", "Card"]
        }
    """
    if not text or not text.strip():
        return {"redacted_text": text, "pii_found": False, "types_found": []}

    redacted, regex_types = regex_redact(text)

    llm_types = []
    if use_llm:
        redacted, llm_types = llm_redact(redacted)

    all_types = regex_types + llm_types
    return {
        "redacted_text": redacted,
        "pii_found":     len(all_types) > 0,
        "types_found":   sorted(set(all_types)),
    }


if __name__ == "__main__":
    # quick manual test
    samples = [
        "My Aadhaar 1234 5678 9012 was used to open a fake account.",
        "Card number 4111111111111234 was charged twice, CVV 123 was also leaked.",
        "PAN ABCDE1234F linked to wrong account.",
        "No PII here, just a regular complaint about slow service.",
    ]
    for s in samples:
        result = redact_pii(s, use_llm=False)  # regex-only for quick test
        print(f"IN : {s}")
        print(f"OUT: {result['redacted_text']}")
        print(f"PII: {result['types_found']}")
        print()