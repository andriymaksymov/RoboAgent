"""db_schema_drift – compare an SSDT-style SQL database project against a live DB.

Reads every CREATE TABLE / CREATE VIEW / CREATE PROCEDURE file under the
project root (organised as ``<Schema>/<Type>/<Object>.sql``) and compares them
against the live Azure SQL / SQL Server database.  Returns a human-readable
drift report.

Connection strings in ADO.NET *or* pyodbc/ODBC format are both accepted.
"""

from __future__ import annotations

import re
from pathlib import Path

from agent.core.registry import ToolError, tool

# ---------------------------------------------------------------------------
# Connection-string normaliser (shared pattern with db_read_metadata)
# ---------------------------------------------------------------------------

_BOOL_TRUE = {"true", "yes", "1"}
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
        if odbc_key in ("Encrypt", "TrustServerCertificate"):
            v = "yes" if v.lower() in _BOOL_TRUE else "no"
        odbc_parts.append(f"{odbc_key}={v}")
    return ";".join(odbc_parts) + ";"


# ---------------------------------------------------------------------------
# Type / default helpers
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


def _strip_default(raw: str | None) -> str | None:
    if raw is None:
        return None
    s = raw.strip()
    while s.startswith("(") and s.endswith(")"):
        s = s[1:-1].strip()
    return s.lower()


# ---------------------------------------------------------------------------
# Live schema reader
# ---------------------------------------------------------------------------

def _read_live(conn_str: str):
    import pyodbc  # type: ignore

    conn = pyodbc.connect(conn_str, timeout=35)
    conn.add_output_converter(-16, lambda b: b.decode("utf-16-le") if b else None)
    cur = conn.cursor()

    cur.execute("""
        SELECT c.TABLE_SCHEMA, c.TABLE_NAME, c.COLUMN_NAME, c.IS_NULLABLE,
               c.DATA_TYPE, c.CHARACTER_MAXIMUM_LENGTH, c.NUMERIC_PRECISION,
               c.NUMERIC_SCALE, CAST(c.COLUMN_DEFAULT AS NVARCHAR(500)) CD,
               c.DATETIME_PRECISION
        FROM INFORMATION_SCHEMA.COLUMNS c
        JOIN INFORMATION_SCHEMA.TABLES t
            ON c.TABLE_SCHEMA = t.TABLE_SCHEMA AND c.TABLE_NAME = t.TABLE_NAME
        WHERE t.TABLE_TYPE = 'BASE TABLE' AND c.TABLE_SCHEMA NOT IN ('sys','INFORMATION_SCHEMA')
        ORDER BY c.TABLE_SCHEMA, c.TABLE_NAME, c.ORDINAL_POSITION
    """)
    columns = {
        (r.TABLE_SCHEMA.lower(), r.TABLE_NAME.lower(), r.COLUMN_NAME.lower()): {
            "type":     _fmt_type(r.DATA_TYPE, r.CHARACTER_MAXIMUM_LENGTH,
                                  r.NUMERIC_PRECISION, r.NUMERIC_SCALE, r.DATETIME_PRECISION),
            "nullable": r.IS_NULLABLE.upper() == "YES",
            "default":  _strip_default(r.CD),
        }
        for r in cur.fetchall()
    }

    cur.execute("""
        SELECT KU.TABLE_SCHEMA, KU.TABLE_NAME, KU.COLUMN_NAME
        FROM INFORMATION_SCHEMA.TABLE_CONSTRAINTS TC
        JOIN INFORMATION_SCHEMA.KEY_COLUMN_USAGE KU
            ON TC.CONSTRAINT_TYPE = 'PRIMARY KEY' AND TC.CONSTRAINT_NAME = KU.CONSTRAINT_NAME
    """)
    pks = {(r.TABLE_SCHEMA.lower(), r.TABLE_NAME.lower(), r.COLUMN_NAME.lower())
           for r in cur.fetchall()}

    cur.execute("""
        SELECT s.name TS, t.name TN, c.name CN,
               CAST(ic.seed_value AS BIGINT) seed, CAST(ic.increment_value AS BIGINT) incr
        FROM sys.identity_columns ic
        JOIN sys.columns c ON ic.object_id=c.object_id AND ic.column_id=c.column_id
        JOIN sys.tables  t ON c.object_id=t.object_id
        JOIN sys.schemas s ON t.schema_id=s.schema_id
    """)
    identity = {(r.TS.lower(), r.TN.lower(), r.CN.lower()): (r.seed, r.incr)
                for r in cur.fetchall()}

    cur.execute("""
        SELECT s_p.name PS, tp.name PT, cp.name PC,
               s_r.name RS, tr.name RT, cr.name RC
        FROM sys.foreign_keys fk
        JOIN sys.foreign_key_columns fkc ON fk.object_id=fkc.constraint_object_id
        JOIN sys.tables  tp ON fkc.parent_object_id=tp.object_id
        JOIN sys.schemas s_p ON tp.schema_id=s_p.schema_id
        JOIN sys.columns cp  ON fkc.parent_object_id=cp.object_id AND fkc.parent_column_id=cp.column_id
        JOIN sys.tables  tr  ON fkc.referenced_object_id=tr.object_id
        JOIN sys.schemas s_r ON tr.schema_id=s_r.schema_id
        JOIN sys.columns cr  ON fkc.referenced_object_id=cr.object_id AND fkc.referenced_column_id=cr.column_id
    """)
    fks = {(r.PS.lower(), r.PT.lower(), r.PC.lower()): (r.RS.lower(), r.RT.lower(), r.RC.lower())
           for r in cur.fetchall()}

    # Views in the DB
    cur.execute("""
        SELECT s.name schema_name, o.name object_name
        FROM sys.objects o
        JOIN sys.schemas s ON o.schema_id=s.schema_id
        WHERE o.type='V' AND s.name NOT IN ('sys')
        ORDER BY s.name, o.name
    """)
    db_views = {(r.schema_name.lower(), r.object_name.lower()) for r in cur.fetchall()}

    # Stored procedures in the DB
    cur.execute("""
        SELECT s.name schema_name, o.name object_name
        FROM sys.objects o
        JOIN sys.schemas s ON o.schema_id=s.schema_id
        WHERE o.type='P' AND s.name NOT IN ('sys')
        ORDER BY s.name, o.name
    """)
    db_procs = {(r.schema_name.lower(), r.object_name.lower()) for r in cur.fetchall()}

    conn.close()
    return columns, pks, identity, fks, db_views, db_procs


