"""A read-only gate for SQL written by a model: one SELECT (or WITH ... SELECT) and nothing else.

This is a second line of defence. The database is also opened read-only with external access switched off, so a
query that slipped through still could not write or read files.
"""
import re

_FORBIDDEN = re.compile(
    r"\b(attach|detach|copy|install|load|pragma|set|reset|export|import|call|create|drop|alter|insert|update|delete|"
    r"truncate|vacuum|checkpoint|glob|httpfs|extension|read_\w+|write_\w+)\b", re.I)


class Rejected(ValueError):
    pass


def _strip(sql: str) -> str:
    sql = re.sub(r"/\*.*?\*/", " ", sql, flags=re.S)
    sql = re.sub(r"--[^\n]*", " ", sql)
    return sql.strip()


def _without_literals(sql: str) -> str:
    sql = re.sub(r"'(?:[^']|'')*'", "''", sql)
    return re.sub(r'"(?:[^"]|"")*"', '""', sql)


def check(sql: str) -> str:
    """The SQL ready to run (comments and a trailing semicolon removed), or Rejected."""
    s = _strip(sql or "")
    if s.endswith(";"):
        s = s[:-1].rstrip()
    if not s:
        raise Rejected("empty query")
    bare = _without_literals(s)
    if ";" in bare:
        raise Rejected("only one statement is allowed")
    if not re.match(r"(?is)^\s*(select|with)\b", bare):
        raise Rejected("only SELECT queries are allowed")
    m = _FORBIDDEN.search(bare)
    if m:
        raise Rejected(f"'{m.group(0)}' is not allowed")
    return s
