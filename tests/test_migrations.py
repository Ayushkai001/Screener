"""STRATLAB Unit Tests: Database Migration Pipeline & SQL Validation."""

from pathlib import Path
import unittest

from database.migrate import (
    compute_checksum,
    discover_migrations,
    run_migrations,
    validate_sql_statements,
)


class TestDatabaseMigrations(unittest.TestCase):
    """Verifies migration discovery, checksum stability, and dry-run SQL parsing."""

    def setUp(self):
        self.migrations_dir = Path(__file__).parent.parent / "database" / "migrations"

    def test_discover_initial_migration(self):
        """Finds 001_initial_schema.sql with correct version and name."""
        migrations = discover_migrations(self.migrations_dir)
        self.assertGreaterEqual(len(migrations), 1)

        initial = migrations[0]
        self.assertEqual(initial.version, "001")
        self.assertEqual(initial.name, "initial_schema")
        self.assertTrue(len(initial.checksum) == 64)  # Valid SHA-256

    def test_sql_statement_parser(self):
        """Extracts valid SQL statements while skipping comments."""
        sample_sql = """
        -- Header comment
        CREATE TABLE test_table (id INT PRIMARY KEY);

        -- Another comment
        INSERT INTO test_table (id) VALUES (1);
        """
        stmts = validate_sql_statements(sample_sql)
        self.assertEqual(len(stmts), 2)
        self.assertTrue(stmts[0].startswith("CREATE TABLE"))
        self.assertTrue(stmts[1].startswith("INSERT INTO"))

    def test_dry_run_migration(self):
        """Executes dry-run validation on the actual 001_initial_schema.sql file."""
        results = run_migrations(
            database_url=None,
            migrations_dir=self.migrations_dir,
            dry_run=True,
        )
        self.assertGreaterEqual(len(results), 1)
        for r in results:
            self.assertEqual(r.status, "DRY_RUN_VALIDATED")
            self.assertIsNone(r.error)

    def test_checksum_determinism(self):
        """Identical content yields identical SHA-256 checksum."""
        text = "CREATE TABLE example (x INT);"
        hash1 = compute_checksum(text)
        hash2 = compute_checksum(text)
        self.assertEqual(hash1, hash2)
        self.assertNotEqual(hash1, compute_checksum(text + " -- modified"))


if __name__ == "__main__":
    unittest.main()
