"""db_apply_change – execute a DDL or DML statement against a SQL Server database.

Runs any SQL statement (CREATE, ALTER, DROP, INSERT, UPDATE, DELETE, EXEC, …)
inside a single connection and commits automatically.  Use it to apply schema
changes, seed data, or call stored procedures from the agent.

Connection strings in both ADO.NET and pyodbc/ODBC formats are accepted
(see ``db_read_metadata`` for the full normalisation rules).
"""

from __future__ import annotations

import re

from agent.core.registry import ToolError, tool

# ---------------------------------------------------------------------------
# Re-use the same connection-string normaliser as db_read_metadata
# ---------------------------------------------------------------------------

_BOOL_TRUE  = {"true", "yes", "1"}

_ADO_MAP = {
    "server":                 "Server",
    "initial catalog":        "Database",
    "user id":                "Uid",
    "password":               "Pwd",
    "encrypt":                "Encrypt",
    "trustservercertificate": "TrustServerCertificate",
    "connection timeout":     "Connection Timeout",
    "persist security info":  None,
}


def _normalise_conn_str(raw: str) -> str:
    raw = raw.strip().rstrip(";")
    if re.search(r"Driver\s*=", raw, re.IGNORECASE):
        return raw
    pairs: dict[str, str] = {}
    for part in re.split(r";", raw):
        part = part.strip()
        if not part:
            continue
        idx = part.index("=")
        pairs[part[:idx].strip().lower()] = part[idx + 1:].strip()

    odbc_parts = ["Driver={ODBC Driver 18 for SQL Server}"]
    for k, v in pairs.items():
        odbc_key = _ADO_MAP.get(k)
        if odbc_key is None:
            continue
        vl = v.lower()
        if odbc_key in ("Encrypt", "TrustServerCertificate"):
            v = "yes" if vl in _BOOL_TRUE else "no"
        odbc_parts.append(f"{odbc_key}={v}")
    return ";".join(odbc_parts) + ";"


# ---------------------------------------------------------------------------
# Tool
# ---------------------------------------------------------------------------


@tool
def db_apply_change(connection_string: str, sql: str) -> str:
    """Execute a DDL or DML SQL statement against a SQL Server / Azure SQL database.

    The statement is executed in autocommit mode so DDL (CREATE / ALTER / DROP)
    works without explicit transaction management.  For DML (INSERT / UPDATE /
    DELETE) the change is committed automatically.

    Returns a short summary of rows affected (or "statement executed" for DDL).

    Args:
        connection_string: ADO.NET or pyodbc ODBC connection string for the target database.
        sql: The SQL statement to execute (single statement; use GO-free T-SQL).
    """
    try:
        import pyodbc  # type: ignore
    except ImportError:
        raise ToolError("pyodbc is not installed. Run: pip install pyodbc")

    if not sql or not sql.strip():
        raise ToolError("'sql' must not be empty.")

    odbc_str = _normalise_conn_str(connection_string)
    try:
        conn = pyodbc.connect(odbc_str, timeout=35, autocommit=True)
    except pyodbc.Error as exc:
        raise ToolError(f"Cannot connect to database: {exc}")

    conn.add_output_converter(-16, lambda b: b.decode("utf-16-le") if b else None)

    try:
        cur = conn.cursor()
        cur.execute(sql.strip())
        try:
            rowcount = cur.rowcount
        except pyodbc.Error:
            rowcount = -1
    except pyodbc.Error as exc:
        raise ToolError(f"SQL execution failed: {exc}\n\nStatement:\n{sql[:500]}")
    finally:
        conn.close()

    if rowcount == -1 or rowcount is None:
        return f"Statement executed successfully (no row count available).\n\nSQL:\n{sql.strip()[:300]}"
    if rowcount < 0:
        return f"Statement executed successfully.\n\nSQL:\n{sql.strip()[:300]}"
    return f"Statement executed successfully. Rows affected: {rowcount}\n\nSQL:\n{sql.strip()[:300]}"
