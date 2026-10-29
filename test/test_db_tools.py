"""Tests for db_read_metadata, db_apply_change, and db_schema_drift plugins.

All live-DB tests are skipped when pyodbc or a reachable server is not
available (CI without network access).  Unit-level logic (conn-string
normalisation, type formatting, project parsing) is always exercised.
"""

from __future__ import annotations

import textwrap
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# ── helpers ──────────────────────────────────────────────────────────────────

def _import_or_skip(module: str):
    """Return the module or pytest.skip if it can't be imported."""
    try:
        import importlib
        return importlib.import_module(module)
    except ImportError:
        pytest.skip(f"Required module '{module}' not installed")


# ─────────────────────────────────────────────────────────────────────────────
# Connection-string normaliser  (tested via the private helper in each plugin)
# ─────────────────────────────────────────────────────────────────────────────

class TestNormaliseConnStr:
    """_normalise_conn_str must convert ADO.NET strings to ODBC format."""

    @pytest.fixture(autouse=True)
    def _import(self):
        from agent.plugin.db_read_metadata import _normalise_conn_str
        self.fn = _normalise_conn_str

    def test_odbc_passthrough(self):
        # Trailing semicolon is stripped by the normaliser; that's intentional
        odbc = "Driver={ODBC Driver 18 for SQL Server};Server=x;Database=y;Uid=u;Pwd=p"
        assert self.fn(odbc) == odbc

    def test_ado_to_odbc_keys(self):
        ado = (
            "Server=tcp:srv.database.windows.net,1433;"
            "Initial Catalog=mydb;"
            "User ID=admin;"
            "Password=s3cret;"
            "Encrypt=True;"
            "TrustServerCertificate=False;"
            "Connection Timeout=30;"
            "Persist Security Info=False;"
        )
        result = self.fn(ado)
        assert "Driver={ODBC Driver 18 for SQL Server}" in result
        assert "Database=mydb" in result
        assert "Uid=admin" in result
        assert "Pwd=s3cret" in result
        assert "Encrypt=yes" in result
        assert "TrustServerCertificate=no" in result
        # Ignored key must not appear
        assert "Persist" not in result
        assert "Security" not in result

    def test_bool_normalisation_true_variants(self):
        for val in ("True", "yes", "1"):
            ado = f"Server=s;Initial Catalog=d;User ID=u;Password=p;Encrypt={val};"
            result = self.fn(ado)
            assert "Encrypt=yes" in result

    def test_bool_normalisation_false_variants(self):
        for val in ("False", "no", "0"):
            ado = f"Server=s;Initial Catalog=d;User ID=u;Password=p;Encrypt={val};"
            result = self.fn(ado)
            assert "Encrypt=no" in result


# ─────────────────────────────────────────────────────────────────────────────
# Type formatter
# ─────────────────────────────────────────────────────────────────────────────

class TestFmtType:
    @pytest.fixture(autouse=True)
    def _import(self):
        from agent.plugin.db_read_metadata import _fmt_type
        self.fn = _fmt_type

    def test_varchar(self):
        assert self.fn("varchar", 100, None, None, None) == "varchar(100)"

    def test_nvarchar_max(self):
        assert self.fn("nvarchar", -1, None, None, None) == "nvarchar(MAX)"

    def test_decimal(self):
        assert self.fn("decimal", None, 18, 4, None) == "decimal(18,4)"

    def test_datetime2(self):
        assert self.fn("datetime2", None, None, None, 7) == "datetime2(7)"

    def test_int(self):
        assert self.fn("int", None, None, None, None) == "int"

    def test_bit(self):
        assert self.fn("bit", None, None, None, None) == "bit"


# ─────────────────────────────────────────────────────────────────────────────
# db_read_metadata — schema / registration
# ─────────────────────────────────────────────────────────────────────────────

class TestDbReadMetadataRegistration:
    def test_tool_is_registered(self):
        import agent.runner  # noqa: F401 – triggers plugin registration
        from agent.core.registry import REGISTRY
        assert "db_read_metadata" in REGISTRY

    def test_schema_exposes_connection_string(self):
        from agent.core.registry import REGISTRY
        tool = REGISTRY.get("db_read_metadata")
        assert "connection_string" in tool.properties
        assert "connection_string" in tool.required


# ─────────────────────────────────────────────────────────────────────────────
# db_apply_change — schema / registration
# ─────────────────────────────────────────────────────────────────────────────

class TestDbApplyChangeRegistration:
    def test_tool_is_registered(self):
        import agent.runner  # noqa: F401
        from agent.core.registry import REGISTRY
        assert "db_apply_change" in REGISTRY

    def test_schema_exposes_sql_param(self):
        from agent.core.registry import REGISTRY
        tool = REGISTRY.get("db_apply_change")
        assert "sql" in tool.properties
        assert "sql" in tool.required

    def test_empty_sql_raises(self):
        from agent.core.registry import ToolError
        from agent.plugin.db_apply_change import db_apply_change
        with pytest.raises(ToolError, match="empty"):
            db_apply_change(connection_string="Server=x;", sql="")

    def test_blank_sql_raises(self):
        from agent.core.registry import ToolError
        from agent.plugin.db_apply_change import db_apply_change
        with pytest.raises(ToolError, match="empty"):
            db_apply_change(connection_string="Server=x;", sql="   ")


# ─────────────────────────────────────────────────────────────────────────────
# db_schema_drift — project parser
# ─────────────────────────────────────────────────────────────────────────────

