"""Madencilik çıktılarının Parquet şemaları. Belge: docs/mining-schema.md."""

import polars as pl

SCHEMA_VERSION = 1

UTC_TS = pl.Datetime("us", "UTC")

COMMITS: dict[str, pl.DataType] = {
    "repo": pl.String(),
    "sha": pl.String(),
    "parents": pl.List(pl.String()),
    "is_merge": pl.Boolean(),
    "author_name": pl.String(),
    "author_email": pl.String(),
    "author_date": UTC_TS,
    "author_utc_offset_minutes": pl.Int32(),
    "committer_date": UTC_TS,
    "message": pl.String(),
    "files_changed": pl.Int32(),
    "lines_added": pl.Int32(),
    "lines_deleted": pl.Int32(),
    "is_fix": pl.Boolean(),
    "fix_signals": pl.List(pl.String()),
    "linked_issues": pl.List(pl.Int64()),
}

FILES: dict[str, pl.DataType] = {
    "repo": pl.String(),
    "sha": pl.String(),
    "old_path": pl.String(),
    "new_path": pl.String(),
    "change_type": pl.String(),
    "lines_added": pl.Int32(),
    "lines_deleted": pl.Int32(),
    "is_python": pl.Boolean(),
}

SZZ: dict[str, pl.DataType] = {
    "repo": pl.String(),
    "fix_sha": pl.String(),
    "inducing_sha": pl.String(),
    "path": pl.String(),
    "blamed_lines": pl.Int32(),
    "fix_date": UTC_TS,
    "inducing_date": UTC_TS,
}

FUNCTIONS: dict[str, pl.DataType] = {
    "repo": pl.String(),
    "sha": pl.String(),
    "path": pl.String(),
    "name": pl.String(),
    "long_name": pl.String(),
    "start_line": pl.Int32(),
    "end_line": pl.Int32(),
    "nloc": pl.Int32(),
    "complexity": pl.Int32(),
}
