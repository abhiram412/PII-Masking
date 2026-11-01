"""Create a deterministic demo financial database with rich synthetic data, disguised columns, and golden records."""
from __future__ import annotations

import os
import random
import sqlite3
import sys

FIRST = [
    "Alice", "Asha", "Ravi", "Meera", "Karthik", "Sneha", "Arjun", "Divya", "Imran", "Priya",
    "Vikram", "Anita", "Rohan", "Nisha", "Suresh", "Lakshmi", "Aman", "Pooja", "Harsha", "Tara"
]
LAST = [
    "Johnson", "Verma", "Reddy", "Nair", "Sharma", "Iyer", "Khan", "Patel", "Rao", "Das", "Mehta"
]
CITIES = ["Springfield", "Pune", "Hyderabad", "Chennai", "Mumbai", "Bengaluru", "New York", "London"]
STREETS = ["742 Evergreen Terrace", "MG Road", "Lake View Rd", "Park Street", "Station Road", "Hill Avenue"]
MERCHANTS = ["Amazon", "Uber", "Netflix", "Swiggy", "Flipkart", "Apple Store", "Starbucks", "Shell"]


def luhn_check_digit(body: str) -> str:
    total = 0
    for i, ch in enumerate(reversed(body)):
        d = int(ch)
        if i % 2 == 0:
            d *= 2
            if d > 9:
                d -= 9
        total += d
    return str((10 - total % 10) % 10)


def make_card(rng: random.Random) -> str:
    body = "4" + "".join(str(rng.randint(0, 9)) for _ in range(14))
    n = body + luhn_check_digit(body)
    return "-".join(n[i:i + 4] for i in range(0, 16, 4))


def compute_iban_check(country_code: str, bban: str) -> str:
    """Computes ISO 7064 mod-97 check digits for IBAN."""
    converted = ""
    for ch in (bban + country_code + "00"):
        if ch.isdigit():
            converted += ch
        else:
            converted += str(ord(ch.upper()) - 55)
    remainder = int(converted) % 97
    check = 98 - remainder
    return f"{check:02d}"


def make_ssn(rng: random.Random) -> str:
    """Generates valid US SSN format avoiding invalid area 666 and 000/900+."""
    area = rng.randint(101, 899)
    while area == 666:
        area = rng.randint(101, 899)
    group = rng.randint(10, 99)
    serial = rng.randint(1000, 9999)
    return f"{area:03d}-{group:02d}-{serial:04d}"


def make_iban(rng: random.Random, bank_code="37040044", acct="0532013000") -> str:
    bban = f"{bank_code}{acct}"
    chk = compute_iban_check("DE", bban)
    return f"DE{chk}{bban}"


