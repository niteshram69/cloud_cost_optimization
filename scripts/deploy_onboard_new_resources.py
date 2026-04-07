from __future__ import annotations

import os
import re
from pathlib import Path

from sqlalchemy import create_engine


DEFAULT_DB_URL = "mysql+pymysql://root@localhost/cloudteck"
PROCEDURE_SQL_PATH = Path("backend/docs/sql/sp_onboard_new_resources.sql")


def _load_procedure_statements(sql_path: Path) -> list[str]:
    """
    Load the procedure DDL and convert mysql-client DELIMITER blocks into executable statements.
    """
    raw = sql_path.read_text(encoding="utf-8")
    stripped = re.sub(r"(?im)^DELIMITER\s+\S+\s*$", "", raw)
    statements = [chunk.strip() for chunk in stripped.split("$$") if chunk.strip()]
    return statements


def deploy_and_run_fix() -> None:
    db_url = os.getenv("DB_CONNECTION_STR", DEFAULT_DB_URL)
    engine = create_engine(db_url)

    if not PROCEDURE_SQL_PATH.exists():
        raise FileNotFoundError(f"Procedure SQL file not found: {PROCEDURE_SQL_PATH}")

    statements = _load_procedure_statements(PROCEDURE_SQL_PATH)
    if not statements:
        raise RuntimeError("No SQL statements parsed from procedure file.")

    print(f"Deploying procedure from: {PROCEDURE_SQL_PATH}")
    print(f"Target DB: {db_url}")

    conn = engine.raw_connection()
    try:
        with conn.cursor() as cursor:
            for stmt in statements:
                cursor.execute(stmt)
            print("Procedure deployed.")

            cursor.execute("CALL sp_onboard_new_resources();")
            row = cursor.fetchone()
            conn.commit()
    finally:
        conn.close()

    if row is None:
        print("Procedure executed, but returned no summary row.")
        return

    # Procedure returns: status, resources_onboarded, history_rows_generated
    status = row[0] if len(row) > 0 else "UNKNOWN"
    resources_onboarded = int(row[1]) if len(row) > 1 and row[1] is not None else 0
    history_rows_generated = int(row[2]) if len(row) > 2 and row[2] is not None else 0

    print(f"Status: {status}")
    print(f"Resources onboarded: {resources_onboarded}")
    print(f"History rows generated: {history_rows_generated}")


if __name__ == "__main__":
    deploy_and_run_fix()
