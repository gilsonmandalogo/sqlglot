import unittest

from sqlglot import ColumnPolicy, exp


class TestColumnPolicy(unittest.TestCase):
    def test_construct_from_list_and_mapping(self):
        from_list = ColumnPolicy(["users.email", "orders.ssn"])
        from_map = ColumnPolicy({"users.email": True, "orders.ssn": "pii"})

        self.assertEqual(len(from_list), 2)
        self.assertEqual(len(from_map), 2)
        self.assertTrue(from_list.covers("users.email"))
        self.assertTrue(from_map.covers("orders.ssn"))
        self.assertFalse(from_list.covers("users.name"))

    def test_mapping_retains_actions(self):
        policy = ColumnPolicy(
            {
                "users.email": "MASK",
                "users.ssn": " Drop ",
                "users.notes": "audit",
                "users.flag": True,
                "users.skip": None,
                "users.off": False,
            }
        )

        self.assertTrue(policy.covers("users.email"))
        self.assertTrue(policy.covers("users.ssn"))
        self.assertTrue(policy.covers("users.notes"))
        self.assertTrue(policy.covers("users.flag"))
        self.assertTrue(policy.covers("users.skip"))
        self.assertTrue(policy.covers("users.off"))

        self.assertEqual(policy.action("users.email"), "mask")
        self.assertEqual(policy.action("users.ssn"), "drop")
        self.assertEqual(policy.action("users.notes"), "audit")
        self.assertEqual(policy.action("users.flag"), "true")
        self.assertIsNone(policy.action("users.skip"))
        self.assertIsNone(policy.action("users.off"))
        self.assertIsNone(policy.action("users.name"))

        # Right-aligned matching matches covers()
        self.assertEqual(policy.action("catalog.db.users.email"), "mask")

        self.assertEqual(policy.entries_with_action("mask"), [("users", "email")])
        self.assertEqual(sorted(policy.entries_with_action("drop")), [("users", "ssn")])

    def test_list_entries_have_no_action(self):
        policy = ColumnPolicy(["users.email", "orders.ssn"])

        self.assertTrue(policy.covers("users.email"))
        self.assertIsNone(policy.action("users.email"))
        self.assertIsNone(policy.action("orders.ssn"))
        self.assertEqual(policy.entries_with_action("drop"), [])

    def test_add_and_contains(self):
        policy = ColumnPolicy()
        policy.add("users.email").add("users.phone")

        self.assertIn("users.email", policy)
        self.assertIn("users.phone", policy)
        self.assertNotIn("users.name", policy)
        self.assertNotIn(123, policy)

    def test_add_requires_table_and_column(self):
        policy = ColumnPolicy()
        with self.assertRaises(ValueError):
            policy.add("email")

    def test_covers_table_column_args(self):
        policy = ColumnPolicy(["users.email"])

        self.assertTrue(policy.covers("users", "email"))
        self.assertTrue(policy.covers(table="users", column="email"))
        self.assertTrue(policy.covers(exp.table_("users"), exp.column("email")))
        self.assertFalse(policy.covers("users", "name"))
        self.assertFalse(policy.covers("accounts", "email"))

    def test_unrelated_table_not_covered(self):
        policy = ColumnPolicy(["users.email"])

        self.assertFalse(policy.covers("other.email"))
        self.assertFalse(policy.covers("accounts.email"))
        self.assertFalse(policy.covers("email"))

    def test_catalog_db_table_col_vs_table_col(self):
        fully_qualified = ColumnPolicy(["catalog.db.users.email"])
        short = ColumnPolicy(["users.email"])

        self.assertTrue(fully_qualified.covers("users.email"))
        self.assertTrue(fully_qualified.covers("db.users.email"))
        self.assertTrue(fully_qualified.covers("catalog.db.users.email"))

        self.assertTrue(short.covers("catalog.db.users.email"))
        self.assertTrue(short.covers("db.users.email"))
        self.assertTrue(short.covers("users.email"))

        self.assertFalse(fully_qualified.covers("other_catalog.db.users.email"))
        self.assertFalse(short.covers("other.email"))

    def test_postgres_case_folding(self):
        policy = ColumnPolicy(["Users.Email"], dialect="postgres")

        self.assertTrue(policy.covers("users.email", dialect="postgres"))
        self.assertTrue(policy.covers("USERS.EMAIL", dialect="postgres"))
        self.assertTrue(policy.covers("Users.Email", dialect="postgres"))

        # Quoted identifiers keep their case under Postgres rules
        policy_quoted = ColumnPolicy(['"Users"."Email"'], dialect="postgres")
        self.assertTrue(policy_quoted.covers('"Users"."Email"', dialect="postgres"))
        self.assertFalse(policy_quoted.covers("users.email", dialect="postgres"))
        self.assertFalse(policy_quoted.covers("Users.Email", dialect="postgres"))

    def test_snowflake_case_folding(self):
        policy = ColumnPolicy(["Users.Email"], dialect="snowflake")

        self.assertTrue(policy.covers("users.email", dialect="snowflake"))
        self.assertTrue(policy.covers("USERS.EMAIL", dialect="snowflake"))
        self.assertTrue(policy.covers("Users.Email", dialect="snowflake"))

        policy_quoted = ColumnPolicy(['users."Email"'], dialect="snowflake")
        self.assertTrue(policy_quoted.covers('USERS."Email"', dialect="snowflake"))
        self.assertFalse(policy_quoted.covers("users.email", dialect="snowflake"))
        self.assertFalse(policy_quoted.covers("USERS.EMAIL", dialect="snowflake"))

    def test_dialect_mismatch_folding(self):
        # Same textual entry normalizes differently per dialect
        pg = ColumnPolicy(["Users.Email"], dialect="postgres")
        sf = ColumnPolicy(["Users.Email"], dialect="snowflake")

        self.assertEqual(set(pg), {("users", "email")})
        self.assertEqual(set(sf), {("USERS", "EMAIL")})

    def test_partially_qualified_table_arg(self):
        policy = ColumnPolicy(["db.users.email"])

        self.assertTrue(policy.covers("db.users", "email"))
        self.assertTrue(policy.covers(table="users", column="email"))
        self.assertFalse(policy.covers("other_db.users", "email"))
