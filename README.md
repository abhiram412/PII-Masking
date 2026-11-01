# T042 · B1: Quantum Data Masking & Post-Quantum Cryptography (PQC)

> **Query-time PII protection powered by real Quantum Entropy (IBM Quantum / Qiskit) and NIST Post-Quantum Cryptography (FIPS 203 ML-KEM + FIPS 204 ML-DSA)**

---

## What it does

Banks must protect customer PII (SSN, PAN, Aadhaar, card numbers, balances) under **GDPR, PCI-DSS and RBI** rules — without rewriting every application or exposing raw storage.

**Quantum Data Masking & PQC** is a read-only, database-agnostic security layer that intercepts SQL at query time and applies role-based masking. Its two core differentiators are:

### 1. Quantum Entropy (QRNG) — the foundation of every token
- Generates true physical randomness from quantum superposition:  
  \( |\psi\rangle = H^{\otimes n}|0\rangle \) measured on IBM Quantum hardware (or high-fidelity local AerSimulator when no token is present).
- The resulting entropy seeds **HMAC-SHA3-256** keyed tokenization so that the same customer always receives the same token *across tables and sessions*, while remaining unlinkable without the quantum-derived key.
- Live IBM Quantum jobs appear in the user’s IBM Quantum console; the dashboard shows backend name, job ID, qubit count and circuit depth.

### 2. Post-Quantum Cryptography (PQC) — future-proof audit trail
- **NIST FIPS 203 (ML-KEM-768 / Kyber)** for envelope encryption of sensitive material.
- **NIST FIPS 204 (ML-DSA-65 / CRYSTALS-Dilithium)** for digital signatures on every audit record.
- Immutable SHA3-256 hash-chain of every masking decision, signed with Dilithium so that even a future quantum adversary cannot forge or alter the ledger.

### Supporting capabilities
- **AST-level SQL lineage & side-channel defence** (sqlglot) — blocks inference attacks via `WHERE`, `ORDER BY`, `GROUP BY`, `HAVING` and CTEs.
- **Role-based format-preserving masking**  
  - Admin → raw (break-glass)  
  - Support → partial mask for verification  
  - Analyst → quantum-keyed tokens + numeric buckets

---

## How to run

All application code, scripts, configuration and tests live inside `FULL_CODE/` (Hackathon coding-guidelines layout).

### 1. Prerequisites
- **Python 3.10+** (tested on Python 3.12 and Python 3.14 on Linux/macOS/Windows)
- Pip and virtualenv

### 2. Environment Setup & Dependencies
```bash
# Navigate to FULL_CODE directory
cd FULL_CODE

# Install required dependencies
pip install -r requirements.txt

# Configure environment variables (create .env from .env.example)
cp .env.example .env
```

> **Quantum Entropy – how to run on real IBM hardware**  
> 1. Create a free account at https://quantum.ibm.com and copy your **API token**.  
> 2. Put the token in `.env`:  
>    ```  
>    IBM_QUANTUM_TOKEN=your_actual_token_here  
>    ```  
> 3. Every entropy generation will then submit a real Hadamard circuit to an IBM QPU.  
>    The job appears in your IBM Quantum console and the dashboard shows the live backend name + job ID.  
> 4. If the token is missing or the cloud call fails, the engine falls back to the local AerSimulator (status remains truthful).  
> 5. PQC keys (ML-KEM-768 + ML-DSA-65) are auto-generated on first run into the git-ignored `keys/` folder.

### 3. Database Seeding
The engine automatically bootstraps from the Saffron Bank dataset CSVs inside `data/csv/`:
```bash
# Full database rebuild from Saffron Bank CSV dataset (129k+ rows):
python seed.py --reset

# Fast development bootstrap with row limit:
python seed.py --reset --limit 500
```

### 4. Running the Interactive Streamlit Dashboard
Launch the dual-theme, WCAG AA/AAA-compliant banking dashboard:
```bash
streamlit run streamlit_app.py
```
Open your browser at `http://localhost:8501`.

