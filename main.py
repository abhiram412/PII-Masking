"""Main unified entrypoint for Smart Data Masking System (BFSI Problem Statement 1).
Provides quick launch options for:
- Streamlit interactive dashboard
- Automated PII scanner
- Multi-role query evaluation
- Test suite execution
"""
import os
import subprocess
import sys


def print_banner():
    print("=" * 70)
    print("  🛡️  SMART DATA MASKING SYSTEM (BFSI - Problem Statement 1) 🛡️")
    print("      Dynamic Query-Time PII Masking | Multi-Backend | QRNG | PQC")
    print("=" * 70)


def run_command(cmd_list):
    print(f"\n[Executing]: {' '.join(cmd_list)}\n")
    return subprocess.run(cmd_list).returncode


def main():
    print_banner()
    if len(sys.argv) > 1:
        arg = sys.argv[1].lower()
        if arg == "dashboard":
            return run_command([sys.executable, "-m", "streamlit", "run", "streamlit_app.py"])
        elif arg == "scan":
            return run_command([sys.executable, "cli.py", "scan"])
        elif arg == "test":
            return run_command([sys.executable, "-m", "unittest", "discover", "tests"])
        elif arg == "seed":
            return run_command([sys.executable, "seed.py", "--reset"])
        elif arg == "compare":
            sql = sys.argv[2] if len(sys.argv) > 2 else "SELECT cust_nm, mob_no, emailid FROM customers LIMIT 3"
            return run_command([sys.executable, "cli.py", "compare", sql])

    print("Options:")
    print("  1. Launch Streamlit Dashboard  (streamlit run streamlit_app.py)")
    print("  2. Run Automated PII Scanner   (python cli.py scan)")
    print("  3. Run Multi-Role SQL Compare  (python cli.py compare '<query>')")
    print("  4. Run Test Suite (25 Tests)   (python -m unittest discover tests)")
    print("  5. Re-seed Database from CSVs  (python seed.py --reset)")
    print("  q. Exit")
    print("-" * 70)
    choice = input("Select an option [1-5/q]: ").strip()

    if choice == "1":
        return run_command([sys.executable, "-m", "streamlit", "run", "streamlit_app.py"])
    elif choice == "2":
        return run_command([sys.executable, "cli.py", "scan"])
    elif choice == "3":
        default_query = "SELECT cust_nm, mob_no, emailid FROM customers LIMIT 3"
        query = input(f"Enter SQL [{default_query}]: ").strip() or default_query
        return run_command([sys.executable, "cli.py", "compare", query])
    elif choice == "4":
        return run_command([sys.executable, "-m", "unittest", "discover", "tests"])
    elif choice == "5":
        return run_command([sys.executable, "seed.py", "--reset"])
    elif choice.lower() in ("q", "quit", "exit"):
        print("Goodbye!")
        return 0
    else:
        print("Invalid option.")
        return 1


if __name__ == "__main__":
    sys.exit(main())
