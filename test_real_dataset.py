import os
import tempfile
import unittest

from masking import MaskingEngine, QueryRejected, SQLiteBackend
from seed import seed_from_dataset


class RealDatasetTests(unittest.TestCase):
    """Runs against the Saffron Bank dataset loaded from data/csv (skips if missing)."""

    @classmethod
    def setUpClass(cls):
        csv_dir = "data/csv"
        if not (os.path.isdir(csv_dir) and os.path.isfile(os.path.join(csv_dir, "customers.csv"))):
            raise unittest.SkipTest("data/csv Saffron Bank dataset not present")
        cls.tmp = tempfile.mkdtemp()
        cls.db = os.path.join(cls.tmp, "bank.db")
        counts = seed_from_dataset(dataset_dir=csv_dir, db_path=cls.db)
        if not counts:
            raise unittest.SkipTest("dataset seeding produced no rows")
        cls.engine = MaskingEngine(
            SQLiteBackend(cls.db),
            catalog_path=os.path.join(cls.tmp, "cat.json"),
            audit_path=os.path.join(cls.tmp, "audit.log"),
            secret="real-dataset-secret",
        )
        cls.engine.scan()

    def one(self, role, sql):
        r = self.engine.query(role, sql)
        return dict(zip(r.columns, r.rows[0]))

    def test_expected_sensitivity_tags(self):
        tags = {t.key: t.tag for t in self.engine.tags if t.tag != "NON_SENSITIVE"}
        self.assertEqual(tags["customers.cust_nm"], "PII_MEDIUM")
        self.assertEqual(tags["customers.mob_no"], "PII_MEDIUM")
        self.assertEqual(tags["customers.emailid"], "PII_MEDIUM")
        self.assertEqual(tags["accounts.account_no"], "FINANCIAL_CONFIDENTIAL")
        self.assertEqual(tags["accounts.ifsc"], "FINANCIAL_CONFIDENTIAL")
        self.assertEqual(tags["cards.CARD_NO"], "PII_HIGH")
        self.assertEqual(tags["kyc_records.pan_no"], "PII_HIGH")
        self.assertEqual(tags["kyc_records.aadhaar_no"], "PII_HIGH")
        self.assertEqual(tags["international_customers.ssn"], "PII_HIGH")
        self.assertEqual(tags["transactions.amount_inr"], "FINANCIAL_CONFIDENTIAL")
        self.assertEqual(tags["loan_applications.col_7"], "PII_HIGH")  # PAN-shaped by content
        # decoys must not be tagged as credit-card
        self.assertNotIn("cards.card_ref", tags)
        self.assertNotIn("transactions.rrn", tags)

    def test_role_based_masking_support(self):
        row = self.one("support", "SELECT cust_nm, mob_no, emailid, addr_line1 FROM customers LIMIT 1")
        # phone partial mask keeps only the last 4 digits
        self.assertGreaterEqual(len([c for c in row["mob_no"] if c.isdigit()]), 4)
        self.assertGreaterEqual(row["mob_no"].count("X"), 6, row["mob_no"])
        # email partial keeps only the first letter of the local part
        self.assertEqual(row["emailid"].split("@")[0], row["emailid"][0] + "***")

    def test_role_based_masking_analyst(self):
        row = self.one("analyst", "SELECT cust_nm, mob_no, emailid, addr_line1 FROM customers LIMIT 1")
        for field in ("cust_nm", "mob_no", "emailid", "addr_line1"):
            self.assertEqual(row[field], "[REDACTED]", f"{field} should be redacted for analyst")

    def test_financial_confidential_stays_masked(self):
        row = self.one("support", "SELECT account_no, curr_bal FROM accounts LIMIT 1")
        self.assertTrue(any(ch == "X" for ch in str(row["account_no"])), row["account_no"])
        self.assertNotEqual(row["curr_bal"], "")

    def test_restricted_roles_block_pii_predicates(self):
        for role in ("support", "analyst"):
            with self.assertRaises(QueryRejected):
                self.engine.query(role, "SELECT customer_id FROM international_customers WHERE ssn LIKE '9%'")
            with self.assertRaises(QueryRejected):
                self.engine.query(role, "SELECT customer_id FROM international_customers ORDER BY ssn")

    def test_admin_sees_raw(self):
        row = self.one("admin", "SELECT cust_nm, emailid FROM customers LIMIT 1")
        self.assertFalse(row["cust_nm"].startswith("X"))
        self.assertNotIn("*", row["emailid"])

    def test_free_text_scrub_hides_embedded_pii(self):
        r = self.engine.query("support", "SELECT ticket_text FROM support_tickets LIMIT 300")
        leaked = [
            v
            for (v,) in r.rows
            if v and any(p in v.lower() for p in ("@gmail.com", "@hotmail.com", "@yahoo.com", "@saffronbank"))
        ]
        self.assertEqual(leaked, [], f"raw emails surfaced for support role: {leaked[:2]}")

    def test_masking_is_deterministic(self):
        sql = "SELECT cust_nm, emailid FROM customers LIMIT 5"
        r1 = self.engine.query("support", sql).rows
        r2 = self.engine.query("support", sql).rows
        self.assertEqual(r1, r2)


if __name__ == "__main__":
    unittest.main()