### 5. Running the Unified Launcher or CLI
```bash
# Interactive unified launcher:
python main.py

# Automated PII & financial schema scan:
python cli.py scan

# Multi-role comparative query:
python cli.py compare "SELECT cust_nm, mob_no, emailid, addr_line1 FROM customers LIMIT 3"

# Single-role execution:
python cli.py query --role support "SELECT CARD_NO, NAME_ON_CARD, CREDIT_LIMIT FROM cards LIMIT 5"
```

---

## How to run the tests

Run the automated test suite with one single command:
```bash
# From inside FULL_CODE/
python -m unittest discover tests
```
Or using pytest:
```bash
pytest -q
```

- **Test Suite Result**: 25/25 passing unit and integration tests.
- **Coverage**: AST SQL lineage tracing, predicate security bypass blocking (`WHERE`/`ORDER BY`), disguised column format detection (PAN, SSN, IFSC, Aadhaar), physical storage SHA-256 dump immutability, role-based differential policies, and real Saffron Bank dataset integration.

---

## Architecture

**Core path (always on):**
1. Incoming SQL → AST lineage (sqlglot)
2. Quantum Entropy seed (IBM Quantum hardware *or* local AerSimulator)
3. Role-based maskers seeded by the quantum entropy
4. Every decision written to a Dilithium-signed, SHA3-256 hash-chained audit log (PQC)



```
                                  [ Incoming SQL Query / API Request ]
                                                   │
                                                   ▼
                                    ┌───────────────────────────────┐
                                    │       MaskingEngine           │
                                    │  - AST Parser (sqlglot)       │
                                    │  - Column Lineage & CTEs      │
                                    │  - Predicate Policy Defense   │
                                    └──────────────┬────────────────┘
                                                   │
                                                   ▼
                                    ┌───────────────────────────────┐
                                    │    Read-Only Database Driver  │
                                    │  - SQLite (Authorizer mode=ro)│
                                    │  - PostgreSQL (Readonly Sess) │
                                    │  - MySQL (Transaction RO)     │
                                    └──────────────┬────────────────┘
                                                   │ Raw Storage Records
                                                   ▼
                                    ┌───────────────────────────────┐
                                    │   Dynamic Masking Pipeline    │
                                    │  - Admin: Cleartext bypass    │
                                    │  - Support: Partial masking   │
                                    │  - Analyst: QRNG HMAC Hash    │
                                    └──────────────┬────────────────┘
                                                   │
                ┌──────────────────────────────────┴──────────────────────────────────┐
                ▼                                                                     ▼
┌───────────────────────────────┐                                     ┌───────────────────────────────┐
│     Quantum Entropy (QRNG)    │                                     │     Post-Quantum Cryptography │
│  - Qiskit Superposition       │                                     │  - NIST FIPS 204 ML-DSA-65    │
│  - IBM Quantum Cloud Heron QPU│                                     │  - NIST FIPS 203 ML-KEM-768   │
│  - Local AerSimulator         │                                     │  - SHA3-256 Hash Chain Ledger │
└───────────────────────────────┘                                     └───────────────────────────────┘
                ▲                                                                     ▲
                └──────────────────────────────────┬──────────────────────────────────┘
                                    └───────────────────────────────┘
```

### Main Components inside `FULL_CODE/`:
- `streamlit_app.py`: WCAG AA/AAA-compliant dashboard with dual theme system (Dark Navy `#0B1020` / Light Slate `#F6F8FC`), dynamic font scaling (`A−`, `100%`, `A+`), synced confidence sliders, and side-by-side Role-Masked Preview comparisons.
- `masking/engine.py`: Core `MaskingEngine` managing SQL AST parsing, alias resolution, predicate blocking, and in-memory dynamic transformation.
- `masking/scanner.py`: Content-driven PII scanner evaluating column names and cell formats (Luhn checksum for cards, Verhoeff for Aadhaar, regex for Indian PAN/IFSC, US SSN, phones, emails).
- `masking/maskers.py`: Implementation of format-preserving masking (`partial_mask`), quantum HMAC hashing (`hash_value`), and free-text scrubbing (`scrub_text_pii`).
- `masking/quantum_entropy.py`: Qiskit quantum circuit generator connected to IBM Quantum Cloud (`ibm_kingston`, `ibm_fez`, `ibm_marrakesh`) and local `AerSimulator`.
- `masking/pqc.py` & `masking/audit.py`: Post-quantum cryptographic implementation providing ML-DSA-65 signatures and ML-KEM-768 envelope encryption.
- `main.py`: One-command interactive CLI & launcher.
- `cli.py`: Production-grade command-line interface for scans, masking, queries, and audit verification.
- `seed.py`: Saffron Bank synthetic dataset loader (9 tables, ~129k rows).

