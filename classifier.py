"""
classifier.py — BFSI complaint classification via vLLM.
Calls Qwen/Llama on AMD MI300X through OpenAI-compatible endpoint.
"""

import json
import time
import uuid
from openai import OpenAI
from config import (
    VLLM_BASE_URL, VLLM_MODEL, VLLM_API_KEY,
    CATEGORIES, SLA_MAP, TEAM_MAP, JSON_PATH,
    CLASSIFY_SYSTEM_PROMPT,
)
from db import insert_complaint, log_classification

_client: OpenAI = None


def get_client() -> OpenAI:
    """Lazy-init OpenAI client — created once, reused across calls."""
    global _client
    if _client is None:
        _client = OpenAI(base_url=VLLM_BASE_URL, api_key=VLLM_API_KEY)
    return _client


def classify(
    complaint:    str,
    customer_id:  str,
    cust_name:    str,
    cust_email:   str  = None,
    channel:      str  = "web",
    branch:       str  = None,
    account_type: str  = "savings",
) -> dict:
    """
    Classify a single complaint via vLLM.
    Saves result to complaints table and logs to classification_log.
    Returns the full record dict including latency_ms.
    Raises ValueError if model returns non-JSON.
    """
    complaint_id = "CMP-" + str(uuid.uuid4())[:8].upper()
    user_msg     = (
        f'Complaint: "{complaint}"\n'
        f"Channel: {channel}\n"
        f"Account type: {account_type}"
    )

    t0       = time.time()
    response = get_client().chat.completions.create(
        model=VLLM_MODEL,
        messages=[
            {"role": "system", "content": CLASSIFY_SYSTEM_PROMPT},
            {"role": "user",   "content": user_msg},
        ],
        temperature=0.1,
        max_tokens=512,
    )
    latency_ms = int((time.time() - t0) * 1000)
    raw        = response.choices[0].message.content.strip()

    try:
        result = json.loads(raw.replace("```json", "").replace("```", "").strip())
    except json.JSONDecodeError:
        log_classification({
            "complaint_id": complaint_id, "raw_response": raw,
            "parse_success": False, "latency_ms": latency_ms,
            "model_used": VLLM_MODEL,
        })
        raise ValueError(f"Non-JSON response from model: {raw[:200]}")

    category = result.get("category", "general")
    if category not in CATEGORIES:
        category = "general"
    priority = result.get("priority", "P3")
    sla_days = SLA_MAP.get(priority, 5)
    team     = result.get("team", TEAM_MAP.get(category, "General Support"))

    record = {
        "complaint_id": complaint_id,
        "customer_id":  customer_id,
        "cust_name":    cust_name,
        "cust_email":   cust_email,
        "complaint":    complaint,
        "channel":      channel,
        "branch":       branch,
        "account_type": account_type,
        "category":     category,
        "priority":     priority,
        "team":         team,
        "sentiment":    result.get("sentiment", "neutral"),
        "sla_days":     sla_days,
        "summary":      result.get("summary", complaint[:100]),
        "reasoning":    result.get("reasoning", ""),
        "status":       "open",
    }

    insert_complaint(record)
    log_classification({
        "complaint_id": complaint_id, "raw_response": raw,
        "parse_success": True, "latency_ms": latency_ms,
        "model_used": VLLM_MODEL,
    })

    record["latency_ms"] = latency_ms
    return record


def classify_from_json(json_path: str = JSON_PATH) -> list[dict]:
    """
    Read a JSON file of complaint dicts and classify each one.
    Required keys per record: complaint, customer_id, cust_name.
    Returns list of result dicts (failures include 'error' key).
    """
    import os

    if not os.path.exists(json_path):
        print(f"[classifier] File not found: {json_path}")
        return []

    with open(json_path, encoding="utf-8") as f:
        tickets = json.load(f)

    if not tickets:
        print("[classifier] JSON file is empty.")
        return []

    results = []
    total   = len(tickets)

    for i, t in enumerate(tickets):
        try:
            r = classify(
                complaint=t["complaint"],
                customer_id=t["customer_id"],
                cust_name=t["cust_name"],
                cust_email=t.get("cust_email"),
                channel=t.get("channel", "web"),
                branch=t.get("branch"),
                account_type=t.get("account_type", "savings"),
            )
            results.append(r)
            print(
                f"[{i+1}/{total}] {r['complaint_id']} "
                f"→ {r['category']} {r['priority']} ({r['latency_ms']}ms)"
            )
        except Exception as e:
            print(f"[{i+1}/{total}] FAILED: {e}")
            results.append({"error": str(e), "complaint": t.get("complaint", "")})

    return results
