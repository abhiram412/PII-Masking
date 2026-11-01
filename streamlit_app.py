"""Streamlit dashboard for Quantum Data Masking & PQC (minimal + interactive)."""
import hashlib
import io
import os
import re
import sqlite3
import time

import pandas as pd
import streamlit as st

from masking import MaskingEngine, QueryRejected, SQLiteBackend
from masking.maskers import POLICIES
from seed import seed, seed_from_dataset

# Sync Streamlit Cloud secrets to environment if deployed on Streamlit Cloud
try:
    if hasattr(st, "secrets"):
        for k, v in st.secrets.items():
            if k not in os.environ and isinstance(v, str):
                os.environ[k] = v
except Exception:
    pass

DB = os.environ.get("BANK_DB", "data/bank.db")
CSV_DIR = os.path.join("data", "csv")
COLORS = {"partial": "#FEF3C7", "hash": "#DBEAFE", "redact": "#FEE2E2"}
ROLE_LABELS = {
    "admin": "Raw values · break-glass",
    "support": "Partial masking · verification",
    "analyst": "Hash + redact · analytics",
}
TAG_ORDER = ["PII_HIGH", "PII_MEDIUM", "FINANCIAL_CONFIDENTIAL", "NON_SENSITIVE"]

# Clean SQL presets without hardcoded limits (limit is chosen interactively)
EXAMPLES = {
    "Customers (PII profiles)": "SELECT customer_id, cust_nm, dob_dt, mob_no, emailid, addr_line1 FROM customers",
    "Cards + holder names": "SELECT CARD_NO, CARD_NETWORK, NAME_ON_CARD, CREDIT_LIMIT, OUTSTANDING_AMT FROM cards",
    "International (US PII + SSN)": "SELECT customer_id, ssn, us_addr, us_zip, us_phone FROM international_customers",
    "Join: masked account balances per customer": "SELECT c.cust_nm, a.account_no, a.curr_bal, a.od_limit_inr "
                                                  "FROM customers c JOIN accounts a ON a.customer_id = c.customer_id",
    "Aggregation: balances by segment (Lineage tracked)": "SELECT segment, COUNT(*) AS n, SUM(a.curr_bal) AS bank_exposure "
                                                         "FROM customers c JOIN accounts a ON a.customer_id = c.customer_id "
                                                         "GROUP BY segment ORDER BY bank_exposure DESC",
    "Bypass Attempt: WHERE ssn LIKE (Blocked)": "SELECT customer_id, ssn FROM international_customers WHERE ssn LIKE '9%'",
    "Bypass Attempt: ORDER BY ssn (Blocked)": "SELECT customer_id, ssn FROM international_customers ORDER BY ssn",
    "CTE Query (Lineage preserved)": "WITH cte AS (SELECT c.cust_nm, i.ssn, a.curr_bal FROM customers c "
                                     "JOIN international_customers i ON i.customer_id = c.customer_id "
                                     "JOIN accounts a ON a.customer_id = c.customer_id) "
                                     "SELECT cust_nm AS holder, ssn AS us_ssn, curr_bal * 2 AS doubled FROM cte",
    "Aggregate Query (Branch exposure)": "SELECT region, COUNT(*) AS branches, SUM(a.curr_bal) AS total "
                                         "FROM branches b JOIN accounts a ON a.branch_code = b.branch_code "
                                         "GROUP BY region ORDER BY total DESC",
}

st.set_page_config(page_title="Quantum Data Masking & PQC", layout="wide", page_icon="⚛️")

# Public-demo hardening: cap rendered rows and throttle per session
MAX_DISPLAY_ROWS = 200
RATE_LIMIT_QPS_WINDOW = 60
RATE_LIMIT_MAX_QUERIES = 30


def apply_limit_to_sql(query_sql: str, limit: int | None) -> str:
    """Intelligently applies row limit without modifying underlying group/order syntax."""
    clean_sql = re.sub(r"\s+LIMIT\s+\d+\s*;?$", "", query_sql.strip(), flags=re.IGNORECASE).rstrip(";")
    if limit is not None:
        return f"{clean_sql} LIMIT {limit}"
    return clean_sql


@st.cache_data(ttl=60, show_spinner=False)
def fetch_backend_queues(token: str) -> list[dict]:
    """Live IBM Quantum Platform queue snapshot: one row per backend.

    Sorted by shortest pending queue (operational first). Empty on failure
    so the UI can fall back to the hardcoded backend list.
    """
    if not token.strip():
        return []
    from qiskit_ibm_runtime import QiskitRuntimeService

    raw = token.strip()
    clean = raw[7:] if raw.startswith("ApiKey-") else raw
    service = None
    last_err: Exception | None = None
    for channel, tok in [
        ("ibm_quantum_platform", clean),
        ("ibm_cloud", clean),
        ("ibm_quantum_platform", raw),
    ]:
        try:
            service = QiskitRuntimeService(channel=channel, token=tok, instance="auto")
            break
        except Exception as exc:
            last_err = exc
    if service is None:
        raise RuntimeError(last_err)
    rows = []
    for backend in service.backends():
        try:
            status = backend.status()
            rows.append(
                {
                    "name": backend.name,
                    "qubits": backend.num_qubits,
                    "pending_jobs": status.pending_jobs,
                    "operational": status.operational,
                }
            )
        except Exception:
            continue
    rows.sort(key=lambda r: (not r["operational"], r["pending_jobs"]))
    return rows