# ---------------------------------------------------------------------------
# Project parser regex patterns
# ---------------------------------------------------------------------------
_PK_RE  = re.compile(r"CONSTRAINT\s+\[[^\]]+\]\s+PRIMARY KEY[^(]*\(([^)]+)\)", re.IGNORECASE)
_FK_RE  = re.compile(
    r"CONSTRAINT\s+\[[^\]]+\]\s+FOREIGN KEY\s*\(\[([^\]]+)\]\)\s*"
    r"REFERENCES\s+\[([^\]]+)\]\.\[([^\]]+)\]\s*\(\[([^\]]+)\]\)", re.IGNORECASE)
_DEF_RE = re.compile(r"DEFAULT\s+\(([^()]*(?:\([^()]*\))*[^()]*)\)", re.IGNORECASE)
_IDN_RE = re.compile(r"IDENTITY\s*\((\d+)\s*,\s*(\d+)\)", re.IGNORECASE)
_COL_RE = re.compile(r"^\[(?P<col>[^\]]+)\]\s+(?P<type>\w+)(?:\((?P<args>[^)]+)\))?", re.IGNORECASE)


def _parse_sql_type(base: str, args: str | None) -> str:
    b = base.lower()
    if args is None:
        return b
    a = args.strip().upper()
    if b in ("varchar", "nvarchar", "char", "nchar", "binary", "varbinary"):
        return f"{b}({a})"
    if b in ("decimal", "numeric"):
        return f"{b}({','.join(x.strip() for x in a.split(','))})"
    if b in ("datetime2", "time", "datetimeoffset"):
        return f"{b}({a})"
    return b


