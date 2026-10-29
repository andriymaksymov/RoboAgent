"""db_read_metadata – reads full database schema metadata from a SQL Server.

Connects via pyodbc and returns a JSON document describing every user object
found in the database: schemas, tables (with columns, PKs, FKs, identity,
indexes), views, stored procedures, and scalar / table-valued functions.

The connection string accepts the ADO.NET format used by Azure SQL:

    Server=tcp:<host>,1433;Initial Catalog=<db>;User ID=<u>;Password=<p>;
    Encrypt=True;TrustServerCertificate=False;Connection Timeout=30;

…or the standard pyodbc/ODBC format:

    Driver={ODBC Driver 18 for SQL Server};Server=tcp:<host>,1433;
    Database=<db>;Uid=<u>;Pwd=<p>;Encrypt=yes;TrustServerCertificate=no;

Both styles are transparently supported.
"""

from __future__ import annotations

import json
import re

from agent.core.registry import ToolError, tool

# ---------------------------------------------------------------------------
# Connection-string normaliser
# ---------------------------------------------------------------------------

_ADO_MAP = {
    "server":              "Server",
    "initial catalog":     "Database",
    "user id":             "Uid",
    "password":            "Pwd",
    "encrypt":             "Encrypt",
    "trustservercertificate": "TrustServerCertificate",
    "connection timeout":  "Connection Timeout",
    "persist security info": None,   # ignored
}

_BOOL_TRUE  = {"true", "yes", "1"}
_BOOL_FALSE = {"false", "no", "0"}


def _normalise_conn_str(raw: str) -> str:
    """Convert ADO.NET or ODBC connection strings to a pyodbc ODBC string."""
    raw = raw.strip().rstrip(";")

    # Already an ODBC string?
    if re.search(r"Driver\s*=", raw, re.IGNORECASE):
        return raw

    # Parse key=value pairs (values may contain '=')
    pairs: dict[str, str] = {}
    for part in re.split(r";", raw):
        part = part.strip()
        if not part:
            continue
        idx = part.index("=")
        k = part[:idx].strip().lower()
        v = part[idx + 1:].strip()
        pairs[k] = v

    odbc_parts = ["Driver={ODBC Driver 18 for SQL Server}"]
    for k, v in pairs.items():
        odbc_key = _ADO_MAP.get(k)
        if odbc_key is None:
            continue  # skip ignored keys
        # Normalise booleans
        vl = v.lower()
        if odbc_key == "Encrypt" or odbc_key == "TrustServerCertificate":
            v = "yes" if vl in _BOOL_TRUE else "no"
        odbc_parts.append(f"{odbc_key}={v}")

    return ";".join(odbc_parts) + ";"


# ---------------------------------------------------------------------------
# Type helpers
# ---------------------------------------------------------------------------

def _fmt_type(data_type: str, max_len, prec, scale, dt_prec) -> str:
    dt = data_type.lower()
    if dt in ("varchar", "nvarchar", "char", "nchar", "binary", "varbinary"):
        return f"{dt}({'MAX' if max_len == -1 else max_len})"
    if dt in ("decimal", "numeric"):
        return f"{dt}({prec},{scale})"
    if dt in ("datetime2", "time", "datetimeoffset"):
        return f"{dt}({dt_prec})"
    return dt


# ---------------------------------------------------------------------------
# Main tool
# ---------------------------------------------------------------------------

_SYS_SCHEMAS = frozenset({
    "sys", "guest", "INFORMATION_SCHEMA",
    "db_owner", "db_accessadmin", "db_securityadmin", "db_ddladmin",
    "db_backupoperator", "db_datareader", "db_datawriter",
    "db_denydatareader", "db_denydatawriter",
})