# ---------------------------------------------------------------------------
# Session State: Theme and Font Size Scale
# ---------------------------------------------------------------------------
if "fs_scale" not in st.session_state:
    st.session_state.fs_scale = 100

if "theme_mode" not in st.session_state:
    st.session_state.theme_mode = "☀️ Light"

fs_multiplier = st.session_state.fs_scale / 100.0
is_dark = st.session_state.theme_mode == "🌙 Dark"

# Theme Variables — refined WCAG AA contrast, modern banking aesthetic
if is_dark:
    p_bg = "#0B1120"           # deep navy-slate
    p_surface = "#151E33"      # elevated card
    p_surface_2 = "#1C2740"    # secondary surface / inputs
    p_border = "#2D3A5C"       # subtle border
    p_text = "#F1F5F9"         # near-white
    p_muted = "#94A3B8"        # slate-400
    p_accent = "#38BDF8"       # sky-400
    p_accent_2 = "#A78BFA"     # violet-400
    p_success = "#34D399"
    p_warning = "#FBBF24"
    p_danger = "#F87171"
    p_shadow = "0 4px 24px rgba(0,0,0,0.35)"
    p_header_bg = "linear-gradient(135deg, #151E33 0%, #1C2740 100%)"
else:
    p_bg = "#F8FAFC"           # slate-50
    p_surface = "#FFFFFF"
    p_surface_2 = "#F1F5F9"    # slate-100
    p_border = "#E2E8F0"       # slate-200
    p_text = "#0F172A"         # slate-900
    p_muted = "#64748B"        # slate-500
    p_accent = "#0284C7"       # sky-600
    p_accent_2 = "#7C3AED"     # violet-600
    p_success = "#059669"
    p_warning = "#D97706"
    p_danger = "#DC2626"
    p_shadow = "0 1px 3px rgba(15,23,42,0.06), 0 4px 12px rgba(15,23,42,0.04)"
    p_header_bg = "linear-gradient(135deg, #FFFFFF 0%, #F1F5F9 100%)"

