"""
config.py — Central configuration for BFSI complaint pipeline.
All modules import from here. Edit VLLM_HOST and VLLM_MODEL before running.
"""

# ── vLLM ──────────────────────────────────────────────────────────────────────
VLLM_HOST     = "http://localhost:8000"     # update to AMD VM IP
VLLM_BASE_URL = f"{VLLM_HOST}/v1"
VLLM_MODEL    = "Qwen2.5-7B-Instruct"      # match --served-model-name exactly
VLLM_API_KEY  = "abc-123"

# ── Paths ─────────────────────────────────────────────────────────────────────
DB_PATH      = "complaints.duckdb"
ROUTING_DB   = "routing.duckdb"
JSON_PATH    = "synthetic_complaints.json"

# ── Classification ────────────────────────────────────────────────────────────
CATEGORIES = [
    "fraud", "card_dispute", "kyc_onboarding", "loan_emi",
    "net_banking_upi", "branch_atm", "insurance", "general",
]

SLA_MAP = {"P1": 1, "P2": 2, "P3": 5, "P4": 10}

TEAM_MAP = {
    "fraud":           "Fraud Response Team",
    "card_dispute":    "Card Operations",
    "kyc_onboarding":  "KYC Team",
    "loan_emi":        "Loan Servicing",
    "net_banking_upi": "Digital Banking",
    "branch_atm":      "Branch Support",
    "insurance":       "Insurance Claims",
    "general":         "General Support",
}

# ── Intake form options ───────────────────────────────────────────────────────
CHANNELS      = ["web", "branch", "mobile_app"]
ACCOUNT_TYPES = ["Consumer Banking", "Corporate Banking"]
COMPLAINT_CHANNELS = [
    "Fraud", "Cards", "KYC", "Loans",
    "Digital Banking", "Branch Support", "Insurance", "General Support",
]
COMPLAINT_CATEGORIES = [
    "Savings", "Credit Card", "Personal Loan",
    "Insurance", "Corporate Banking", "Corporate Credit Card",
]

TIERS_CITIES = [
    "Agra", "Ahmedabad", "Ajmer", "Aligarh", "Allahabad", "Amravati", "Amritsar",
    "Asansol", "Bangalore", "Bhopal", "Bhubaneswar", "Chandigarh", "Chennai",
    "Coimbatore", "Dehradun", "Delhi", "Dhanbad", "Durg-Bhilai", "Erode", "Faridabad",
    "Ghaziabad", "Gwalior", "Hubli-Dharwad", "Hyderabad", "Indore", "Jabalpur",
    "Jaipur", "Jalandhar", "Jodhpur", "Kannur", "Kanpur", "Kochi", "Kolhapur",
    "Kollam", "Kolkata", "Kozhikode", "Lucknow", "Ludhiana", "Madurai", "Meerut",
    "Moradabad", "Mumbai", "Nagpur", "Nanded", "Nashik", "Nellore", "Noida",
    "Puducherry", "Pune", "Raipur", "Rajkot", "Ranchi", "Salem", "Shillong",
    "Shimla", "Siliguri", "Solapur", "Srinagar", "Surat", "Thiruvananthapuram",
    "Thrissur", "Tiruchirappalli", "Tirunelveli", "Tiruppur", "Udaipur", "Ujjain",
    "Vadodara", "Varanasi", "Vijayawada", "Visakhapatnam", "Warangal",
]

# ── Data generation ───────────────────────────────────────────────────────────
CATEGORY_WEIGHTS = {
    "fraud": 0.10, "card_dispute": 0.20, "net_banking_upi": 0.25,
    "kyc_onboarding": 0.10, "loan_emi": 0.15, "branch_atm": 0.08,
    "insurance": 0.07, "general": 0.05,
}

CATEGORY_ACCOUNT_AFFINITY = {
    "fraud":           ["credit_card", "savings"],
    "card_dispute":    ["credit_card", "savings"],
    "kyc_onboarding":  ["savings", "current"],
    "loan_emi":        ["loan"],
    "net_banking_upi": ["savings", "current"],
    "branch_atm":      ["savings", "current"],
    "insurance":       ["insurance"],
    "general":         ["savings", "current", "credit_card"],
}

INDIAN_FIRST_NAMES = [
    "Rahul", "Priya", "Amit", "Sneha", "Vikram", "Kavya", "Rohan", "Pooja",
    "Arjun", "Deepika", "Suresh", "Anita", "Nikhil", "Meera", "Rajesh",
    "Sunita", "Kiran", "Neha", "Sanjay", "Divya", "Arun", "Lakshmi",
    "Manish", "Ritu", "Gaurav", "Swati", "Vinod", "Pallavi", "Ashok", "Rekha",
]