---

## Deep Dive: Key Innovations

### 1. Quantum Entropy (QRNG) & Quantum for Structured Data
Standard pseudorandom number generators (PRNGs) are deterministic and vulnerable to seed prediction. This project harnesses quantum mechanics for data privacy:
- **Hadamard Circuit Superposition**: Creates true physical quantum randomness by placing qubits into superposition $|\psi\rangle = \frac{1}{\sqrt{2}}(|0\rangle + |1\rangle)$, measuring quantum state collapse across multiple shots.
- **Hardware Integration**: Live telemetry and job submission to IBM Quantum Platform QPUs (156-qubit Heron architecture) with automatic fallback to local Qiskit `AerSimulator`.
- **Quantum-Keyed Deterministic Masking**: Derived quantum seeds feed `hmac.new(quantum_secret, value, hashlib.sha3_256)`, ensuring that the same customer identifier (e.g., `customer_id` or `ssn`) consistently hashes to identical joinable tokens (`h_8A3F...`) across queries, enabling relational analytics without exposing underlying PII.

### 2. Post-Quantum Cryptography (PQC) & Proof of Concept (PoC)
To safeguard audit records against "Harvest Now, Decrypt Later" quantum adversaries:
- **NIST FIPS 204 (ML-DSA-65 / CRYSTALS-Dilithium)**: Every query execution produces an immutable audit record signed using lattice-based post-quantum signatures with dedicated verification keys stored in `keys/`.
- **NIST FIPS 203 (ML-KEM-768 / Kyber)**: Sensitive query descriptors are wrapped using post-quantum lattice-based key encapsulation mechanisms.
- **Physical Immutability Proof**: The database is accessed exclusively with SQLite Authorizers and `mode=ro`. A live SHA-256 database dump comparison proves that physical storage is 100% untouched while users see masked data in real time.


## AI usage

- **AI Coding Assistants**: Google Antigravity IDE and DeepMind agentic tools were utilized during development for test harness synthesis, CSS design system verification, and AST lineage coverage testing.
- **Zero Hallucination Guarantee**: All structured SQL masking is strictly deterministic and mathematical, seeded by quantum entropy — no generative model is used on database rows.

---

## Pre-built and third-party code

All open-source dependencies are tracked in `FULL_CODE/requirements.txt`:
- **`sqlglot`** (MIT License): Abstract syntax tree parsing and SQL column lineage analysis.
- **`qiskit` & `qiskit-aer`** (Apache 2.0): Quantum circuit simulation, state measurement, and IBM Quantum Cloud runtime.
- **`dilithium-py` & `kyber-py`** (MIT License): Reference implementations of NIST FIPS 204 (ML-DSA) and FIPS 203 (ML-KEM).
- **`cryptography`** (Apache 2.0 / BSD): AES-GCM envelope encryption and SHA3-256 cryptographic hashing.
- **`streamlit`** (Apache 2.0) & **`pandas`** (BSD-3): Visual analytics dashboard and tabular data manipulation.

---

## Limitations

1. **Quantum Hardware Queueing**: Submitting jobs to IBM Quantum Cloud open-tier hardware involves public queue times (seconds to minutes depending on platform load). The system provides a zero-latency local `AerSimulator` fallback with an live backend queue inspector.
2. **Deep Content Sampling on Massive Tables**: Dynamic heuristic scanning on unindexed tables with tens of millions of rows can introduce initial discovery latency. This is mitigated through schema fingerprint caching (`data/pii_catalog.json`).
3. **Complex Non-Standard SQL Dialects**: Highly dialect-specific proprietary stored procedures fall back to content-driven verification when AST lineage cannot deterministically trace dynamic expressions.