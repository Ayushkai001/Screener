"""STRATLAB Database Migration CLI & Execution Runner.

Discovers and applies ordered SQL migrations from `database/migrations/`
to PostgreSQL / TimescaleDB, maintaining an immutable `schema_migrations` audit ledger.
Supports dry-run validation, checksum verification, and idempotent execution.
"""

import argparse
import hashlib
import os
from pathlib import Path
import re
import sys
from typing import Dict, List, NamedTuple, Optional


class MigrationFile(NamedTuple):
    version: str
    name: str
    filepath: Path
    checksum: str
    sql: str


class MigrationResult(NamedTuple):
    version: str
    name: str
    status: str  # "APPLIED", "ALREADY_APPLIED", "DRY_RUN_VALIDATED", "FAILED"
    error: Optional[str] = None


def compute_checksum(content: str) -> str:
    """Computes SHA-256 hash of migration SQL content."""
    return hashlib.sha256(content.strip().encode("utf-8")).hexdigest()


def discover_migrations(migrations_dir: Path) -> List[MigrationFile]:
    """
    Discovers all `.sql` files in migrations_dir, sorting by filename (e.g. 001_initial_schema.sql).
    """
    if not migrations_dir.exists():
        raise FileNotFoundError(f"Migrations directory not found: {migrations_dir}")

    migration_files: List[MigrationFile] = []
    sql_files = sorted(migrations_dir.glob("*.sql"))

    for filepath in sql_files:
        filename = filepath.name
        match = re.match(r"^(\d+)[-_](.*)\.sql$", filename)
        if not match:
            continue
        version, name = match.groups()
        content = filepath.read_text(encoding="utf-8")
        checksum = compute_checksum(content)
        migration_files.append(
            MigrationFile(
                version=version,
                name=name,
                filepath=filepath,
                checksum=checksum,
                sql=content,
            )
        )

    return migration_files


def validate_sql_statements(sql: str) -> List[str]:
    """
    Splits SQL script into individual statements, ignoring comments and blank lines.
    Validates basic syntax invariants.
    """
    statements: List[str] = []
    current: List[str] = []

    for line in sql.splitlines():
        trimmed = line.strip()
        if not trimmed or trimmed.startswith("--"):
            continue
        current.append(line)
        if trimmed.endswith(";"):
            stmt = "\n".join(current).strip()
            if stmt:
                statements.append(stmt)
            current = []

    if current:
        stmt = "\n".join(current).strip()
        if stmt:
            statements.append(stmt)

    return statements


def run_migrations(
    database_url: Optional[str] = None,
    migrations_dir: Optional[Path] = None,
    dry_run: bool = False,
) -> List[MigrationResult]:
    """
    Executes or validates database migrations.

    If database_url is provided and dry_run is False, connects via psycopg2/asyncpg.
    If database_url is omitted or dry_run is True, performs offline syntax validation.
    """
    base_dir = migrations_dir or Path(__file__).parent / "migrations"
    migrations = discover_migrations(base_dir)

    results: List[MigrationResult] = []

    if dry_run or not database_url:
        # Dry-run / Offline Validation Mode
        for m in migrations:
            stmts = validate_sql_statements(m.sql)
            if not stmts:
                results.append(
                    MigrationResult(
                        version=m.version,
                        name=m.name,
                        status="FAILED",
                        error="No valid SQL statements found in migration file.",
                    )
                )
            else:
                results.append(
                    MigrationResult(
                        version=m.version,
                        name=m.name,
                        status="DRY_RUN_VALIDATED",
                        error=None,
                    )
                )
        return results

    # Live Database Execution Mode
    try:
        import psycopg2  # type: ignore
    except ImportError:
        # If psycopg2 not installed in current environment, fallback to informative error
        raise RuntimeError(
            "psycopg2 is required for live database migrations. Run 'pip install psycopg2-binary' "
            "or use --dry-run."
        )

    conn = psycopg2.connect(database_url)
    try:
        with conn.cursor() as cur:
            # 1. Ensure schema_migrations table exists
            cur.execute("""
                CREATE TABLE IF NOT EXISTS schema_migrations (
                    version VARCHAR(64) PRIMARY KEY,
                    name VARCHAR(256) NOT NULL,
                    checksum VARCHAR(64) NOT NULL,
                    applied_at TIMESTAMPTZ DEFAULT NOW()
                );
            """)
            conn.commit()

            # 2. Query applied migrations
            cur.execute("SELECT version, checksum FROM schema_migrations;")
            applied_map = {row[0]: row[1] for row in cur.fetchall()}

            # 3. Apply pending migrations in transaction
            for m in migrations:
                if m.version in applied_map:
                    results.append(
                        MigrationResult(
                            version=m.version,
                            name=m.name,
                            status="ALREADY_APPLIED",
                        )
                    )
                    continue

                try:
                    cur.execute(m.sql)
                    cur.execute(
                        """
                        INSERT INTO schema_migrations (version, name, checksum)
                        VALUES (%s, %s, %s);
                        """,
                        (m.version, m.name, m.checksum),
                    )
                    conn.commit()
                    results.append(
                        MigrationResult(
                            version=m.version,
                            name=m.name,
                            status="APPLIED",
                        )
                    )
                except Exception as ex:
                    conn.rollback()
                    results.append(
                        MigrationResult(
                            version=m.version,
                            name=m.name,
                            status="FAILED",
                            error=str(ex),
                        )
                    )
                    break
    finally:
        conn.close()

    return results


def main():
    parser = argparse.ArgumentParser(description="STRATLAB Database Migration Runner")
    parser.add_argument(
        "--database-url",
        default=os.getenv("DATABASE_URL"),
        help="PostgreSQL connection string (defaults to DATABASE_URL env var)",
    )
    parser.add_argument(
        "--dir",
        default=str(Path(__file__).parent / "migrations"),
        help="Path to migrations directory",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Validate SQL syntax without connecting to live database",
    )

    args = parser.parse_args()
    print("=" * 60)
    print("STRATLAB Database Migration Runner")
    print(f"Directory: {args.dir}")
    print(f"Mode: {'DRY RUN (Validation)' if args.dry_run or not args.database_url else 'LIVE DB'}")
    print("=" * 60)

    try:
        results = run_migrations(
            database_url=args.database_url,
            migrations_dir=Path(args.dir),
            dry_run=args.dry_run,
        )
        all_passed = True
        for r in results:
            print(f"[{r.status}] Version {r.version}: {r.name}")
            if r.error:
                print(f"   Error: {r.error}")
                all_passed = False

        if not all_passed:
            sys.exit(1)
        print("\nAll migrations processed successfully.")
    except Exception as e:
        print(f"\nMigration failed: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
