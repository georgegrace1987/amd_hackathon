"""
data_generator.py — Synthetic BFSI complaint generator via vLLM.
Generates realistic labelled complaints with customer metadata.
"""

import json
import random
from openai import OpenAI
from config import (
    VLLM_BASE_URL, VLLM_MODEL, VLLM_API_KEY,
    CATEGORY_WEIGHTS, CATEGORY_ACCOUNT_AFFINITY,
    CHANNELS, MUMBAI_BRANCHES, EMAIL_DOMAINS,
    INDIAN_FIRST_NAMES, INDIAN_LAST_NAMES, JSON_PATH,
)
from db import load_json_to_db

_client: OpenAI = None

CATEGORY_PROMPTS = {
    "fraud": """Generate 1 realistic Indian bank customer complaint about fraud or unauthorized transaction.
1-3 sentences, urgent tone. Occasional Hindi-English mix is fine.
Examples:
- My HDFC credit card was used for Rs 8500 at a Delhi merchant I never visited. Block immediately.
- Someone made 3 UPI transactions from my account totaling Rs 15000 last night.
Return ONLY the complaint text, nothing else.""",

    "card_dispute": """Generate 1 realistic Indian bank customer complaint about a card issue.
1-3 sentences, frustrated tone.
Examples:
- My SBI debit card got blocked after paying at petrol pump. Need it unblocked urgently.
- Rs 2300 Zomato charge showing twice in my statement. I only ordered once.
Return ONLY the complaint text, nothing else.""",

    "kyc_onboarding": """Generate 1 realistic Indian bank customer complaint about KYC or account opening delay.
1-3 sentences, impatient tone.
Examples:
- I submitted Aadhaar and PAN for new savings account 3 weeks ago. Still showing under review.
- Video KYC appointment was scheduled but no one called. This is the third time rescheduling.
Return ONLY the complaint text, nothing else.""",

    "loan_emi": """Generate 1 realistic Indian bank customer complaint about loan EMI or home loan.
1-3 sentences, concerned tone.
Examples:
- Extra EMI of Rs 4200 deducted this month from home loan account. No prior notice given.
- I requested loan prepayment last month but full EMI still deducted.
Return ONLY the complaint text, nothing else.""",

    "net_banking_upi": """Generate 1 realistic Indian bank customer complaint about UPI failure or net banking.
1-3 sentences, frustrated tone.
Examples:
- Paid Rs 8500 to vendor via UPI. Money debited but vendor says not received.
- Net banking login stopped working after OTP verification. Getting error code 502.
Return ONLY the complaint text, nothing else.""",

    "branch_atm": """Generate 1 realistic Indian bank customer complaint about ATM or branch service.
1-3 sentences, annoyed tone.
Examples:
- ATM at Andheri West dispensed Rs 500 less but full amount got debited.
- Visited branch 3 times for fixed deposit issue. Every time told to come next day.
Return ONLY the complaint text, nothing else.""",

    "insurance": """Generate 1 realistic Indian bank customer complaint about insurance claim or policy.
1-3 sentences, distressed tone.
Examples:
- My father passed away in March. Life insurance claim submitted with all documents. Still pending 4 months.
- Health insurance cashless request rejected at hospital despite valid policy.
Return ONLY the complaint text, nothing else.""",

    "general": """Generate 1 realistic Indian bank customer complaint about a general service issue.
1-3 sentences, neutral or mildly frustrated tone.
Examples:
- Not receiving monthly account statement on registered email for last 2 months.
- Want to update mobile number linked to my account. Branch form process is too complicated.
Return ONLY the complaint text, nothing else.""",
}


def get_client() -> OpenAI:
    global _client
    if _client is None:
        _client = OpenAI(base_url=VLLM_BASE_URL, api_key=VLLM_API_KEY)
    return _client


def gen_customer_id() -> str:
    return str(random.randint(1000_0000_0000_0000, 9999_9999_9999_9999))


def gen_customer_name() -> str:
    return f"{random.choice(INDIAN_FIRST_NAMES)} {random.choice(INDIAN_LAST_NAMES)}"


def gen_email(name: str) -> str | None:
    if random.random() < 0.70:
        local = name.lower().replace(" ", ".") + str(random.randint(10, 99))
        return f"{local}@{random.choice(EMAIL_DOMAINS)}"
    return None


def gen_branch(channel: str) -> str | None:
    if channel == "branch":
        return random.choice(MUMBAI_BRANCHES)
    if random.random() < 0.20:
        return random.choice(MUMBAI_BRANCHES)
    return None


def generate_one(category: str) -> dict:
    """Generate a single synthetic complaint record."""
    response = get_client().chat.completions.create(
        model=VLLM_MODEL,
        messages=[{"role": "user", "content": CATEGORY_PROMPTS[category]}],
        temperature=0.85,
        max_tokens=150,
    )
    text      = response.choices[0].message.content.strip().strip('"')
    channel   = random.choice(CHANNELS)
    cust_name = gen_customer_name()
    affinities = CATEGORY_ACCOUNT_AFFINITY.get(category, ["savings"])

    return {
        "customer_id":  gen_customer_id(),
        "cust_name":    cust_name,
        "cust_email":   gen_email(cust_name),
        "complaint":    text,
        "category":     category,
        "channel":      channel,
        "branch":       gen_branch(channel),
        "account_type": random.choice(affinities),
    }


def generate_dataset(count: int = 80) -> list[dict]:
    """Generate `count` synthetic complaints with weighted category distribution."""
    categories  = list(CATEGORY_WEIGHTS.keys())
    weights     = list(CATEGORY_WEIGHTS.values())
    target_cats = random.choices(categories, weights=weights, k=count)

    dataset = []
    for i, cat in enumerate(target_cats):
        try:
            record = generate_one(cat)
            dataset.append(record)
            print(f"[{i+1}/{count}] {cat} | {record['customer_id']} | {record['complaint'][:60]}...")
        except Exception as e:
            print(f"[{i+1}/{count}] FAILED ({cat}): {e}")

    return dataset


def save_to_json(dataset: list[dict], path: str = JSON_PATH) -> None:
    """Save dataset to JSON file."""
    import json as _json
    with open(path, "w", encoding="utf-8") as f:
        _json.dump(dataset, f, indent=2, ensure_ascii=False)
    print(f"[generator] Saved {len(dataset)} records to {path}")


def run_generator(count: int = 80, output: str = "both") -> list[dict]:
    """
    Full generation pipeline.
    output: 'json' | 'db' | 'both'
    Returns the generated dataset.
    """
    print(f"\nGenerating {count} complaints via {VLLM_MODEL}...\n")
    dataset = generate_dataset(count)

    if not dataset:
        print("[generator] No records generated — check VLLM_MODEL and endpoint.")
        return []

    if output in ("json", "both"):
        save_to_json(dataset)
    if output in ("db", "both"):
        load_json_to_db(JSON_PATH)

    dist = {}
    for r in dataset:
        dist[r["category"]] = dist.get(r["category"], 0) + 1
    print(f"\n[generator] Done. {len(dataset)} records. Distribution: {dist}")
    return dataset