INDIAN_LAST_NAMES = [
    "Sharma", "Patel", "Singh", "Kumar", "Mehta", "Nair", "Iyer", "Joshi",
    "Reddy", "Verma", "Gupta", "Shah", "Pillai", "Rao", "Mishra", "Desai",
    "Malhotra", "Chopra", "Bose", "Das", "Pandey", "Sinha", "Tiwari", "Dubey",
]

EMAIL_DOMAINS   = ["gmail.com", "yahoo.com", "hotmail.com", "outlook.com", "rediffmail.com"]
MUMBAI_BRANCHES = [
    "Andheri West", "Bandra East", "Borivali", "Dadar", "Thane",
    "Kurla", "Powai", "Malad", "Goregaon", "Vashi", "Kandivali", "Mulund",
]

# ── Routing ───────────────────────────────────────────────────────────────────
TEAM_PROFILES = {
    "Fraud Response Team": {
        "handles":    ["unauthorized transactions", "card fraud", "account takeover", "phishing"],
        "escalation": "Head of Fraud",
        "sla_hours":  24,
        "email":      "fraud-alerts@bank.in",
    },
    "Card Operations": {
        "handles":    ["card blocked", "card declined", "duplicate charge", "card replacement"],
        "escalation": "Card Ops Manager",
        "sla_hours":  48,
        "email":      "card-ops@bank.in",
    },
    "KYC Team": {
        "handles":    ["KYC pending", "document verification", "account opening delay", "video KYC"],
        "escalation": "KYC Head",
        "sla_hours":  48,
        "email":      "kyc@bank.in",
    },
    "Loan Servicing": {
        "handles":    ["EMI discrepancy", "loan prepayment", "interest rate", "home loan"],
        "escalation": "Loans Manager",
        "sla_hours":  120,
        "email":      "loans@bank.in",
    },
    "Digital Banking": {
        "handles":    ["UPI failure", "net banking", "mobile app", "NEFT/IMPS"],
        "escalation": "Digital Head",
        "sla_hours":  120,
        "email":      "digital@bank.in",
    },
    "Branch Support": {
        "handles":    ["ATM cash discrepancy", "branch service", "fixed deposit", "passbook"],
        "escalation": "Branch Manager",
        "sla_hours":  120,
        "email":      "branch@bank.in",
    },
    "Insurance Claims": {
        "handles":    ["life insurance claim", "health insurance", "cashless rejection", "policy lapse"],
        "escalation": "Claims Head",
        "sla_hours":  48,
        "email":      "insurance@bank.in",
    },
    "General Support": {
        "handles":    ["statement", "mobile number update", "feedback", "general inquiry"],
        "escalation": "Support Manager",
        "sla_hours":  240,
        "email":      "support@bank.in",
    },
}

ROUTER_SYSTEM = """You are a BFSI complaint routing agent. Reason step-by-step and decide
the best team to handle this complaint.

Teams and what they handle:
{team_profiles}

Return ONLY a valid JSON object with these fields:
- routed_team: exact team name from the list above
- escalate: true or false
- escalate_to: escalation contact name if escalate=true, else null
- action: specific instruction for the team (1-2 sentences)
- routing_reason: why this team was chosen (1-2 sentences)
- confidence: high | medium | low

No markdown. No text outside JSON."""

# ── Default users (seeded on DB init) ────────────────────────────────────────
DEFAULT_USERS = [
    ("Fraud_Member_01",    "FM01",   "TeamMember"),
    ("Fraud_Member_02",    "FM02",   "TeamMember"),
    ("Fraud_Supervisor_01","FMS01",  "Supervisor"),
    ("KYC_Member_01",      "KYC01",  "TeamMember"),
    ("KYC_Supervisor_01",  "KYCS01", "Supervisor"),
    ("Admin",              "Admin",  "Admin"),
]

# ── Classifier system prompt ──────────────────────────────────────────────────
CLASSIFY_SYSTEM_PROMPT = """You are a BFSI complaint classification and routing agent for an Indian bank.

Given a customer complaint, return ONLY a valid JSON object — no markdown, no explanation outside JSON.

JSON fields:
- category: one of [fraud, card_dispute, kyc_onboarding, loan_emi, net_banking_upi, branch_atm, insurance, general]
- priority: P1 (fraud/security, 1 day) | P2 (card block/KYC, 2 days) | P3 (UPI/EMI/ATM, 5 days) | P4 (general, 10 days)
- team: one of [Fraud Response Team, Card Operations, KYC Team, Loan Servicing, Digital Banking, Branch Support, Insurance Claims, General Support]
- sentiment: one of [angry, distressed, frustrated, neutral, satisfied]
- sla_days: 1 | 2 | 5 | 10
- summary: one sentence summarising the issue
- reasoning: 1-2 sentences explaining priority and team

Return ONLY valid JSON. No markdown fences. No preamble."""
