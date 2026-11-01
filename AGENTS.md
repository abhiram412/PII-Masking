# AGENTS.md

## What this is
Python "Smart Data Masking" demo: query-time PII masking for SQL databases with `sqlglot` lineage, role policies, Qiskit QRNG, and a post-quantum signed audit chain.

- Entrypoints: `cli.py`, `streamlit_app.py`, `seed.py`.
- Core package: `masking/` (`scanner.py` -> `engine.py` -> `maskers.py`; `audit.py` / `pqc.py`; `backends.py`). `qrng/` only re-exports `masking/quantum_entropy.py`.
- Default backend is SQLite at `data/bank.db`; Postgres (`psycopg2-binary`) and MySQL (`pymysql`) are optional extras.

## Commands (run from repo root)
- Install: `pip install -r requirements.txt` (includes pytest)
- Seed from the Saffron CSVs: `python seed.py --reset` (rebuilds `data/bank.db` from `data/csv/`, ~129k rows); use `--limit N` to load only N rows per table when iterating fast
- All tests: `python -m unittest -v` (legacy 17) or `pytest -q` — both pick up `test_real_dataset.py`, which seeds a temp DB from `data/csv/` and skips if that folder is missing
- Single test: `python -m unittest -v test_engine.EngineTests.test_roles`
- CLI scan: `python cli.py scan` (only non-clean columns) / `python cli.py scan --table customers`
- CLI tables/mask: `python cli.py list-tables` | `python cli.py mask --table cards --role support --limit 10`
- CLI query/compare: `python cli.py query --role support "SELECT ..."` / `python cli.py compare "SELECT ..."`
- Dashboard: `streamlit run streamlit_app.py` (has a "Raw vs Masked" side-by-side tab with raw storage vs the selected role's masked view)
- No lint/format/typecheck config exists; use the unittest/pytest suites for verification.

## Environment/setup gotchas
- Git repo (initialized after prior work; `data/bank.db`, `data/pii_catalog.json`, `data/audit_chain.jsonl` are intentionally NOT committed — rebuild with `python seed.py --reset`). `.github/workflows/ci.yml` runs tests + cold-start smoke on push.
- Deployment: `Dockerfile` seeds DB + scans PII at build time; `python:3.12-slim`; app serves on 8501 with a healthcheck at `/_stcore/health`. Streamlit Cloud works too (repo ≈ 21MB CSVs, cold start auto-seeds).
- Cold-start bootstrap (`streamlit_app.bootstrap_db`, also in `cli.py`): seeds from `data/csv` when present, falls back to the legacy 50-row demo.
- Use the project venv: `./.venv/bin/python` / `./.venv/bin/streamlit`. System Python has no pip, and this WSL image lacks `ensurepip` (venv is created via `python3 -m venv --without-pip` + `get-pip.py`).
- Paths are CWD-relative (`data/bank.db`, `data/pii_catalog.json`, `data/audit_chain.jsonl`, `keys/`). Running from another directory creates or scans the wrong location.
- `BANK_DB` overrides only the database path; catalog and audit paths stay at their `data/` defaults.
- `fetch_backend_queues(token)` in `streamlit_app.py` (`@st.cache_data(ttl=60)`) issues one REST call per IBM backend for live `pending_jobs`/`operational`; the Settings popover renders the queue panel and feeds the backend selectbox (shortest queue first). A web/ React frontend was added then removed (user preference is Streamlit as the only UI); the earlier frontend removed itself in commit 1769070, so `web/` should not exist.

## Repo-specific traps
`data/bank.db` holds the **Saffron Bank** synthetic dataset (9 tables). The canonical source is the pack's CSVs in `data/csv/` — `seed.py --reset` rebuilds from them. IBM Quantum token is read only from `IBM_QUANTUM_TOKEN` env (or Settings UI). Empty token => local AerSimulator fallback. Never commit `.env`.
- Catalog fingerprinting: `data/pii_catalog.json` stores a `schema_fingerprint` (SHA3-256 of table/columns). `MaskingEngine` reuses the catalog when the fingerprint matches and silently re-scans when the DB changes or the file is the legacy list format.
- Public-demo hardening in `streamlit_app.py`: renders at most `MAX_DISPLAY_ROWS` (200) rows and throttles to 30 queries/min per session.
- Scanner heuristics are content-driven where possible: PAN (`AAAAA0000F`, e.g. `loan_applications.col_7` found by format alone), IFSC (`SAFF0004110-0747`), synthetic 9xx SSNs, Indian phone/pincode formats, and person-name shapes (`cust_nm`/`nominee_nm`/`NAME_ON_CARD`). Decoys (`ssn_verified`, `rrn`, `card_ref`) stay NON_SENSITIVE.
- Restricted roles (support/analyst) get `scrub_text_pii` applied to NON_SENSITIVE free-text columns (ticket text, narration) so embedded emails/phones/SSNs never surface; admin sees everything raw.
- `masking/quantum_entropy.py` was patched: `service = None` is initialized before token handling (without it, no-token runs crashed with `UnboundLocalError`).
- `data_masking/` was originally a full duplicate of the repo root. Edit the root tree only; do not maintain both copies.
- `keys/*_sk.bin` are committed private keys, and signatures in `data/audit_chain.jsonl` depend on them. Do not delete or regenerate keys unless invalidating existing audit records is intended.
- `cli.py` and the Streamlit app append to `data/audit_chain.jsonl` and may rewrite `data/pii_catalog.json`; treat those demo artifacts as mutable.
- Tests use temp DB/catalog/audit paths but still read repo-level `keys/`; run them from the repo root. They are local unless `IBM_QUANTUM_TOKEN` is set (an IBM token can trigger slow network calls).
- No hardcoded IBM token exists anywhere in source. The live token lives in `.env` (`IBM_QUANTUM_TOKEN=...`, gitignored) and is loaded by `masking/quantum_entropy.py` at import. Last verified working (connected to `ibm_kingston`, 156-qubit Heron QPU). Never print, commit, or copy the token into other files. The Settings popover in the dashboard prefills from the env var; leaving it empty falls back to the local `AerSimulator`.

## Behavior to preserve
- Non-admin roles are rejected when using `PII_HIGH` columns in WHERE/ORDER BY/GROUP BY/HAVING; unknown roles fail closed to redaction.
- The database is opened read-only and masking happens in memory; do not "fix" masking by writing masked values back to the DB.
