"""Build the SQLite warehouse and the Power BI extract from the generator.

Usage:  python -m tokenroi.warehouse
Writes: data/northwind_ai.db (git-ignored, rebuilt in seconds) and powerbi/data/*.csv
"""
from __future__ import annotations

import sqlite3
from pathlib import Path

from tokenroi.data import generate

ROOT = Path(__file__).resolve().parents[2]
DB = ROOT / "data" / "northwind_ai.db"
PBI = ROOT / "powerbi" / "data"
VIEWS = ROOT / "sql" / "00_views.sql"


def build(path: Path = DB, seed: int = 26, export: bool = True) -> Path:
    tables = generate(seed)
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        path.unlink()
    with sqlite3.connect(path) as con:
        for name, df in tables.items():
            df = df.copy()
            for c in df.columns:
                if str(df[c].dtype).startswith("datetime"):
                    df[c] = df[c].dt.strftime("%Y-%m-%d")
            df.to_sql(name, con, index=False)
        con.executescript(VIEWS.read_text())
    if export:
        PBI.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(path) as con:
            import pandas as pd
            for name in ["dim_team", "dim_feature", "dim_model", "dim_date", "fact_usage_daily", "fact_outcomes_weekly",
                         "model_quality", "survey_time_saved"]:
                pd.read_sql(f"SELECT * FROM {name}", con).to_csv(PBI / f"{name}.csv", index=False)
    return path


def connect(path: Path = DB) -> sqlite3.Connection:
    if not path.exists():
        build(path)
    return sqlite3.connect(path)


if __name__ == "__main__":
    print(f"Built {build()}")
