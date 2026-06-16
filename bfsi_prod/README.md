# BFSI Complaint Pipeline — Production Structure

## Folder layout

```
bfsi_prod/
├── run_pipeline.py              ← entry point, run this
├── requirements.txt
├── synthetic_complaints.json    ← sample data for SEED_DATA=True testing
├── config/
│   └── config.py                ← all settings: vLLM endpoint, categories, team routing, default users
├── data/
│   └── db.py                    ← all DuckDB operations (complaints.duckdb + routing.duckdb)
├── model/
│   ├── classifier.py            ← LLM classification (category/priority/sentiment)
│   ├── router.py                ← LLM routing agent (team assignment/escalation)
│   └── data_generator.py        ← synthetic complaint generator for testing
├── security/
│   ├── pii_redactor.py          ← Aadhaar/PAN/card/CVV redaction (regex + LLM second pass)
│   └── content_security.py      ← SQL/code/prompt injection detection (regex + LLM second pass)
└── ui/
    ├── unified_app.py           ← single Gradio app, two tabs (customer + employee)
    ├── login_form.py            ← employee login page layout
    ├── list_form.py             ← employee complaint list page layout
    ├── details_form.py          ← employee complaint detail/edit page layout
    └── dashboard_form.py        ← supervisor dashboard page layout
```

## How imports work across folders

Every file still uses simple flat imports exactly as before
(`from db import X`, `from config import Y`, etc.) — nothing was rewritten.
`run_pipeline.py` adds each subfolder to `sys.path` at startup, so Python
finds every module regardless of which folder it physically lives in.

If you ever add a new script that needs these modules, copy this block to
the top of it before any other imports:

```python
import os, sys
_BASE_DIR = os.path.dirname(os.path.abspath(__file__))
for _sub in ("config", "data", "model", "security", "ui"):
    sys.path.insert(0, os.path.join(_BASE_DIR, _sub))
```

## Running

```bash
cd bfsi_prod
pip install -r requirements.txt
python run_pipeline.py
```

This will:
1. Initialise `complaints.duckdb` and `routing.duckdb` (created in this folder)
2. Skip seeding by default (`SEED_DATA = False` in `run_pipeline.py` — set
   `True` to seed from `synthetic_complaints.json` for testing)
3. Start a background poll loop that classifies + routes new complaints every 60s
4. Launch the unified Gradio app (single public URL, two tabs: Lodge Complaint / Employee Portal)

Before running, make sure vLLM is serving on the endpoint configured in
`config/config.py` (`VLLM_HOST`, `VLLM_MODEL`).

## Removed files (superseded, not part of production build)

These were intermediate/duplicate versions created during development and
are NOT included here since `unified_app.py` replaced their functionality:
- `cust_ui.py`, `cust_ui_v2.py` — standalone customer UI, replaced by the
  Lodge Complaint tab in `unified_app.py`
- `app_form.py`, `app_form_v2.py`, `app_form_v2_00.py`, `app_form_alternate.py`,
  `db_manager.py`, `complaints_app.py` — standalone employee portal versions,
  replaced by the Employee Portal tab in `unified_app.py`
- `main.py` — CLI entry point referencing a module (`app_form_v2`) that no
  longer exists in the final design; `run_pipeline.py` is the sole entry point
- old `run_pipeline.py` (two-port version) — superseded by the single
  unified-port version, now just called `run_pipeline.py`
- two `.ipynb` notebooks — exploratory/dev notebooks, not part of the
  deployed pipeline

## Default login users (seeded on first `init_db()` run)

| UserID | Password | Type | Team |
|---|---|---|---|
| FraudMember01 / 02 | FM01 / FM02 | TeamMember | Fraud |
| FraudSupervisor01 | FMS01 | Supervisor | Fraud |
| KYCMember01 | KYC01 | TeamMember | KYC |
| KYCSupervisor01 | KYCS01 | Supervisor | KYC |
| InsuranceMember01 | IM01 | TeamMember | Insurance |
| InsuranceSupervisor01 | IMS01 | Supervisor | Insurance |
| GeneralMember01 | GM01 | TeamMember | General |
| GeneralSupervisor01 | GMS01 | Supervisor | General |
| CardMember01 | CDM01 | TeamMember | Card |
| CardSupervisor01 | CDMS01 | Supervisor | Card |
| LoanMember01 | LM01 | TeamMember | Loan |
| LoanSupervisor01 | LMS01 | Supervisor | Loan |
| DigitalMember01 | DM01 | TeamMember | Digital |
| DigitalSupervisor01 | DMS01 | Supervisor | Digital |
| BranchMember01 | BM01 | TeamMember | Branch |
| BranchSupervisor01 | BMS01 | Supervisor | Branch |
| Admin | Admin | Admin | sees all teams |

**Production note:** `config/config.py` has these credentials in plaintext
for development convenience. Before real deployment, hash passwords and
move credentials to environment variables or a secrets manager — this is
flagged inline in `config.py` as a TODO.