CSS = f"""
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&family=JetBrains+Mono:wght@400;500;600&display=swap');

:root {{
    --fs-scale: {fs_multiplier};
    --bg: {p_bg};
    --surface: {p_surface};
    --surface-2: {p_surface_2};
    --border: {p_border};
    --text: {p_text};
    --muted: {p_muted};
    --accent: {p_accent};
    --accent-2: {p_accent_2};
    --success: {p_success};
    --warning: {p_warning};
    --danger: {p_danger};
    --shadow: {p_shadow};
    --header-bg: {p_header_bg};
}}

html, body, [class*="css"], .stApp {{
    font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif !important;
    font-size: calc(14.5px * var(--fs-scale)) !important;
    background-color: var(--bg) !important;
    color: var(--text) !important;
    transition: background-color 180ms ease, color 180ms ease !important;
}}

.stApp {{
    background: var(--bg) !important;
    color: var(--text) !important;
}}

[data-testid="stHeader"] {{ background: transparent !important; }}
#MainMenu, footer {{ visibility: hidden !important; }}
.block-container {{
    padding-top: 1.2rem !important;
    max-width: 1280px !important;
    padding-bottom: 3rem !important;
    padding-left: 1.5rem !important;
    padding-right: 1.5rem !important;
}}

/* Headings */
h1, h2, h3, h4, h5, h6 {{
    color: var(--text) !important;
    font-weight: 700 !important;
    letter-spacing: -0.02em !important;
}}

.brand {{
    font-size: 1.28rem;
    letter-spacing: -0.025em;
    display: flex;
    align-items: center;
    gap: 10px;
    font-weight: 800;
}}
.brand-badge {{ color: var(--accent) !important; font-weight: 800; }}
.brand-title {{ font-weight: 800; color: var(--text) !important; }}
.sub {{
    font-size: 0.80rem;
    color: var(--muted) !important;
    margin-top: 0.2rem;
    font-weight: 500;
    line-height: 1.4;
}}
.row-limit-label {{
    font-size: 0.82rem;
    font-weight: 600;
    color: var(--muted) !important;
}}

/* Card Surface */
.card {{
    background: var(--surface) !important;
    border: 1px solid var(--border) !important;
    border-radius: 14px !important;
    padding: 18px 20px !important;
    box-shadow: var(--shadow) !important;
    margin-bottom: 16px !important;
}}

/* Top header bar */
.header-bar {{
    background: var(--header-bg) !important;
    border: 1px solid var(--border) !important;
    border-radius: 14px !important;
    padding: 14px 18px !important;
    margin-bottom: 18px !important;
    box-shadow: var(--shadow) !important;
}}

/* Navigation Tabs */
[data-baseweb="tab-list"] {{
    gap: 0.6rem !important;
    background: var(--surface) !important;
    border: 1px solid var(--border) !important;
    border-bottom: none !important;
    padding: 6px 10px 0 10px !important;
    border-radius: 12px 12px 0 0 !important;
    box-shadow: none !important;
}}
[data-baseweb="tab"] {{
    padding: 0.7rem 0.9rem !important;
    border-radius: 8px 8px 0 0 !important;
    color: var(--muted) !important;
    font-weight: 600 !important;
    font-size: 0.88rem !important;
    background: transparent !important;
    transition: color 150ms ease, background 150ms ease !important;
}}
[data-baseweb="tab"]:hover {{
    color: var(--accent) !important;
    background: var(--surface-2) !important;
}}
[data-baseweb="tab"][aria-selected="true"] {{
    color: var(--accent) !important;
    font-weight: 700 !important;
    background: var(--surface) !important;
}}
[data-baseweb="tab-highlight"] {{
    background: var(--accent) !important;
    height: 3px !important;
    border-radius: 3px 3px 0 0 !important;
}}
[data-baseweb="tab-border"] {{ display: none !important; }}

/* Buttons */
.stButton > button {{
    border-radius: 10px !important;
    border: 1px solid var(--border) !important;
    background: var(--surface-2) !important;
    color: var(--text) !important;
    font-weight: 600 !important;
    font-size: 0.86rem !important;
    transition: all 160ms ease !important;
    box-shadow: none !important;
}}
.stButton > button:hover {{
    border-color: var(--accent) !important;
    color: var(--accent) !important;
    background: var(--surface) !important;
}}
.stButton > button:focus {{
    outline: 2px solid var(--accent) !important;
    outline-offset: 2px !important;
}}
.stButton > button[kind="primary"] {{
    background: var(--accent) !important;
    border: 1px solid var(--accent) !important;
    color: #FFFFFF !important;
    font-weight: 700 !important;
    box-shadow: 0 2px 8px color-mix(in srgb, var(--accent) 35%, transparent) !important;
}}
.stButton > button[kind="primary"]:hover {{
    filter: brightness(1.08) !important;
    color: #FFFFFF !important;
}}

/* Inputs & Textareas */
.stTextArea textarea, .stTextInput input, .stNumberInput input, .stSelectbox [data-baseweb="select"] > div {{
    font-family: 'JetBrains Mono', ui-monospace, monospace !important;
    font-size: 0.84rem !important;
    background: var(--surface-2) !important;
    color: var(--text) !important;
    border: 1px solid var(--border) !important;
    border-radius: 10px !important;
}}
.stTextArea textarea:focus, .stTextInput input:focus, .stNumberInput input:focus {{
    border-color: var(--accent) !important;
    box-shadow: 0 0 0 3px color-mix(in srgb, var(--accent) 25%, transparent) !important;
}}

/* Segmented / Pills */
[data-testid="stSegmentedControl"] {{
    background: var(--surface-2) !important;
    padding: 4px !important;
    border-radius: 10px !important;
    border: 1px solid var(--border) !important;
}}
[data-testid="stSegmentedControl"] button {{
    font-size: 0.82rem !important;
    font-weight: 600 !important;
    color: var(--muted) !important;
    border-radius: 7px !important;
}}
[data-testid="stSegmentedControl"] button[aria-selected="true"] {{
    background: var(--accent) !important;
    color: #FFFFFF !important;
    font-weight: 700 !important;
}}

/* Pills (examples) */
[data-testid="stPills"] button {{
    border-radius: 999px !important;
    font-size: 0.78rem !important;
    font-weight: 600 !important;
    border: 1px solid var(--border) !important;
    background: var(--surface) !important;
    color: var(--muted) !important;
}}
[data-testid="stPills"] button[aria-selected="true"] {{
    background: color-mix(in srgb, var(--accent) 12%, var(--surface)) !important;
    border-color: var(--accent) !important;
    color: var(--accent) !important;
}}

/* Dataframes */
[data-testid="stDataFrame"] {{
    border: 1px solid var(--border) !important;
    border-radius: 12px !important;
    background: var(--surface) !important;
    overflow: hidden !important;
    box-shadow: var(--shadow) !important;
}}

/* Expanders */
[data-testid="stExpander"] {{
    border: 1px solid var(--border) !important;
    border-radius: 12px !important;
    background: var(--surface) !important;
    color: var(--text) !important;
}}
[data-testid="stExpander"] details {{
    background: var(--surface) !important;
}}
[data-testid="stPopoverBody"] {{
    background: var(--surface) !important;
    border: 1px solid var(--border) !important;
    color: var(--text) !important;
    border-radius: 12px !important;
    box-shadow: 0 8px 24px rgba(0,0,0,0.12) !important;
}}

/* Labels */
label, [data-testid="stWidgetLabel"] p {{
    color: var(--text) !important;
    font-weight: 600 !important;
    font-size: 0.86rem !important;
}}
.stCaption, [data-testid="stCaptionContainer"] p {{
    color: var(--muted) !important;
    font-weight: 500 !important;
}}

/* Alerts / status */
[data-testid="stAlert"] {{
    border-radius: 12px !important;
    border: 1px solid var(--border) !important;
}}

/* Code */
code {{
    font-family: 'JetBrains Mono', monospace !important;
    background: var(--surface-2) !important;
    color: var(--text) !important;
    padding: 2px 7px !important;
    border-radius: 6px !important;
    border: 1px solid var(--border) !important;
}}

/* Slider */
[data-baseweb="slider"] div {{
    color: var(--text) !important;
}}

/* Metric cards */
[data-testid="stMetric"] {{
    background: var(--surface) !important;
    border: 1px solid var(--border) !important;
    border-radius: 12px !important;
    padding: 12px 16px !important;
}}

/* Scrollbar */
::-webkit-scrollbar {{ width: 8px; height: 8px; }}
::-webkit-scrollbar-track {{ background: var(--surface-2); }}
::-webkit-scrollbar-thumb {{ background: var(--border); border-radius: 4px; }}
::-webkit-scrollbar-thumb:hover {{ background: var(--muted); }}

/* Success / error chips used in NER */
.ner-chip-high {{
    background: color-mix(in srgb, var(--danger) 15%, transparent);
    color: var(--danger);
    border: 1px solid color-mix(in srgb, var(--danger) 40%, transparent);
    border-radius: 6px;
    padding: 2px 8px;
    font-weight: 700;
    font-size: 0.78rem;
}}
.ner-chip-medium {{
    background: color-mix(in srgb, var(--accent) 12%, transparent);
    color: var(--accent);
    border: 1px solid color-mix(in srgb, var(--accent) 35%, transparent);
    border-radius: 6px;
    padding: 2px 8px;
    font-weight: 700;
    font-size: 0.78rem;
}}
</style>
"""
st.markdown(CSS, unsafe_allow_html=True)


