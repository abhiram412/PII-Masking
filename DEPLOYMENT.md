# Deployment Guide
## Smart Data Masking System for PII Protection (BFSI PS-1)

This system supports three primary deployment configurations:
1. **Local Deployment (Bare Metal / Python Venv)**
2. **Containerized Deployment (Docker & Docker Compose)**
3. **Cloud Deployment (Streamlit Community Cloud / Cloud Run)**

---

## 1. Option A: Local Deployment (Active Now)

### Step 1: Install Dependencies
```bash
pip install -r requirements.txt
```

### Step 2: Configure Environment
Copy `.env.example` to `.env`:
```bash
cp .env.example .env
```
*(Optional)* Populate `IBM_QUANTUM_TOKEN` with your IBM Quantum Cloud token. If left blank, the system automatically runs with local `AerSimulator` quantum physics simulation.

### Step 3: Seed Database
```bash
python seed.py --reset
```
This seeds `data/bank.db` from the 129,000+ row Saffron Bank dataset in `data/csv/`.

### Step 4: Run the Application
You can run the application using any of the following methods:
- **One-Click Batch File (Windows):** Double-click `run_local.bat`
- **Unified Launcher:** `python main.py dashboard`
- **Direct Streamlit Command:**
  ```bash
  streamlit run streamlit_app.py --server.port=8501
  ```
- **Access in Browser:** `http://localhost:8501`
- **Healthcheck URL:** `http://localhost:8501/_stcore/health` (Returns HTTP 200)

---

## 2. Option B: Docker Container Deployment

The project includes an optimized, production-hardened `Dockerfile` with multi-step build-time database seeding and automated PII scanning:

### Build Container Image
```bash
docker build -t pii-masking-system:latest .
```

### Run Container
```bash
docker run -d \
  --name pii-masker \
  -p 8501:8501 \
  --env-file .env \
  --restart unless-stopped \
  pii-masking-system:latest
```

### Check Container Health
```bash
docker ps
curl http://localhost:8501/_stcore/health
```

---

## 3. Option C: Streamlit Community Cloud Deployment

The repository is pre-configured for one-click deployment on Streamlit Community Cloud:
1. Connect your GitHub repository to [share.streamlit.io](https://share.streamlit.io).
2. Configure application settings:
   - **Main file path:** `streamlit_app.py`
   - **Python version:** `3.12`
3. In **App Settings → Secrets**, add:
   ```toml
   IBM_QUANTUM_TOKEN = "your_token_here"
   BANK_DB = "data/bank.db"
   ```
4. Click **Deploy**. The app automatically bootstraps the database on cold start and serves the interface.

---

## 4. Verification & Smoke Test Checklist

| Verification Check | Command | Expected Outcome |
| :--- | :--- | :--- |
| **Healthcheck** | `curl -s http://localhost:8501/_stcore/health` | HTTP 200 / empty response |
| **CLI Scan** | `python cli.py scan` | Outputs tagged sensitive columns with confidence scores |
| **Role Compare** | `python cli.py compare "SELECT cust_nm, mob_no FROM customers LIMIT 3"` | Shows cleartext for Admin, masked for Support, redacted for Analyst |
| **Unit Test Suite** | `python -m unittest discover tests` | `Ran 25 tests ... OK` |