def _read_project(root: Path):
    columns: dict = {}
    pks: set = set()
    identity: dict = {}
    fks: dict = {}
    proj_views: set = set()
    proj_procs: set = set()
    sql_files: list = []

    for sql_path in sorted(root.rglob("**/*.sql")):
        parts = sql_path.relative_to(root).parts
        if len(parts) < 3:
            continue  # not Schema/Type/Object.sql
        schema = parts[0].lower()
        obj_type = parts[1].lower()  # Tables / Views / StoredProcedures
        obj_name = sql_path.stem.lower()

        raw  = sql_path.read_text(encoding="utf-8")
        text = re.sub(r"--[^\n]*", "", raw)
        sql_files.append(sql_path)

        if obj_type == "views":
            proj_views.add((schema, obj_name))
            continue
        if obj_type in ("storedprocedures", "stored procedures"):
            proj_procs.add((schema, obj_name))
            continue
        if obj_type != "tables":
            continue

        m = re.search(r"CREATE\s+TABLE[^(]+\((.+)\)", text, re.DOTALL | re.IGNORECASE)
        if not m:
            continue

        body = m.group(1)
        clauses = [c.strip() for c in re.split(r",\s*\n", body) if c.strip()]
        for clause in clauses:
            pk_m = _PK_RE.search(clause)
            if pk_m:
                for col in re.findall(r"\[([^\]]+)\]", pk_m.group(1)):
                    pks.add((schema, obj_name, col.lower()))
                continue
            fk_m = _FK_RE.search(clause)
            if fk_m:
                pc, rs, rt, rc = fk_m.groups()
                fks[(schema, obj_name, pc.lower())] = (rs.lower(), rt.lower(), rc.lower())
                continue
            col_m = _COL_RE.match(clause)
            if not col_m:
                continue
            col  = col_m.group("col").lower()
            typ  = _parse_sql_type(col_m.group("type"), col_m.group("args"))
            null = "NOT NULL" not in clause.upper()
            def_m   = _DEF_RE.search(clause)
            idn_m   = _IDN_RE.search(clause)
            key = (schema, obj_name, col)
            columns[key] = {
                "type":     typ,
                "nullable": null,
                "default":  def_m.group(1).strip().lower() if def_m else None,
            }
            if idn_m:
                identity[key] = (int(idn_m.group(1)), int(idn_m.group(2)))

    return columns, pks, identity, fks, proj_views, proj_procs, sql_files


# ---------------------------------------------------------------------------
# Tool
# ---------------------------------------------------------------------------

