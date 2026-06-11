# Complaint Management System - User Testing Guide

## Setup Instructions

### 1. Install Dependencies
```bash
pip install -r requirements.txt
```

### 2. Run the Application
```bash
streamlit run complaints_app.py
```

The app will open at `http://localhost:8501`

---

## Test Scenarios (User Perspective)

### **Test 1: Dashboard View** 🏠
**Objective:** Verify initial database state and statistics display

**Steps:**
1. Launch the app (you'll automatically land on Dashboard)
2. Observe the KPI metrics (Total Complaints, SLA Breached, Open, Resolved)
3. Check the "By Priority" and "By Category" charts
4. Verify the "Status Breakdown" table

**Expected Results:**
- Dashboard loads without errors
- All metrics display (may show 0 if no data loaded yet)
- Charts are empty until data is loaded

---

### **Test 2: Data Ingestion** 📥
**Objective:** Load synthetic complaint data from JSON file

**Steps:**
1. Click "📥 Data Ingestion" in sidebar
2. The JSON file path should default to `synthetic_complaints.json`
3. Click "📂 Load JSON → synthetic_raw"
4. Observe the success message and record count

**Expected Results:**
- ✅ Loads **8 record(s)** from `synthetic_complaints.json`
- The "Synthetic Raw Preview" table shows 8 rows with all columns:
  - customer_id, cust_name, cust_email, complaint, category, channel, branch, account_type

**Sample Data Loaded:**
- CUST001-CUST008 with various complaint types (billing, fraud, technical, service, etc.)

---

### **Test 3: Submit New Complaint** ➕
**Objective:** Test the form validation and complaint creation

**Steps:**
1. Click "➕ Submit Complaint" in sidebar
2. **Leave all required fields blank** and click "🚀 Submit Complaint"
3. Verify error messages appear
4. Fill in the form with valid data:
   - **Customer Name:** "Alice Cooper"
   - **Customer ID:** "CUST999"
   - **Email:** "alice@email.com"
   - **Branch:** "Test Branch"
   - **Complaint:** "This is a test complaint for system validation."
   - **Channel:** "web"
   - **Account Type:** "savings"
   - **Category:** "service"
   - **Priority:** "high"
   - **Team:** "customer_service"
   - **Sentiment:** "negative"
   - **SLA Days:** 5
   - **Summary:** (optional) "Customer frustrated with service"
   - **Reasoning:** (optional) "High priority issue affecting user satisfaction"
5. Click "🚀 Submit Complaint"

**Expected Results:**
- ✅ Error messages for missing required fields
- ✅ Success message with complaint ID (e.g., "Complaint **CMP-ABC12345** created successfully!")
- New complaint appears in queue after submission

---

### **Test 4: Complaints Queue - View & Filter** 📑
**Objective:** Test filtering, sorting, and complaint details view

**Steps:**
1. Click "📑 Complaints Queue" in sidebar
2. Observe the complaint list (should show all complaints created so far)
3. **Test Filters:**
   - Select Priority: "high"
   - Select Status: "open"
   - Select Category: "billing"
   - Adjust the "Rows" slider to 25
4. Click a complaint ID in the detail view section
5. Examine the full complaint details displayed

**Expected Results:**
- ✅ Filters work correctly and narrow down results
- ✅ Table shows selected columns: complaint_id, cust_name, category, priority, status, team, created_at, sla_deadline, sla_breached
- ✅ "SLA Breached" checkbox shows TRUE only for open complaints past deadline
- ✅ Detail view displays all fields (customer info, complaint text, summary, reasoning)

---

### **Test 5: Status Update** 💾
**Objective:** Test updating complaint status

**Steps:**
1. Go to "📑 Complaints Queue"
2. Select any complaint from the dropdown
3. In the "Update Status" selectbox, choose: "in_progress"
4. Click "💾 Save Status"
5. Verify the status changed
6. Reload and check the updated status persists

**Expected Results:**
- ✅ Status updates successfully
- ✅ Success message displayed
- ✅ Page refreshes and status persists in database
- ✅ Complaint can be updated through different statuses: open → in_progress → resolved → closed

---

### **Test 6: Classification Log** 📜
**Objective:** Verify classification log view

**Steps:**
1. Click "📜 Classification Log" in sidebar
2. Adjust "Rows to display" slider (10-500)
3. Observe the table

**Expected Results:**
- ✅ Page displays "No classification logs recorded yet" (logs are auto-inserted when AI processes complaints)
- ✅ Slider allows adjusting display limit
- ✅ Once logs exist, displays: complaint_id, raw_response, parse_success, latency_ms, model_used, logged_at

---

### **Test 7: Dashboard with Populated Data** 🏠
**Objective:** Verify dashboard updates with loaded data

**Steps:**
1. Go back to "🏠 Dashboard"
2. Observe updated KPIs and charts

**Expected Results:**
- ✅ Total Complaints: shows current count
- ✅ SLA Breached: counts open complaints past SLA deadline
- ✅ By Priority chart: shows distribution
- ✅ By Category chart: shows distribution
- ✅ Status Breakdown: table with current counts

---

## Known Limitations

⚠️ **Note on SLA Deadline Calculation:**
- The SLA deadline is calculated as: `current_timestamp + INTERVAL '?' DAY`
- Syntax may need adjustment depending on DuckDB version
- All new complaints get SLA deadline 3 days from creation by default

⚠️ **Database:**
- Uses DuckDB with local file storage (`complaints.duckdb`)
- Data persists between sessions
- To reset, delete `complaints.duckdb` file

---

## Troubleshooting

### App won't start
```bash
# Check dependencies
pip install -r requirements.txt --upgrade

# Clear Streamlit cache
streamlit cache clear

# Run with verbose output
streamlit run complaints_app.py --logger.level=debug
```

### Database errors
- Delete `complaints.duckdb` to reset
- Ensure write permissions in the directory

### JSON loading fails
- Verify `synthetic_complaints.json` is in the same directory as `complaints_app.py`
- Check JSON syntax with: `python -m json.tool synthetic_complaints.json`

---

## Test Summary Checklist

- [ ] Dashboard loads and displays stats
- [ ] Data ingestion loads 8 records successfully
- [ ] Complaint form validates required fields
- [ ] New complaint can be created
- [ ] Complaints Queue displays all records
- [ ] Filters work correctly
- [ ] Status can be updated and persists
- [ ] Classification Log page accessible
- [ ] Dashboard updates after data loads
- [ ] No crashes or errors during navigation

**Total Expected Test Time:** ~10-15 minutes