def seed(path: str, n_customers: int = 50, seed_value: int = 42) -> None:
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    if os.path.exists(path):
        os.remove(path)
    rng = random.Random(seed_value)
    conn = sqlite3.connect(path)

    # Tables with compatibility aliases (id and customer_id, etc.)
    conn.executescript("""
        CREATE TABLE customers (
            id INTEGER PRIMARY KEY,
            customer_id INTEGER,
            first_name TEXT,
            last_name TEXT,
            full_name TEXT,
            email TEXT,
            phone TEXT,
            ssn TEXT,
            dob TEXT,
            address TEXT,
            city TEXT,
            country TEXT,
            notes TEXT,            -- Disguised column: contains SSN in >80% of rows
            ssn_verified INTEGER,  -- Decoy column: BOOLEAN, must NOT be tagged
            contact TEXT,          -- Alternate email
            created_at TEXT
        );

        CREATE TABLE accounts (
            id INTEGER PRIMARY KEY,
            account_id INTEGER,
            customer_id INTEGER,
            iban TEXT,
            account_number TEXT,
            card_number TEXT,
            balance REAL,
            currency TEXT,
            account_type TEXT,
            opened_at TEXT
        );

        CREATE TABLE cards (
            id INTEGER PRIMARY KEY,
            customer_id INTEGER,
            card_number TEXT,
            card_type TEXT,
            expiry TEXT,
            holder_name TEXT
        );

        CREATE TABLE transactions (
            id INTEGER PRIMARY KEY,
            txn_id INTEGER,
            account_id INTEGER,
            amount REAL,
            merchant TEXT,
            ts TEXT,
            txn_date TEXT
        );
    """)

    txn_counter = 1
    for cid in range(1, n_customers + 1):
        if cid == 1:
            # Golden Record Customer 1
            first_name = "Alice"
            last_name = "Johnson"
            full_name = "Alice Johnson"
            email = "alice.johnson@example.com"
            phone = "+1 (415) 555-0134"
            ssn = "123-45-6789"
            dob = "1990-05-17"
            address = "742 Evergreen Terrace"
            city = "Springfield"
            country = "US"
            notes = "321-54-9876"  # Disguised SSN
            ssn_verified = 1
            contact = "alt.alice@example.com"
            created_at = "2024-01-15 10:30:00"

            iban = "DE89370400440532013000"
            account_number = "0532013000"
            balance = 25432.50
            currency = "EUR"
            card_number = "4111-1111-1111-1111"
            card_type = "VISA"
            expiry = "2029-12"
            holder_name = "Alice Johnson"
        else:
            first_name = rng.choice(FIRST)
            last_name = rng.choice(LAST)
            full_name = f"{first_name} {last_name}"
            email = f"{first_name.lower()}.{last_name.lower()}{cid}@example.com"
            phone = f"+1 ({rng.randint(200, 999)}) {rng.randint(100, 999)}-{rng.randint(1000, 9999)}"
            ssn = make_ssn(rng)
            dob = f"{rng.randint(1965, 2003)}-{rng.randint(1, 12):02d}-{rng.randint(1, 28):02d}"
            city = rng.choice(CITIES)
            country = "US" if city in ["Springfield", "New York"] else "IN"
            address = f"{rng.randint(10, 990)} {rng.choice(STREETS)}, {city}"

            # Disguised column trap: 85% rows have SSN format
            if rng.random() < 0.85:
                notes = make_ssn(rng)
            else:
                notes = "Customer requested paperless statement."

            ssn_verified = 1 if rng.random() > 0.3 else 0
            contact = f"alt.{email}"
            created_at = f"2024-{rng.randint(1, 12):02d}-{rng.randint(1, 28):02d} 09:00:00"

            acct_digits = f"{rng.randint(10**9, 10**10 - 1)}"
            account_number = acct_digits
            iban = make_iban(rng, acct=acct_digits[:10])
            balance = round(rng.choice([rng.uniform(500, 8500), rng.uniform(12000, 75000), rng.uniform(120000, 850000)]), 2)
            currency = rng.choice(["USD", "EUR", "GBP"])
            card_number = make_card(rng)
            card_type = rng.choice(["VISA", "MASTERCARD", "AMEX"])
            expiry = f"202{rng.randint(6, 9)}-{rng.randint(1, 12):02d}"
            holder_name = full_name

        conn.execute(
            """INSERT INTO customers (id, customer_id, first_name, last_name, full_name, email, phone, ssn, dob, address, city, country, notes, ssn_verified, contact, created_at)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (cid, cid, first_name, last_name, full_name, email, phone, ssn, dob, address, city, country, notes, ssn_verified, contact, created_at)
        )

        conn.execute(
            """INSERT INTO accounts (id, account_id, customer_id, iban, account_number, card_number, balance, currency, account_type, opened_at)
               VALUES (?,?,?,?,?,?,?,?,?,?)""",
            (cid, cid, cid, iban, account_number, card_number, balance, currency, rng.choice(["SAVINGS", "CHECKING", "INVESTMENT"]), created_at)
        )

        conn.execute(
            """INSERT INTO cards (id, customer_id, card_number, card_type, expiry, holder_name)
               VALUES (?,?,?,?,?,?)""",
            (cid, cid, card_number, card_type, expiry, holder_name)
        )

        for _ in range(rng.randint(1, 4)):
            amt = round(rng.uniform(15.0, 3500.0), 2)
            merch = rng.choice(MERCHANTS)
            ts = f"2026-0{rng.randint(1, 9)}-{rng.randint(1, 28):02d} 14:22:00"
            conn.execute(
                """INSERT INTO transactions (id, txn_id, account_id, amount, merchant, ts, txn_date)
                   VALUES (?,?,?,?,?,?,?)""",
                (txn_counter, txn_counter, cid, amt, merch, ts, ts[:10])
            )
            txn_counter += 1

    # Load MOCK_DATA.csv if available
    csv_candidates = [
        "MOCK_DATA.csv",
        os.path.join(os.path.dirname(path) or ".", "MOCK_DATA.csv"),
        os.path.join(os.path.dirname(os.path.abspath(__file__)), "MOCK_DATA.csv"),
    ]
    mock_csv = next((p for p in csv_candidates if os.path.exists(p)), None)
    if mock_csv:
        import csv
        conn.execute("""
            CREATE TABLE IF NOT EXISTS mock_users (
                id INTEGER PRIMARY KEY,
                first_name TEXT,
                last_name TEXT,
                email TEXT,
                gender TEXT,
                ip_address TEXT
            );
        """)
        with open(mock_csv, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            mock_rows = [
                (int(r["id"]), r["first_name"], r["last_name"], r["email"], r["gender"], r["ip_address"])
                for r in reader
            ]
            conn.executemany(
                "INSERT OR REPLACE INTO mock_users (id, first_name, last_name, email, gender, ip_address) VALUES (?, ?, ?, ?, ?, ?)",
                mock_rows
            )

    conn.commit()
    conn.close()




# ---------------------------------------------------------------------------
# Real dataset loading (Saffron Bank pack CSVs -> SQLite / Postgres / MySQL)
# ---------------------------------------------------------------------------
import argparse
import re
from pathlib import Path

import pandas as pd

DEFAULT_DB_PATH = os.environ.get("BANK_DB", "data/bank.db")
DEFAULT_DATASET_DIR = os.environ.get("DATASET_DIR", "data/csv")
DEFAULT_SCHEMA_PATH = "data/schema/saffron_schema.sql"
POSTGRES_DSN_ENV = "POSTGRES_DSN"
MYSQL_DSN_ENV = "MYSQL_DSN"

NUMERIC_TYPE_RE = re.compile(r"\b(INT(?!ERVAL)|REAL|FLOAT|DOUBLE|NUMERIC|DECIMAL)\b", re.I)
DDL_BLOCK_RE = re.compile(r"CREATE TABLE[^;]+;", re.I | re.S)


def _parse_ddl_blocks(schema_path: str) -> dict[str, str]:
    """Maps table name -> its CREATE TABLE statement from the shared DDL script."""
    text = Path(schema_path).read_text(encoding="utf-8")
    blocks: dict[str, str] = {}
    for block in DDL_BLOCK_RE.findall(text):
        m = re.search(r'CREATE TABLE\s+"?(\w+)"?', block, re.I)
        if not m:
            continue
        blocks[m.group(1)] = block
    return blocks


def _clean_chunk(df: pd.DataFrame, col_types: dict[str, str]) -> pd.DataFrame:
    """Strip whitespace, turn '' into NULL, coerce numeric-looking types."""
    df.columns = [str(c).strip() for c in df.columns]
    for col in df.columns:
        if df[col].dtype == object:
            df[col] = df[col].map(lambda v: v.strip() if isinstance(v, str) else v)
        df[col] = df[col].replace("", None)
        if NUMERIC_TYPE_RE.search(col_types.get(col, "") or ""):
            df[col] = pd.to_numeric(df[col], errors="coerce").astype(object).where(df[col].notna(), None)
    return df.drop_duplicates().reset_index(drop=True)


def _insert_rows(cursor, table: str, columns: list[str], rows) -> int:
    """Batched idempotent insert (INSERT OR REPLACE keyed on the table PK)."""
    cols_sql = ", ".join(f'"{c}"' for c in columns)
    marks = ", ".join("?" for _ in columns)
    cursor.executemany(
        f'INSERT OR REPLACE INTO "{table}" ({cols_sql}) VALUES ({marks})', rows
    )
    return len(rows)


def seed_sqlite(
    db_path: str,
    dataset_dir: str,
    schema_path: str,
    reset: bool,
    limit: int | None = None,
) -> dict[str, int]:
    """Bulk-load the CSV datasets into a SQLite DB. Returns table -> row count."""
    os.makedirs(os.path.dirname(db_path) or ".", exist_ok=True)
    blocks = _parse_ddl_blocks(schema_path)
    if not blocks:
        raise FileNotFoundError(f"No CREATE TABLE statements in {schema_path}")

    conn = sqlite3.connect(db_path)
    counts: dict[str, int] = {}
    try:
        if reset:
            for table in blocks:
                conn.execute(f'DROP TABLE IF EXISTS "{table}"')
        for table, ddl in blocks.items():
            csv_path = Path(dataset_dir) / f"{table}.csv"
            if not csv_path.exists() and not reset:
                continue  # leave untouched when the CSV is absent and no --reset was requested
            if csv_path.exists() or reset:
                conn.execute(f'DROP TABLE IF EXISTS "{table}"')
                conn.executescript(ddl + ";")
            if not csv_path.exists():
                counts[table] = 0
                continue
            col_types = {
                r[1]: r[2]
                for r in conn.execute(f'PRAGMA table_info("{table}")').fetchall()
            }
            df = _clean_chunk(pd.read_csv(csv_path, dtype=str, keep_default_na=False), col_types)
            if limit is not None:
                df = df.head(int(limit))
            connector_cols = [c for c in col_types if c in df.columns]
            missing = set(col_types) - set(connector_cols)
            if missing:
                print(f"  ! {table}: missing columns {sorted(missing)} in {csv_path.name}")
            if set(df.columns) - set(col_types):
                print(f"  ! {table}: CSV-only columns dropped {sorted(set(df.columns) - set(col_types))}")
            rows = [tuple(r) for r in df[connector_cols].to_numpy()]
            with conn:
                counts[table] = _insert_rows(conn.cursor(), table, connector_cols, rows)
    finally:
        conn.close()
    return counts


def _ddl_for_postgres(ddl: str) -> str:
    """Small SQLite->PostgreSQL DDL translation (types + IF NOT EXISTS)."""
    ddl = re.sub(r"\bTIMESTAMP\b", "TIMESTAMP", ddl, flags=re.I)
    ddl = re.sub(r"\bVARCHAR\(\d+\)", lambda m: m.group(0), ddl, flags=re.I)
    return ddl.replace("CREATE TABLE ", "CREATE TABLE IF NOT EXISTS ", 1)


def _ddl_for_mysql(ddl: str) -> str:
    """Small SQLite->MySQL DDL translation (types + IF NOT EXISTS)."""
    ddl = re.sub(r"\bTIMESTAMP\b", "DATETIME", ddl, flags=re.I)
    return ddl.replace("CREATE TABLE ", "CREATE TABLE IF NOT EXISTS ", 1)


def seed_postgres(
    dsn: str,
    dataset_dir: str,
    schema_path: str,
    limit: int | None = None,
):
    """Optional Postgres seeding (needs psycopg2). Driven by POSTGRES_DSN env."""
    import psycopg2  # lazy: optional dependency
    from psycopg2 import extras as pg_extras  # lazy: optional dependency

    blocks = _parse_ddl_blocks(schema_path)
    with psycopg2.connect(dsn) as conn:  # autocommit DDL via conn.commit()
        cur = conn.cursor()
        for table, ddl in blocks.items():
            cur.execute(f'DROP TABLE IF EXISTS "{table}" CASCADE')
        for table, ddl in blocks.items():
            cur.execute(_ddl_for_postgres(ddl))
            col_types = {}
            cur.execute(
                "SELECT column_name, data_type FROM information_schema.columns "
                "WHERE table_name=%s ORDER BY ordinal_position",
                (table,),
            )
            col_types = {r[0]: r[1] for r in cur.fetchall()}
            csv_path = Path(dataset_dir) / f"{table}.csv"
            if not csv_path.exists():
                continue
            df = _clean_chunk(pd.read_csv(csv_path, dtype=str, keep_default_na=False), col_types)
            if limit is not None:
                df = df.head(int(limit))
            cols_sql = ", ".join(f'"{c}"' for c in df.columns)
            marks = ", ".join(["%s"] * len(df.columns))
            pg_extras.execute_values(
                cur,
                f'INSERT INTO "{table}" ({cols_sql}) VALUES %s',
                df.itertuples(index=False, name=None),
                page_size=1000,
            )
            print(f"  postgres.{table}: {len(df)} rows")
        conn.commit()


def seed_mysql(
    dsn: str,
    dataset_dir: str,
    schema_path: str,
    limit: int | None = None,
):
    """Optional MySQL seeding (needs pymysql). Driven by MYSQL_DSN env."""
    import pymysql  # lazy: optional dependency
    from urllib.parse import urlparse

    parsed = urlparse(dsn)
    conn = pymysql.connect(
        host=parsed.hostname or "127.0.0.1",
        port=parsed.port or 3306,
        user=parsed.username,
        password=parsed.password or "",
        database=parsed.path.lstrip("/") or "saffron_bank",
        charset="utf8mb4",
    )
    try:
        blocks = _parse_ddl_blocks(schema_path)
        with conn.cursor() as cur:
            for table, ddl in blocks.items():
                cur.execute(f"DROP TABLE IF EXISTS `{table}`")
                cur.execute(_ddl_for_mysql(ddl))
                cur.execute(f"SHOW COLUMNS FROM `{table}`")
                col_types = {r[0]: r[1] for r in cur.fetchall()}
                csv_path = Path(dataset_dir) / f"{table}.csv"
                if not csv_path.exists():
                    continue
                df = _clean_chunk(pd.read_csv(csv_path, dtype=str, keep_default_na=False), col_types)
                if limit is not None:
                    df = df.head(int(limit))
                cols_sql = ", ".join(f"`{c}`" for c in df.columns)
                marks = ", ".join(["%s"] * len(df.columns))
                cur.executemany(
                    f"INSERT INTO `{table}` ({cols_sql}) VALUES ({marks})",
                    df.itertuples(index=False, name=None),
                )
                print(f"  mysql.{table}: {len(df)} rows")
        conn.commit()
    finally:
        conn.close()


def seed_from_dataset(
    db_path: str = DEFAULT_DB_PATH,
    dataset_dir: str = DEFAULT_DATASET_DIR,
    schema_path: str = DEFAULT_SCHEMA_PATH,
    reset: bool = False,
    limit: int | None = None,
) -> dict[str, int]:
    """Load the real csv datasets into the primary SQLite DB (plus optional backends)."""
    counts = seed_sqlite(
        db_path=db_path,
        dataset_dir=dataset_dir,
        schema_path=schema_path,
        reset=reset,
        limit=limit,
    )
    pg_dsn = os.environ.get(POSTGRES_DSN_ENV, "")
    if pg_dsn:
        seed_postgres(pg_dsn, dataset_dir, schema_path, limit=limit)
    mysql_dsn = os.environ.get(MYSQL_DSN_ENV, "")
    if mysql_dsn:
        seed_mysql(mysql_dsn, dataset_dir, schema_path, limit=limit)
    return counts


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        description="Seed the masking demo DB. Prefers real CSV datasets; falls back to synthetic data."
    )
    ap.add_argument("path", nargs="?", default=None,
                    help="Target SQLite file (default: $BANK_DB or data/bank.db)")
    ap.add_argument("--dataset-path", "--dataset-dir", dest="dataset_dir", default=DEFAULT_DATASET_DIR,
                    help="Folder with the CSV datasets (default: $DATASET_DIR or data/csv)")
    ap.add_argument("--reset", action="store_true",
                    help="Drop & recreate each table before loading (fresh copy).")
    ap.add_argument("--limit", type=int, default=None,
                    help="Load only the first N rows of every CSV (quick demos).")
    ap.add_argument("--fallback-sample", action="store_true",
                    help="Use the built-in synthetic seed() when no CSVs are found.")
    args = ap.parse_args(argv)

    db_path = args.path or DEFAULT_DB_PATH
    csv_files = sorted(Path(args.dataset_dir).glob("*.csv")) if Path(args.dataset_dir).exists() else []
    if not csv_files:
        if args.fallback_sample:
            seed(db_path)
            print(f"No CSV datasets in {args.dataset_dir!r}; seeded synthetic sample at {db_path}")
            return 0
        print(f"No CSV datasets found in {args.dataset_dir!r} "
              f"(pass --dataset-path or use --fallback-sample).")
        return 1

    counts = seed_from_dataset(
        db_path=db_path,
        dataset_dir=args.dataset_dir,
        reset=args.reset,
        limit=args.limit,
    )
    total = sum(counts.values())
    print(f"Seeded {db_path} from {args.dataset_dir} ({total:,} rows):")
    for table, count in sorted(counts.items()):
        print(f"  {table:<26}{count:>9,}")
    if not args.reset:
        print("(add --reset to drop & recreate tables fresh)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