@tool
def db_schema_drift(connection_string: str, project_root: str, workdir: Path) -> str:
    """Compare an SSDT-style SQL database project against a live SQL Server database.

    Reads CREATE TABLE / VIEW / PROCEDURE SQL files from the project (organised
    as ``<Schema>/<Type>/<Object>.sql``) and reports any differences compared to
    the live database (missing columns, type mismatches, extra objects, etc.).

    Args:
        connection_string: ADO.NET or pyodbc ODBC connection string for the target database.
        project_root: Path to the database project root (absolute or relative to workdir).
    """
    root = Path(project_root)
    if not root.is_absolute():
        root = workdir / root
    if not root.exists():
        raise ToolError(f"project_root does not exist: {root}")

    odbc_str = _normalise_conn_str(connection_string)

    # Read live
    try:
        live = _read_live(odbc_str)
    except OSError as exc:
        raise ToolError(f"Cannot read live database: {exc}")

    live_cols, live_pks, live_id, live_fks, db_views, db_procs = live

    # Read project
    proj = _read_project(root)
    proj_cols, proj_pks, proj_id, proj_fks, proj_views, proj_procs, sql_files = proj

    drifts: list[str] = []

    # ── Columns ──────────────────────────────────────────────────────────────
    for k in proj_cols:
        if k not in live_cols:
            drifts.append(f"MISSING IN DB   : [{k[0]}].[{k[1]}].[{k[2]}]")
    for k in live_cols:
        if k not in proj_cols:
            drifts.append(f"EXTRA IN DB     : [{k[0]}].[{k[1]}].[{k[2]}]")
    for k in proj_cols:
        if k not in live_cols:
            continue
        p, l = proj_cols[k], live_cols[k]
        if p["type"] != l["type"]:
            drifts.append(f"TYPE MISMATCH   : [{'.'.join(k)}]  proj={p['type']}  db={l['type']}")
        if p["nullable"] != l["nullable"]:
            drifts.append(f"NULL MISMATCH   : [{'.'.join(k)}]  "
                          f"proj={'NULL' if p['nullable'] else 'NOT NULL'}  "
                          f"db={'NULL' if l['nullable'] else 'NOT NULL'}")
        if p["default"] != l["default"]:
            drifts.append(f"DEFAULT MISMATCH: [{'.'.join(k)}]  proj={p['default']}  db={l['default']}")

    # ── PKs ──────────────────────────────────────────────────────────────────
    for k in proj_pks - live_pks:
        drifts.append(f"PK MISSING IN DB: [{'.'.join(k)}]")
    for k in live_pks - proj_pks:
        drifts.append(f"PK EXTRA IN DB  : [{'.'.join(k)}]")

    # ── Identity ─────────────────────────────────────────────────────────────
    for k, v in proj_id.items():
        if k not in live_id:
            drifts.append(f"IDENTITY MISSING: [{'.'.join(k)}]")
        elif v != live_id[k]:
            drifts.append(f"IDENTITY MISMATCH: [{'.'.join(k)}]  proj={v}  db={live_id[k]}")
    for k in live_id:
        if k not in proj_id:
            drifts.append(f"IDENTITY EXTRA  : [{'.'.join(k)}]")

    # ── FKs ──────────────────────────────────────────────────────────────────
    for k, v in proj_fks.items():
        if k not in live_fks:
            drifts.append(f"FK MISSING IN DB: [{'.'.join(k)}] -> {v}")
        elif v != live_fks[k]:
            drifts.append(f"FK MISMATCH: [{'.'.join(k)}]  proj={v}  db={live_fks[k]}")
    for k, v in live_fks.items():
        if k not in proj_fks:
            drifts.append(f"FK EXTRA IN DB  : [{'.'.join(k)}] -> {v}")

    # ── Views ─────────────────────────────────────────────────────────────────
    for v in proj_views - db_views:
        drifts.append(f"VIEW MISSING IN DB : [{v[0]}].[{v[1]}]")
    for v in db_views - proj_views:
        drifts.append(f"VIEW EXTRA IN DB   : [{v[0]}].[{v[1]}]")

    # ── Stored Procedures ─────────────────────────────────────────────────────
    for p in proj_procs - db_procs:
        drifts.append(f"PROC MISSING IN DB : [{p[0]}].[{p[1]}]")
    for p in db_procs - proj_procs:
        drifts.append(f"PROC EXTRA IN DB   : [{p[0]}].[{p[1]}]")

    # ── Report ────────────────────────────────────────────────────────────────
    lines = ["=" * 70, "  SCHEMA DRIFT REPORT", "=" * 70, ""]
    if not drifts:
        lines.append("  [OK] No drift detected — project and database are in sync.")
    else:
        lines.append(f"  [!!] {len(drifts)} drift(s) found:")
        for d in drifts:
            lines.append(f"    * {d}")
    lines += [
        "",
        f"  Parsed files   : {len(sql_files)}",
        f"  Columns  proj={len(proj_cols):3d}  db={len(live_cols):3d}",
        f"  PKs      proj={len(proj_pks):3d}  db={len(live_pks):3d}",
        f"  FKs      proj={len(proj_fks):3d}  db={len(live_fks):3d}",
        f"  Identity proj={len(proj_id):3d}  db={len(live_id):3d}",
        f"  Views    proj={len(proj_views):3d}  db={len(db_views):3d}",
        f"  Procs    proj={len(proj_procs):3d}  db={len(db_procs):3d}",
        "=" * 70,
    ]
    return "\n".join(lines)