@tool
def db_read_metadata(connection_string: str) -> str:
    """Read full schema metadata from a SQL Server / Azure SQL database.

    Connects to the database and returns a JSON document with:
      - schemas          : list of user schema names
      - tables           : each table with columns, PKs, FKs, identity flags, and indexes
      - views            : each view with its CREATE definition
      - stored_procedures: each procedure with its CREATE definition
      - functions        : each function with its CREATE definition and sub-type

    Args:
        connection_string: ADO.NET or pyodbc ODBC connection string for the target database.
    """
    try:
        import pyodbc  # type: ignore
    except ImportError:
        raise ToolError("pyodbc is not installed. Run: pip install pyodbc")

    odbc_str = _normalise_conn_str(connection_string)
    try:
        conn = pyodbc.connect(odbc_str, timeout=35)
    except pyodbc.Error as exc:
        raise ToolError(f"Cannot connect to database: {exc}")

    # Handle XML columns (ODBC type -16)
    conn.add_output_converter(-16, lambda b: b.decode("utf-16-le") if b else None)
    cur = conn.cursor()

    result: dict = {
        "schemas": [],
        "tables": [],
        "views": [],
        "stored_procedures": [],
        "functions": [],
    }

    try:
        # ── Schemas ──────────────────────────────────────────────────────
        cur.execute("""
            SELECT s.name
            FROM sys.schemas s
            JOIN sys.database_principals p ON s.principal_id = p.principal_id
            WHERE p.type IN ('S','U','G','A')           -- SQL/Windows/Group/App role
              AND s.name NOT IN (
                  'sys','guest','INFORMATION_SCHEMA',
                  'db_owner','db_accessadmin','db_securityadmin','db_ddladmin',
                  'db_backupoperator','db_datareader','db_datawriter',
                  'db_denydatareader','db_denydatawriter')
            ORDER BY s.name
        """)
        result["schemas"] = [r[0] for r in cur.fetchall()]

        # ── Tables ───────────────────────────────────────────────────────
        cur.execute("""
            SELECT TABLE_SCHEMA, TABLE_NAME
            FROM INFORMATION_SCHEMA.TABLES
            WHERE TABLE_TYPE = 'BASE TABLE'
              AND TABLE_SCHEMA NOT IN (
                  'sys','INFORMATION_SCHEMA')
            ORDER BY TABLE_SCHEMA, TABLE_NAME
        """)
        raw_tables = cur.fetchall()

        # Columns
        cur.execute("""
            SELECT c.TABLE_SCHEMA, c.TABLE_NAME, c.COLUMN_NAME,
                   c.ORDINAL_POSITION, c.IS_NULLABLE, c.DATA_TYPE,
                   c.CHARACTER_MAXIMUM_LENGTH, c.NUMERIC_PRECISION, c.NUMERIC_SCALE,
                   CAST(c.COLUMN_DEFAULT AS NVARCHAR(500)) AS COLUMN_DEFAULT,
                   c.DATETIME_PRECISION
            FROM INFORMATION_SCHEMA.COLUMNS c
            JOIN INFORMATION_SCHEMA.TABLES t
                ON c.TABLE_SCHEMA = t.TABLE_SCHEMA AND c.TABLE_NAME = t.TABLE_NAME
            WHERE t.TABLE_TYPE = 'BASE TABLE'
              AND c.TABLE_SCHEMA NOT IN ('sys','INFORMATION_SCHEMA')
            ORDER BY c.TABLE_SCHEMA, c.TABLE_NAME, c.ORDINAL_POSITION
        """)
        col_rows = cur.fetchall()

        # Identity columns
        cur.execute("""
            SELECT s.name schema_name, t.name table_name, c.name col_name,
                   CAST(ic.seed_value AS BIGINT) seed,
                   CAST(ic.increment_value AS BIGINT) incr
            FROM sys.identity_columns ic
            JOIN sys.columns c  ON ic.object_id = c.object_id AND ic.column_id = c.column_id
            JOIN sys.tables  t  ON c.object_id = t.object_id
            JOIN sys.schemas s  ON t.schema_id = s.schema_id
        """)
        identity_map = {
            (r.schema_name, r.table_name, r.col_name): (r.seed, r.incr)
            for r in cur.fetchall()
        }

        # Primary keys
        cur.execute("""
            SELECT KU.TABLE_SCHEMA, KU.TABLE_NAME, KU.COLUMN_NAME,
                   KU.ORDINAL_POSITION, TC.CONSTRAINT_NAME
            FROM INFORMATION_SCHEMA.TABLE_CONSTRAINTS TC
            JOIN INFORMATION_SCHEMA.KEY_COLUMN_USAGE KU
                ON TC.CONSTRAINT_TYPE = 'PRIMARY KEY'
               AND TC.CONSTRAINT_NAME = KU.CONSTRAINT_NAME
            ORDER BY KU.TABLE_SCHEMA, KU.TABLE_NAME, KU.ORDINAL_POSITION
        """)
        pk_map: dict[tuple, dict] = {}
        for r in cur.fetchall():
            key = (r.TABLE_SCHEMA, r.TABLE_NAME)
            pk_map.setdefault(key, {"constraint_name": r.CONSTRAINT_NAME, "columns": []})
            pk_map[key]["columns"].append(r.COLUMN_NAME)

        # Foreign keys
        cur.execute("""
            SELECT
                s_p.name PS, tp.name PT, fk.name fk_name, cp.name PC,
                s_r.name RS, tr.name RT, cr.name RC
            FROM sys.foreign_keys           fk
            JOIN sys.foreign_key_columns    fkc ON fk.object_id = fkc.constraint_object_id
            JOIN sys.tables  tp ON fkc.parent_object_id      = tp.object_id
            JOIN sys.schemas s_p ON tp.schema_id             = s_p.schema_id
            JOIN sys.columns cp  ON fkc.parent_object_id     = cp.object_id
                                 AND fkc.parent_column_id    = cp.column_id
            JOIN sys.tables  tr  ON fkc.referenced_object_id = tr.object_id
            JOIN sys.schemas s_r ON tr.schema_id             = s_r.schema_id
            JOIN sys.columns cr  ON fkc.referenced_object_id = cr.object_id
                                 AND fkc.referenced_column_id = cr.column_id
            ORDER BY s_p.name, tp.name, fk.name
        """)
        fk_map: dict[tuple, list] = {}
        for r in cur.fetchall():
            key = (r.PS, r.PT)
            fk_map.setdefault(key, []).append({
                "constraint_name": r.fk_name,
                "column": r.PC,
                "ref_schema": r.RS,
                "ref_table": r.RT,
                "ref_column": r.RC,
            })

        # Non-PK indexes
        cur.execute("""
            SELECT s.name schema_name, t.name table_name, i.name index_name,
                   i.type_desc, i.is_unique,
                   STRING_AGG(c.name, ',') WITHIN GROUP (ORDER BY ic.key_ordinal) cols
            FROM sys.indexes i
            JOIN sys.tables       t  ON i.object_id = t.object_id
            JOIN sys.schemas      s  ON t.schema_id = s.schema_id
            JOIN sys.index_columns ic ON i.object_id = ic.object_id
                                     AND i.index_id  = ic.index_id
            JOIN sys.columns      c  ON ic.object_id = c.object_id
                                     AND ic.column_id = c.column_id
            WHERE i.is_primary_key = 0 AND i.type > 0
            GROUP BY s.name, t.name, i.name, i.type_desc, i.is_unique
            ORDER BY s.name, t.name, i.name
        """)
        idx_map: dict[tuple, list] = {}
        for r in cur.fetchall():
            key = (r.schema_name, r.table_name)
            idx_map.setdefault(key, []).append({
                "name":    r.index_name,
                "type":    r.type_desc,
                "unique":  bool(r.is_unique),
                "columns": r.cols.split(","),
            })

        # Assemble column lookup
        col_map: dict[tuple, list] = {}
        for c in col_rows:
            key = (c.TABLE_SCHEMA, c.TABLE_NAME)
            ikey = (c.TABLE_SCHEMA, c.TABLE_NAME, c.COLUMN_NAME)
            id_info = identity_map.get(ikey)
            col_map.setdefault(key, []).append({
                "name":     c.COLUMN_NAME,
                "ordinal":  c.ORDINAL_POSITION,
                "type":     _fmt_type(c.DATA_TYPE, c.CHARACTER_MAXIMUM_LENGTH,
                                      c.NUMERIC_PRECISION, c.NUMERIC_SCALE,
                                      c.DATETIME_PRECISION),
                "nullable": c.IS_NULLABLE.upper() == "YES",
                "default":  c.COLUMN_DEFAULT,
                "identity": {"seed": id_info[0], "increment": id_info[1]}
                             if id_info else None,
            })

        for row in raw_tables:
            key = (row.TABLE_SCHEMA, row.TABLE_NAME)
            result["tables"].append({
                "schema":  row.TABLE_SCHEMA,
                "name":    row.TABLE_NAME,
                "columns": col_map.get(key, []),
                "primary_key": pk_map.get(key),
                "foreign_keys": fk_map.get(key, []),
                "indexes": idx_map.get(key, []),
            })

        # ── Views ────────────────────────────────────────────────────────
        cur.execute("""
            SELECT s.name schema_name, o.name object_name, m.definition
            FROM sys.objects o
            JOIN sys.schemas    s ON o.schema_id  = s.schema_id
            JOIN sys.sql_modules m ON o.object_id = m.object_id
            WHERE o.type = 'V'
              AND s.name NOT IN ('sys')
            ORDER BY s.name, o.name
        """)
        for r in cur.fetchall():
            result["views"].append({
                "schema":     r.schema_name,
                "name":       r.object_name,
                "definition": (r.definition or "").strip(),
            })

        # ── Stored Procedures ─────────────────────────────────────────────
        cur.execute("""
            SELECT s.name schema_name, o.name object_name, m.definition
            FROM sys.objects o
            JOIN sys.schemas    s ON o.schema_id  = s.schema_id
            JOIN sys.sql_modules m ON o.object_id = m.object_id
            WHERE o.type = 'P'
              AND s.name NOT IN ('sys')
            ORDER BY s.name, o.name
        """)
        for r in cur.fetchall():
            result["stored_procedures"].append({
                "schema":     r.schema_name,
                "name":       r.object_name,
                "definition": (r.definition or "").strip(),
            })

        # ── Functions ────────────────────────────────────────────────────
        cur.execute("""
            SELECT s.name schema_name, o.name object_name, o.type_desc, m.definition
            FROM sys.objects o
            JOIN sys.schemas    s ON o.schema_id  = s.schema_id
            JOIN sys.sql_modules m ON o.object_id = m.object_id
            WHERE o.type IN ('FN','IF','TF')   -- scalar / inline / multi-statement
              AND s.name NOT IN ('sys')
            ORDER BY s.name, o.name
        """)
        for r in cur.fetchall():
            result["functions"].append({
                "schema":     r.schema_name,
                "name":       r.object_name,
                "type":       r.type_desc,
                "definition": (r.definition or "").strip(),
            })

    finally:
        conn.close()

    # Summary line prepended for quick reading
    summary_lines = [
        f"schemas={len(result['schemas'])}",
        f"tables={len(result['tables'])}",
        f"views={len(result['views'])}",
        f"stored_procedures={len(result['stored_procedures'])}",
        f"functions={len(result['functions'])}",
    ]
    return "# DB Metadata  " + "  ".join(summary_lines) + "\n" + json.dumps(result, indent=2, ensure_ascii=False)