class TestProjectParser:
    """The project SQL parser must correctly extract tables and views."""

    @pytest.fixture
    def project(self, tmp_path: Path) -> Path:
        """Build a minimal SSDT-style project on disk."""
        tables_dir = tmp_path / "dbo" / "Tables"
        views_dir  = tmp_path / "dbo" / "Views"
        tables_dir.mkdir(parents=True)
        views_dir.mkdir(parents=True)

        (tables_dir / "Person.sql").write_text(textwrap.dedent("""\
            CREATE TABLE [dbo].[Person]
            (
                [id]   INT NOT NULL IDENTITY(1, 1),
                [name] VARCHAR(100) NULL,
                CONSTRAINT [PK_Person] PRIMARY KEY ([id] ASC)
            );
        """), encoding="utf-8")

        (views_dir / "PersonView.sql").write_text(textwrap.dedent("""\
            CREATE VIEW [dbo].[PersonView] AS
            SELECT id, name FROM [dbo].[Person];
        """), encoding="utf-8")

        return tmp_path

    def test_table_columns_parsed(self, project):
        from agent.plugin.db_schema_drift import _read_project
        cols, pks, identity, fks, views, procs, files = _read_project(project)
        assert ("dbo", "person", "id") in cols
        assert ("dbo", "person", "name") in cols

    def test_pk_parsed(self, project):
        from agent.plugin.db_schema_drift import _read_project
        cols, pks, identity, fks, views, procs, files = _read_project(project)
        assert ("dbo", "person", "id") in pks

    def test_identity_parsed(self, project):
        from agent.plugin.db_schema_drift import _read_project
        cols, pks, identity, fks, views, procs, files = _read_project(project)
        assert ("dbo", "person", "id") in identity
        assert identity[("dbo", "person", "id")] == (1, 1)

    def test_view_detected(self, project):
        from agent.plugin.db_schema_drift import _read_project
        cols, pks, identity, fks, views, procs, files = _read_project(project)
        assert ("dbo", "personview") in views

    def test_file_list(self, project):
        from agent.plugin.db_schema_drift import _read_project
        cols, pks, identity, fks, views, procs, files = _read_project(project)
        assert len(files) == 2


# ─────────────────────────────────────────────────────────────────────────────
# db_schema_drift — drift detection logic
# ─────────────────────────────────────────────────────────────────────────────

class TestDriftDetection:
    """Run the drift check against a mocked live DB (no network needed)."""

    @pytest.fixture
    def project_with_extra_col(self, tmp_path: Path) -> Path:
        tables_dir = tmp_path / "dbo" / "Tables"
        tables_dir.mkdir(parents=True)
        (tables_dir / "Foo.sql").write_text(textwrap.dedent("""\
            CREATE TABLE [dbo].[Foo]
            (
                [id]    INT NOT NULL IDENTITY(1,1),
                [col_a] VARCHAR(50) NULL,
                [col_b] INT NULL,
                CONSTRAINT [PK_Foo] PRIMARY KEY ([id] ASC)
            );
        """), encoding="utf-8")
        return tmp_path

    def _make_live(self, **overrides):
        """Return a fake live-schema tuple matching a minimal Foo table."""
        cols = {
            ("dbo", "foo", "id"):    {"type": "int",          "nullable": False, "default": None},
            ("dbo", "foo", "col_a"): {"type": "varchar(50)",  "nullable": True,  "default": None},
        }
        cols.update(overrides.get("cols", {}))
        pks      = {("dbo", "foo", "id")}
        identity = {("dbo", "foo", "id"): (1, 1)}
        fks      = {}
        db_views = set()
        db_procs = set()
        return cols, pks, identity, fks, db_views, db_procs

    def test_detects_extra_column_in_project(self, project_with_extra_col):
        from agent.plugin.db_schema_drift import _read_project, _read_live
        proj = _read_project(project_with_extra_col)

        fake_live = self._make_live()  # col_b is missing from live

        with patch("agent.plugin.db_schema_drift._read_live", return_value=fake_live):
            from agent.plugin.db_schema_drift import db_schema_drift
            result = db_schema_drift(
                connection_string="Server=fake;",
                project_root=str(project_with_extra_col),
                workdir=project_with_extra_col,
            )

        assert "MISSING IN DB" in result
        assert "col_b" in result

    def test_no_drift_when_in_sync(self, tmp_path):
        from agent.plugin.db_schema_drift import db_schema_drift
        tables_dir = tmp_path / "dbo" / "Tables"
        tables_dir.mkdir(parents=True)
        (tables_dir / "Bar.sql").write_text(textwrap.dedent("""\
            CREATE TABLE [dbo].[Bar]
            (
                [id] INT NOT NULL IDENTITY(1,1),
                CONSTRAINT [PK_Bar] PRIMARY KEY ([id] ASC)
            );
        """), encoding="utf-8")

        fake_live = (
            {("dbo", "bar", "id"): {"type": "int", "nullable": False, "default": None}},
            {("dbo", "bar", "id")},
            {("dbo", "bar", "id"): (1, 1)},
            {},
            set(),
            set(),
        )
        with patch("agent.plugin.db_schema_drift._read_live", return_value=fake_live):
            result = db_schema_drift(
                connection_string="Server=fake;",
                project_root=str(tmp_path),
                workdir=tmp_path,
            )

        assert "No drift detected" in result

    def test_invalid_project_root_raises(self, tmp_path):
        from agent.core.registry import ToolError
        from agent.plugin.db_schema_drift import db_schema_drift
        with pytest.raises(ToolError, match="does not exist"):
            db_schema_drift(
                connection_string="Server=fake;",
                project_root="/nonexistent/path/xyz",
                workdir=tmp_path,
            )
