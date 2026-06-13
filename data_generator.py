"""
data_generator.py — Synthetic BFSI data generator via vLLM.
Generates realistic labelled complaints AND customer KYC records.

Functions:
    run_generator(count, output)  — generate synthetic complaints
    run_kyc_generator(count)      — generate synthetic customer_kyc records
"""

import json
import random
from openai import OpenAI
from config import (
    VLLM_BASE_URL, VLLM_MODEL, VLLM_API_KEY,
    CATEGORY_WEIGHTS, CATEGORY_ACCOUNT_AFFINITY,
    CHANNELS, MUMBAI_BRANCHES, EMAIL_DOMAINS,
    INDIAN_FIRST_NAMES, INDIAN_LAST_NAMES, JSON_PATH,
    TIERS_CITIES,
)
from db import load_json_to_db, get_conn

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


# ── KYC generator ─────────────────────────────────────────────────────────────

INDIAN_STATES = [
    "Andhra Pradesh", "Bihar", "Delhi", "Gujarat", "Haryana",
    "Karnataka", "Kerala", "Madhya Pradesh", "Maharashtra", "Punjab",
    "Rajasthan", "Tamil Nadu", "Telangana", "Uttar Pradesh", "West Bengal",
]

KYC_SYSTEM_PROMPT = """You are a synthetic data generator for an Indian bank.
Generate realistic Indian customer KYC details.
Return ONLY a valid JSON object with these exact fields — no markdown, no extra text:

- cust_phone: 10-digit Indian mobile number starting with 9, 8, 7, or 6
- date_of_birth: date in YYYY-MM-DD format, age between 21 and 65
- pan_number: valid format — 5 uppercase letters, 4 digits, 1 uppercase letter (e.g. ABCDE1234F)
- aadhaar_number: 12-digit number (no spaces)
- address: realistic Indian street address (house number, street, locality)
- pincode: valid 6-digit Indian pincode

Return ONLY the JSON object. No explanation."""


def generate_kyc_record(customer_id: str, cust_name: str,
                        cust_email: str, city: str) -> dict:
    """Generate KYC fields for one customer via vLLM."""
    user_msg = (
        f"Customer name: {cust_name}\n"
        f"City: {city}\n"
        f"Generate realistic KYC details for this Indian bank customer."
    )
    response = get_client().chat.completions.create(
        model=VLLM_MODEL,
        messages=[
            {"role": "system", "content": KYC_SYSTEM_PROMPT},
            {"role": "user",   "content": user_msg},
        ],
        temperature=0.85,
        max_tokens=200,
    )
    raw = response.choices[0].message.content.strip()

    try:
        fields = json.loads(raw.replace("```json", "").replace("```", "").strip())
    except json.JSONDecodeError:
        raise ValueError(f"Non-JSON KYC response: {raw[:150]}")

    # derive state from city
    city_state_map = {
        "Mumbai": "Maharashtra", "Pune": "Maharashtra", "Nagpur": "Maharashtra",
        "Delhi": "Delhi", "Noida": "Delhi", "Faridabad": "Haryana",
        "Bangalore": "Karnataka", "Mysore": "Karnataka",
        "Chennai": "Tamil Nadu", "Coimbatore": "Tamil Nadu", "Madurai": "Tamil Nadu",
        "Hyderabad": "Telangana", "Warangal": "Telangana",
        "Kolkata": "West Bengal", "Siliguri": "West Bengal",
        "Ahmedabad": "Gujarat", "Surat": "Gujarat", "Vadodara": "Gujarat",
        "Jaipur": "Rajasthan", "Jodhpur": "Rajasthan", "Udaipur": "Rajasthan",
        "Lucknow": "Uttar Pradesh", "Kanpur": "Uttar Pradesh",
        "Indore": "Madhya Pradesh", "Bhopal": "Madhya Pradesh",
        "Chandigarh": "Punjab", "Ludhiana": "Punjab", "Amritsar": "Punjab",
        "Kochi": "Kerala", "Thiruvananthapuram": "Kerala", "Kozhikode": "Kerala",
        "Bhubaneswar": "Odisha", "Ranchi": "Jharkhand",
    }
    state = city_state_map.get(city, random.choice(INDIAN_STATES))

    return {
        "customer_id":    customer_id,
        "cust_name":      cust_name,
        "cust_email":     cust_email,
        "cust_phone":     fields.get("cust_phone", ""),
        "date_of_birth":  fields.get("date_of_birth", ""),
        "pan_number":     fields.get("pan_number", ""),
        "aadhaar_number": fields.get("aadhaar_number", ""),
        "address":        fields.get("address", ""),
        "city":           city,
        "state":          state,
        "pincode":        str(fields.get("pincode", "")),
        "kyc_status":     random.choices(
            ["verified", "pending", "rejected"],
            weights=[0.70, 0.20, 0.10]
        )[0],
    }


def generate_kyc_dataset(count: int = 20) -> list[dict]:
    """Generate `count` synthetic KYC records via vLLM."""
    records = []
    for i in range(count):
        cust_name = gen_customer_name()
        city      = random.choice(TIERS_CITIES)
        cust_email = gen_email(cust_name)
        customer_id = gen_customer_id()
        try:
            record = generate_kyc_record(customer_id, cust_name, cust_email, city)
            records.append(record)
            print(f"[{i+1}/{count}] {customer_id} | {cust_name} | {city} | {record['kyc_status']}")
        except Exception as e:
            print(f"[{i+1}/{count}] FAILED ({cust_name}): {e}")
    return records


def save_kyc_to_db(records: list[dict]) -> None:
    """Insert KYC records into customer_kyc table."""
    if not records:
        print("[kyc_generator] No records to save.")
        return
    conn = get_conn()
    conn.executemany("""
        INSERT OR IGNORE INTO customer_kyc (
            customer_id, cust_name, cust_email, cust_phone,
            date_of_birth, pan_number, aadhaar_number,
            address, city, state, pincode, kyc_status
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, [
        (
            r["customer_id"], r["cust_name"], r.get("cust_email"), r["cust_phone"],
            r["date_of_birth"], r["pan_number"], r["aadhaar_number"],
            r["address"], r["city"], r["state"], r["pincode"], r["kyc_status"],
        )
        for r in records
    ])
    conn.close()
    print(f"[kyc_generator] Saved {len(records)} KYC records to customer_kyc.")


def run_kyc_generator(count: int = 20) -> list[dict]:
    """
    Generate synthetic KYC records via vLLM and save to customer_kyc table.
    Returns list of generated records.
    """
    print(f"\n[kyc_generator] Generating {count} KYC records via {VLLM_MODEL}...\n")
    records = generate_kyc_dataset(count)

    if not records:
        print("[kyc_generator] No records generated — check VLLM_MODEL and endpoint.")
        return []

    save_kyc_to_db(records)

    status_dist = {}
    for r in records:
        status_dist[r["kyc_status"]] = status_dist.get(r["kyc_status"], 0) + 1
    print(f"\n[kyc_generator] Done. {len(records)} records. Status: {status_dist}")
    return records