def rate_limited() -> bool:
    """True (and records the attempt) if this session exceeded the query budget."""
    now = time.time()
    recent = [t for t in st.session_state.get("query_times", []) if now - t < RATE_LIMIT_QPS_WINDOW]
    if len(recent) >= RATE_LIMIT_MAX_QUERIES:
        st.session_state.query_times = recent
        return True
    st.session_state.query_times = recent + [now]
    return False


def compute_db_hash(path: str) -> str:
    """Computes SHA-256 of SQLite database dump to prove physical immutability."""
    if not os.path.exists(path):
        return "N/A"
    conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    h = hashlib.sha256()
    for line in conn.iterdump():
        h.update(line.encode("utf-8"))
    conn.close()
    return h.hexdigest()


def bootstrap_db(db_path: str) -> None:
    """Cold-start bootstrap: Saffron Bank CSVs if available, legacy demo otherwise."""
    if os.path.exists(db_path):
        return
    if os.path.isfile(os.path.join(CSV_DIR, "customers.csv")):
        seed_from_dataset(dataset_dir=CSV_DIR)
        return
    seed(db_path, n_customers=50)


@st.cache_resource
def get_engine():
    bootstrap_db(DB)
    eng = MaskingEngine(SQLiteBackend(DB))
    if not eng.tags:
        eng.scan()
    return eng


@st.cache_data(ttl=300, show_spinner=False)
def dataset_stats(db_path: str, _mtime: float) -> tuple[list[str], dict[str, int]]:
    conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    try:
        tables = [r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")]
        rows = {
            t: conn.execute(f'SELECT COUNT(*) FROM "{t.replace(chr(34), chr(34) * 2)}"').fetchone()[0]
            for t in tables
        }
    finally:
        conn.close()
    return tables, rows


def filter_sort(df: pd.DataFrame, key: str) -> pd.DataFrame:
    """Search bar + alphabetical sort toolbar for an in-memory table."""
    if df.empty:
        return df
    col_search, col_sort, col_order = st.columns([3, 1.8, 0.9])
    term = col_search.text_input(
        "Search", "", placeholder="Search any value…", key=f"{key}_search", label_visibility="collapsed"
    )
    sort_col = col_sort.selectbox(
        "Sort by", ["Original order", *df.columns], key=f"{key}_sort", label_visibility="collapsed"
    )
    order = col_order.segmented_control(
        "Order", ["A-Z", "Z-A"], default="A-Z", key=f"{key}_order", label_visibility="collapsed"
    )
    out = df
    if term:
        mask = out.astype(str).apply(lambda c: c.str.contains(term, case=False, regex=False))
        out = out[mask.any(axis=1)]
    if sort_col != "Original order":
        keys = out[sort_col].astype(str).str.upper()
        out = out.loc[keys.sort_values(ascending=order != "Z-A").index]
    if term or sort_col != "Original order":
        st.caption(f"{len(out):,} of {len(df):,} rows")
    return out


def show(result, key: str = "result"):
    df = pd.DataFrame(result.rows, columns=result.columns)
    action = {r["column"]: r["action"] for r in result.column_report}
    if len(df) > MAX_DISPLAY_ROWS:
        st.caption(f"Showing first {MAX_DISPLAY_ROWS:,} of {result.row_count:,} rows.")
        df = df.head(MAX_DISPLAY_ROWS)

    def paint(col):
        act = action.get(str(col.name)) or ""
        if act == "partial":
            return ["background-color: rgba(245, 158, 11, 0.22); color: #D97706; font-weight: 700;"] * len(col)
        elif act == "hash":
            return ["background-color: rgba(59, 130, 246, 0.22); color: #3B82F6; font-weight: 700;"] * len(col)
        elif act == "redact":
            return ["background-color: rgba(239, 68, 68, 0.22); color: #EF4444; font-weight: 700;"] * len(col)
        return [""] * len(col)

    if df.columns.is_unique and df.index.is_unique:
        df = filter_sort(df, key)
        st.dataframe(df.style.apply(paint, axis=0), hide_index=True, width="stretch")
    elif df.columns.is_unique:
        st.dataframe(df.style.apply(paint, axis=0), hide_index=True, width="stretch")
    else:
        st.dataframe(df, hide_index=True, width="stretch")
    protected = [r for r in result.column_report if r["action"] != "none"]
    if protected:
        st.caption("Masked: " + " · ".join(f'{r["column"]} ({r["action"]})' for r in protected))


engine = get_engine()
stats_mtime = os.path.getmtime(DB) if os.path.exists(DB) else 0.0
tables, table_rows = dataset_stats(DB, stats_mtime)
total_rows = sum(table_rows.values())
pii_count = sum(1 for t in engine.tags if t.tag != "NON_SENSITIVE")

# ---------------------------------------------------------------------------
# Header & Navigation Bar
# ---------------------------------------------------------------------------
top_brand, top_role, top_fs, top_theme, top_settings = st.columns(
    [2.0, 1.2, 1.15, 0.95, 0.6], vertical_alignment="center"
)

with top_brand:
    st.markdown(
        '<div class="brand"><span class="brand-badge">⚛️ Quantum</span> <span class="brand-title">Data Masking & PQC</span></div>'
        '<div class="sub">Query-time PII Protection · Qiskit Quantum Entropy (QRNG) · Dilithium Post-Quantum Signatures</div>',
        unsafe_allow_html=True,
    )

with top_role:
    role_choice = st.segmented_control(
        "Role",
        list(POLICIES),
        default="support",
        key="role",
        label_visibility="collapsed",
        width="stretch",
    )
role = role_choice or "support"

with top_fs:
    # Font scale controls: A- / Reset / A+
    c_fs_down, c_fs_val, c_fs_up = st.columns([0.8, 1.4, 0.8], vertical_alignment="center")
    with c_fs_down:
        if st.button("A−", key="fs_dec", help="Decrease font size", use_container_width=True):
            if st.session_state.fs_scale > 85:
                st.session_state.fs_scale -= 5
                st.rerun()
    with c_fs_val:
        if st.button(f"{st.session_state.fs_scale}%", key="fs_reset", help="Click to reset font size to 100%", use_container_width=True):
            st.session_state.fs_scale = 100
            st.rerun()

    with c_fs_up:
        if st.button("A+", key="fs_inc", help="Increase font size", use_container_width=True):
            if st.session_state.fs_scale < 150:
                st.session_state.fs_scale += 5
                st.rerun()

with top_theme:
    new_theme = st.segmented_control(
        "Theme",
        ["☀️ Light", "🌙 Dark"],
        default=st.session_state.theme_mode,
        key="theme_mode_selector",
        label_visibility="collapsed",
        width="stretch",
    )
    if new_theme and new_theme != st.session_state.theme_mode:
        st.session_state.theme_mode = new_theme
        st.rerun()

with top_settings:
    with st.popover("Settings", width="stretch"):
        st.markdown("**Quantum key management (QRNG)**")
        custom_token = st.text_input(
            "IBM Quantum API token",
            value=os.environ.get("IBM_QUANTUM_TOKEN", ""),
            type="password",
            help="Leave empty to use the local simulator",
        )
        token_for_ui = (custom_token or "").strip() or os.environ.get("IBM_QUANTUM_TOKEN", "").strip()
        queues: list[dict] = []
        if token_for_ui:
            try:
                queues = fetch_backend_queues(token_for_ui)
            except Exception:
                queues = []
        online = [b for b in queues if b["operational"]]

        if queues:
            peak = max(b["pending_jobs"] for b in queues) or 1
            st.markdown("**IBM platform queues**")
            for idx, backend_q in enumerate(online[:8]):
                tag = " — shortest queue" if idx == 0 else ""
                st.write(
                    f"`{backend_q['name']}` · {backend_q['qubits']} qubits · "
                    f"**{backend_q['pending_jobs']}** pending jobs{tag}"
                )
                st.progress(min(1.0, backend_q["pending_jobs"] / peak))
            if st.button("Refresh queues"):
                fetch_backend_queues.clear()
                st.rerun()
            st.caption("Sorted by shortest queue · cached for 60 s")
        elif token_for_ui:
            st.caption("Could not reach IBM Quantum Platform — using default backend list.")

        options = [b["name"] for b in online]
        for preset in ("ibm_kingston", "ibm_fez", "ibm_marrakesh"):
            if preset not in options:
                options.append(preset)
        backend_choice = st.selectbox(
            "IBM Quantum backend (shortest queue first)",
            options=options,
            index=0,
            help="Live from IBM Quantum Platform when a token is set, sorted by pending jobs.",
        )
        engine.quantum.set_backend(backend_choice)

        c1, c2 = st.columns(2)
        with c1:
            if st.button("Connect IBM", width="stretch"):
                if custom_token:
                    new_res = engine.quantum.set_token(custom_token)
                    fetch_backend_queues.clear()
                    if new_res.is_ibm_cloud:
                        st.success(f"Connected: {new_res.backend_name}")
                    else:
                        st.warning("Using Qiskit Aer (local sim)")
        with c2:
            if st.button("Rotate seed", width="stretch"):
                engine.quantum.generate_entropy()
                st.success("Entropy rotated")

        if st.button(f"Submit circuit to {backend_choice}", type="primary", width="stretch"):
            try:
                with st.spinner("Submitting Hadamard circuit..."):
                    j_info = engine.quantum.submit_job_to_ibm_cloud(backend_name=backend_choice)
                    st.success(f"Job active on {j_info['backend']} — `{j_info['job_id']}`")
                    st.markdown(f"[View job]({j_info['platform_url']})")
                    st.code(j_info["circuit_ascii"], language="text")
            except Exception as exc:
                st.error(f"Submission note: {exc}")

        q_res = engine.quantum.cached_entropy
        if q_res:
            with st.expander("Provenance", expanded=False):
                mode = "IBM Quantum Platform" if q_res.is_ibm_cloud else "Qiskit Aer (local sim)"
                st.write(f"**Backend:** `{q_res.backend_name}` · {mode}")
                st.write(f"**Circuit:** {q_res.num_qubits} qubits · depth {q_res.circuit_depth} · {q_res.shots} shots")
                if getattr(q_res, "job_id", None):
                    st.write(f"**Job ID:** `{q_res.job_id}`")
                st.write(f"**Seed (SHA3-256):** `{q_res.entropy_hex[:16]}...`")
                if q_res.bitstring_sample:
                    st.write(f"**Bit samples:** `{', '.join(q_res.bitstring_sample[:4])}`")
                if q_res.circuit_str:
                    st.code(q_res.circuit_str, language="text")
                if q_res.error_message:
                    st.caption(f"Note: {q_res.error_message}")

        st.markdown("**Role policy matrix**")
        st.dataframe(pd.DataFrame(POLICIES).T.fillna("none"), width="stretch")

q_res = engine.quantum.cached_entropy
quantum_mode = "IBM Quantum" if (q_res and q_res.is_ibm_cloud) else "local QRNG sim"
st.caption(
    f"{len(tables)} tables · {total_rows:,} rows · {pii_count} sensitive columns · "
    f"read-only · {quantum_mode} · {ROLE_LABELS.get(role, '')}"
)

# ---------------------------------------------------------------------------
# Navigation Tabs
# ---------------------------------------------------------------------------
tab_q, tab_cmp, tab_side, tab_raw, tab_scan, tab_audit = st.tabs(
    ["Query", "Compare", "Raw vs Masked", "Storage", "Catalog", "Audit"]
)

if "sql" not in st.session_state:
    st.session_state.sql = EXAMPLES["Customers (PII profiles)"]


def load_preset():
    chosen = st.session_state.get("example_pill")
    if chosen:
        st.session_state.sql = EXAMPLES[chosen]


with tab_q:
    st.pills(
        "Examples",
        list(EXAMPLES),
        default="Customers (PII profiles)",
        key="example_pill",
        on_change=load_preset,
        label_visibility="collapsed",
    )
    sql = st.text_area("SQL", key="sql", height=105, label_visibility="collapsed")

    col_run, col_limit_lbl, col_limit = st.columns([1.5, 0.7, 3.2], vertical_alignment="center")
    with col_run:
        run_btn = st.button(f"Run as {role}", type="primary", use_container_width=True)
    with col_limit_lbl:
        st.markdown("<span class='row-limit-label'>Row Limit:</span>", unsafe_allow_html=True)
    with col_limit:
        limit_choice = st.segmented_control(
            "Row Limit",
            ["5 rows", "10 rows", "25 rows", "50 rows", "100 rows", "No Limit"],
            default="10 rows",
            key="query_row_limit",
            label_visibility="collapsed",
        )

    limit_map = {
        "5 rows": 5,
        "10 rows": 10,
        "25 rows": 25,
        "50 rows": 50,
        "100 rows": 100,
        "No Limit": None,
    }
    chosen_limit = limit_map.get(limit_choice or "10 rows", 10)
    effective_sql = apply_limit_to_sql(sql, chosen_limit)

    if run_btn:
        if rate_limited():
            st.warning("Rate limit reached (30 queries/min per session). Try again shortly.")
            st.stop()

        ibm_job_info: dict | None = None
        ibm_error: str | None = None
        try:
            ibm_job_info = engine.quantum.submit_job_to_ibm_cloud(backend_name=backend_choice)
        except Exception as exc:
            ibm_error = str(exc)

        try:
            t0 = time.time()
            with st.spinner(f"Running as {role}..."):
                res = engine.query(role, effective_sql)
            elapsed = (time.time() - t0) * 1000
        except QueryRejected as exc:
            st.error(f"Rejected by policy engine: {exc}")
        except Exception as exc:
            st.error(f"Execution error: {exc}")
        else:
            limit_tag = f" · limit {chosen_limit}" if chosen_limit else ""
            st.toast(f"{res.row_count} rows{limit_tag} · {elapsed:.0f} ms · masked for {role}")
            if ibm_job_info:
                st.toast(f"IBM job queued on {ibm_job_info['backend']}: {ibm_job_info['job_id'][:12]}…")
            elif ibm_error:
                st.warning(f"IBM platform not used for this run: {ibm_error}")
            show(res, key="query")
            q_info = engine.quantum.cached_entropy
            rec = res.audit_record
            enc = engine.pqc.envelope_encrypt(
                f"query_id={rec.query_id if rec else 'demo'}"
            )
            with st.expander("Details", expanded=False):
                st.caption(f"Executed SQL: `{effective_sql}`")
                st.json({
                    "quantum_entropy_qrng": {
                        "backend": q_info.backend_name if q_info else "N/A",
                        "num_qubits": q_info.num_qubits if q_info else 0,
                        "shots": q_info.shots if q_info else 0,
                        "circuit_depth": q_info.circuit_depth if q_info else 0,
                        "bitstring_samples": q_info.bitstring_sample if q_info else [],
                        "entropy_seed_hex": q_info.entropy_hex if q_info else "",
                    },
                    "ibm_quantum_job": {
                        "backend": ibm_job_info["backend"] if ibm_job_info else "N/A",
                        "job_id": ibm_job_info["job_id"] if ibm_job_info else "N/A",
                        "status": ibm_job_info["status"] if ibm_job_info else "N/A",
                        "url": ibm_job_info["platform_url"] if ibm_job_info else "N/A",
                    },
                    "post_quantum_envelope_encryption_fips_203": enc,
                    "post_quantum_audit_signature_fips_204": {
                        "algorithm": rec.sig_alg if rec else "N/A",
                        "key_id": rec.key_id if rec else "N/A",
                        "signature_base64": rec.signature if rec else "N/A",
                        "entry_hash": rec.entry_hash if rec else "N/A",
                        "prev_hash": rec.prev_hash if rec else "N/A",
                    },
                })
                if q_info and getattr(q_info, "circuit_str", None):
                    st.code(q_info.circuit_str, language="text")

with tab_cmp:
    col_cmp_btn, col_cmp_lbl, col_cmp_limit = st.columns([1.5, 0.7, 3.2], vertical_alignment="center")
    with col_cmp_btn:
        cmp_btn = st.button("Compare all roles", type="primary", use_container_width=True)
    with col_cmp_lbl:
        st.markdown("<span class='row-limit-label'>Row Limit:</span>", unsafe_allow_html=True)
    with col_cmp_limit:
        cmp_limit_sel = st.segmented_control(
            "Compare Limit",
            ["5 rows", "10 rows", "25 rows", "50 rows"],
            default="5 rows",
            key="cmp_limit_sel",
            label_visibility="collapsed",
        )

    cmp_limit = {"5 rows": 5, "10 rows": 10, "25 rows": 25, "50 rows": 50}.get(cmp_limit_sel or "5 rows", 5)
    effective_cmp_sql = apply_limit_to_sql(st.session_state.sql, cmp_limit)

    if cmp_btn:
        try:
            ibm_j = engine.quantum.submit_job_to_ibm_cloud(backend_name=backend_choice)
            st.caption(f"IBM job `{ibm_j['job_id'][:14]}…` queued on {ibm_j['backend']} for this comparison")
        except Exception as exc:
            st.caption(f"IBM platform not used for this comparison: {exc}")
        cols = st.columns(len(POLICIES))
        for col, r in zip(cols, POLICIES):
            with col:
                st.markdown(f"**{r.upper()}**")
                st.caption(ROLE_LABELS.get(r, ""))
                try:
                    show(engine.query(r, effective_cmp_sql), key=f"cmp_{r}")
                except QueryRejected as exc:
                    st.warning(f"Blocked: {exc}")
                except Exception as exc:
                    st.error(str(exc))
    else:
        st.caption("Runs the current SQL from the Query tab across admin, support, and analyst with the selected row limit.")

with tab_side:
    c1, c2 = st.columns([1, 1])
    with c1:
        side_table = st.pills("Table", tables, default="customers", key="side_table", label_visibility="collapsed")
    with c2:
        side_role = st.segmented_control(
            "Masked role", list(POLICIES), default="support", key="side_role", label_visibility="collapsed"
        ) or "support"
    preview_rows = st.slider("Rows", 5, 50, 10, label_visibility="collapsed")

    if side_table:
        raw_cols, raw_rows, _ = engine.backend.execute_readonly(
            f"SELECT * FROM {engine.backend.quote(side_table)} LIMIT {preview_rows}"
        )
        raw_df = pd.DataFrame(raw_rows, columns=raw_cols)
        masked_res = None
        masked_df = pd.DataFrame()
        try:
            masked_res = engine.query(
                side_role, f"SELECT * FROM {engine.backend.quote(side_table)} LIMIT {preview_rows}"
            )
            masked_df = pd.DataFrame(masked_res.rows, columns=masked_res.columns)
        except QueryRejected as exc:
            st.warning(f"Masked view unavailable: {exc}")
        except Exception as exc:
            st.warning(f"Masked view unavailable: {exc}")

        left, right = st.columns(2, gap="large")
        with left:
            st.caption("Raw storage")
            st.dataframe(filter_sort(raw_df, "side_raw"), hide_index=True, width="stretch")
        with right:
            st.caption(f"Masked · {side_role}")
            if not masked_df.empty:
                masked_df = filter_sort(masked_df, "side_masked")
            st.dataframe(masked_df, hide_index=True, width="stretch")
        if masked_res is not None:
            masked_cols = [c for c in masked_res.column_report if c["action"] != "none"]
            st.caption(
                "Masked: " + (" · ".join(f'{c["column"]} ({c["action"]})' for c in masked_cols) or "none")
            )

with tab_raw:
    st.caption("SHA-256 of the physical database dump. Opened read-only, so it stays constant across queries.")
    st.code(compute_db_hash(DB), language=None)
    table = st.pills("Inspect table", tables, default="customers", key="raw_table", label_visibility="collapsed")
    if table:
        cols, rows, _ = engine.backend.execute_readonly(
            f"SELECT * FROM {engine.backend.quote(table)} LIMIT 20"
        )
        st.dataframe(filter_sort(pd.DataFrame(rows, columns=cols), "inspect"), hide_index=True, width="stretch")

with tab_scan:
    tag_filter = st.pills(
        "Sensitivity",
        TAG_ORDER,
        selection_mode="multi",
        default=[t for t in TAG_ORDER if t != "NON_SENSITIVE"],
        key="tag_filter",
        label_visibility="collapsed",
    )
    table_filter = st.pills(
        "Tables", ["all", *tables], default="all", key="table_filter", label_visibility="collapsed"
    )
    c1, c2 = st.columns([1, 5])
    with c1:
        if st.button("Re-scan"):
            engine.scan()
            st.toast("Catalog re-scanned")
    visible = [
        t for t in engine.tags
        if t.tag in tag_filter and (table_filter in (None, "all") or t.table == table_filter)
    ]
    tags_df = pd.DataFrame([
        {
            "Table": t.table,
            "Column": t.column,
            "Type": t.sql_type,
            "Tag": t.tag,
            "Confidence": f"{t.confidence:.1%}",
            "Detector": t.detector,
        }
        for t in visible
    ])
    st.dataframe(filter_sort(tags_df, "catalog"), hide_index=True, width="stretch")

with tab_audit:
    c1, c2 = st.columns([1, 5])
    with c1:
        verify = st.button("Verify chain", type="primary")
    if verify:
        v_res = engine.verify_audit_trail()
        if v_res.get("valid"):
            st.success(f"Verified · {v_res.get('status')}")
        else:
            st.error(f"Verification failed · {v_res.get('status')}")
    entries = engine.recent_audit(50)
    if entries:
        st.dataframe(pd.DataFrame(entries), hide_index=True, width="stretch")
    else:
        st.caption("No audit entries yet. Run a query to generate one.")
