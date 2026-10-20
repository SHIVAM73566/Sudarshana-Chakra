"""Local business data layer for Sudarshana Chakra AI.

Provides a single, thread-safe SQLite-backed store shared by every enterprise
vertical (manufacturing, procurement, inventory, finance, marketing) plus
helpers for encrypted-at-rest protection and Excel/CSV export.

Design goals
------------
* **Local-first**: everything lives in ``%LOCALAPPDATA%/SudarshanaAI/business``.
* **Zero hard dependency on optional packages**: ``openpyxl``/``pandas`` are
  imported lazily; export degrades gracefully to CSV when they are absent.
* **Encrypted at rest**: sensitive columns are optionally protected with the
  Windows Data Protection API (DPAPI). On non-Windows hosts (or when DPAPI is
  unavailable) the store falls back to an obfuscating HMAC-XOR stream so the
  module never crashes and never stores plaintext secrets.
* **Thread-safe**: one connection guarded by a lock; ``check_same_thread`` is
  disabled so background worker threads may query concurrently.
"""

from __future__ import annotations

import base64
import csv
import hashlib
import json
import logging
import os
import sqlite3
import threading
import time
from pathlib import Path
from typing import Any, Iterable

from core.user_paths import get_user_data_dir

logger = logging.getLogger("sudarshana.business.db")

BUSINESS_DIR = get_user_data_dir() / "business"
DEFAULT_DB_PATH = BUSINESS_DIR / "business.sqlite3"

__all__ = [
    "BusinessStore",
    "get_store",
    "EncryptedColumn",
    "export_rows",
    "BUSINESS_DIR",
]


# --------------------------------------------------------------------------- #
# At-rest encryption (DPAPI primary, HMAC-XOR fallback)
# --------------------------------------------------------------------------- #

class _Protector:
    """Protects short sensitive strings for local storage.

    Primary path uses the Windows DPAPI (``CryptProtectData``) via ctypes so the
    ciphertext is bound to the current user account. When unavailable, a
    deterministic HMAC-derived XOR stream is used. The fallback is NOT
    cryptographically strong; it only prevents casual plaintext exposure, which
    is an accepted trade-off for cross-platform portability.
    """

    _PREFIX_DPAPI = "dpapi:"
    _PREFIX_XOR = "x1:"

    def __init__(self, key_material: str = "sudarshana-business-v1") -> None:
        self._key = hashlib.sha256(key_material.encode("utf-8")).digest()
        self._dpapi_ok = self._probe_dpapi()

    def _probe_dpapi(self) -> bool:
        if os.name != "nt":
            return False
        try:
            import importlib.util

            return importlib.util.find_spec("ctypes") is not None
        except Exception:
            return False

    def protect(self, plaintext: str) -> str:
        raw = str(plaintext).encode("utf-8")
        if self._dpapi_ok:
            try:
                return self._PREFIX_DPAPI + self._dpapi_protect(raw)
            except Exception:
                pass
        return self._PREFIX_XOR + self._xor(raw).hex()

    def unprotect(self, token: str) -> str:
        token = str(token)
        if token.startswith(self._PREFIX_DPAPI):
            try:
                return self._dpapi_unprotect(token[len(self._PREFIX_DPAPI):])
            except Exception:
                return ""
        if token.startswith(self._PREFIX_XOR):
            try:
                return self._xor(bytes.fromhex(token[len(self._PREFIX_XOR):])).decode("utf-8")
            except Exception:
                return ""
        return token

    def _xor(self, data: bytes) -> bytes:
        keystream = bytearray()
        counter = 0
        while len(keystream) < len(data):
            keystream.extend(hashlib.sha256(self._key + counter.to_bytes(4, "big")).digest())
            counter += 1
        return bytes(b ^ k for b, k in zip(data, keystream))

    def _dpapi_protect(self, raw: bytes) -> str:
        import ctypes
        from ctypes import wintypes

        class DATA_BLOB(ctypes.Structure):
            _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_char))]

        crypt32 = ctypes.windll.crypt32
        kernel32 = ctypes.windll.kernel32
        blob_in = DATA_BLOB(len(raw), ctypes.cast(ctypes.create_string_buffer(raw), ctypes.POINTER(ctypes.c_char)))
        blob_out = DATA_BLOB()
        if not crypt32.CryptProtectData(ctypes.byref(blob_in), None, None, None, None, 0, ctypes.byref(blob_out)):
            raise OSError("CryptProtectData failed")
        try:
            buf = ctypes.string_at(blob_out.pbData, blob_out.cbData)
            return base64.b64encode(buf).decode("ascii")
        finally:
            kernel32.LocalFree(blob_out.pbData)

    def _dpapi_unprotect(self, b64: str) -> str:
        import ctypes
        from ctypes import wintypes

        class DATA_BLOB(ctypes.Structure):
            _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_char))]

        raw = base64.b64decode(b64)
        crypt32 = ctypes.windll.crypt32
        kernel32 = ctypes.windll.kernel32
        blob_in = DATA_BLOB(len(raw), ctypes.cast(ctypes.create_string_buffer(raw), ctypes.POINTER(ctypes.c_char)))
        blob_out = DATA_BLOB()
        if not crypt32.CryptUnprotectData(ctypes.byref(blob_in), None, None, None, None, 0, ctypes.byref(blob_out)):
            raise OSError("CryptUnprotectData failed")
        try:
            return ctypes.string_at(blob_out.pbData, blob_out.cbData).decode("utf-8")
        finally:
            kernel32.LocalFree(blob_out.pbData)


_protector = _Protector()


def EncryptedColumn(value: str) -> str:  # noqa: N802 - intentional constructor-style API
    """Return an at-rest protected token for *value*."""
    return _protector.protect(value)


def decrypt_column(token: str) -> str:
    """Reverse :func:`EncryptedColumn`."""
    return _protector.unprotect(token)


# --------------------------------------------------------------------------- #
# Store
# --------------------------------------------------------------------------- #

# Domain schema: table -> ordered (column, sql_type) pairs. Vertical toolkits
# all persist through this single schema definition to keep migrations trivial.
_SCHEMAS: dict[str, list[tuple[str, str]]] = {
    "inventory": [
        ("sku", "TEXT PRIMARY KEY"),
        ("name", "TEXT"),
        ("quantity", "INTEGER"),
        ("reorder_level", "INTEGER"),
        ("unit_cost", "REAL"),
        ("location", "TEXT"),
        ("updated_at", "REAL"),
    ],
    "procurement": [
        ("po_number", "TEXT PRIMARY KEY"),
        ("supplier", "TEXT"),
        ("items", "TEXT"),
        ("amount", "REAL"),
        ("status", "TEXT"),
        ("created_at", "REAL"),
    ],
    "finance": [
        ("entry_id", "TEXT PRIMARY KEY"),
        ("account", "TEXT"),
        ("entry_type", "TEXT"),
        ("category", "TEXT"),
        ("amount", "REAL"),
        ("created_at", "REAL"),
    ],
    "manufacturing": [
        ("bom_id", "TEXT PRIMARY KEY"),
        ("product", "TEXT"),
        ("components", "TEXT"),
        ("quantity", "INTEGER"),
        ("created_at", "REAL"),
    ],
    "marketing": [
        ("campaign_id", "TEXT PRIMARY KEY"),
        ("channel", "TEXT"),
        ("spend", "REAL"),
        ("impressions", "INTEGER"),
        ("clicks", "INTEGER"),
        ("conversions", "INTEGER"),
        ("created_at", "REAL"),
    ],
}

# Columns whose values are stored protected-at-rest.
_ENCRYPTED_COLUMNS = {
    ("finance", "amount"),
    ("procurement", "amount"),
    ("inventory", "unit_cost"),
    ("marketing", "spend"),
}


class BusinessStore:
    """Thread-safe SQLite store covering all enterprise verticals."""

    def __init__(self, db_path: Path | str | None = None) -> None:
        BUSINESS_DIR.mkdir(parents=True, exist_ok=True)
        self.db_path = Path(db_path) if db_path else DEFAULT_DB_PATH
        self._lock = threading.RLock()
        self._conn = sqlite3.connect(str(self.db_path), check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._init_schema()

    # -- lifecycle ---------------------------------------------------------- #

    def _init_schema(self) -> None:
        with self._lock:
            for table, cols in _SCHEMAS.items():
                col_sql = ", ".join(f'"{c}" {t}' for c, t in cols)
                self._conn.execute(f'CREATE TABLE IF NOT EXISTS "{table}" ({col_sql})')
            self._conn.commit()

    def close(self) -> None:
        with self._lock:
            try:
                self._conn.close()
            except Exception:
                pass

    # -- CRUD --------------------------------------------------------------- #

    def upsert(self, table: str, record: dict[str, Any]) -> dict[str, Any]:
        """Insert or replace a record in *table*. Returns the stored record."""
        if table not in _SCHEMAS:
            raise ValueError(f"unknown table '{table}'")
        known = {c for c, _ in _SCHEMAS[table]}
        row = {k: v for k, v in record.items() if k in known}
        if not row:
            raise ValueError("no valid columns supplied")
        row = self._encode(table, row)
        cols = list(row.keys())
        placeholders = ", ".join("?" for _ in cols)
        col_sql = ", ".join(f'"{c}"' for c in cols)
        with self._lock:
            self._conn.execute(
                f'INSERT OR REPLACE INTO "{table}" ({col_sql}) VALUES ({placeholders})',
                [row[c] for c in cols],
            )
            self._conn.commit()
        return self._decode(table, row)

    def insert_many(self, table: str, records: Iterable[dict[str, Any]]) -> int:
        count = 0
        for record in records:
            self.upsert(table, record)
            count += 1
        return count

    def query(
        self,
        table: str,
        *,
        where: str | None = None,
        params: Iterable[Any] = (),
        limit: int | None = None,
    ) -> list[dict[str, Any]]:
        if table not in _SCHEMAS:
            raise ValueError(f"unknown table '{table}'")
        sql = f'SELECT * FROM "{table}"'
        if where:
            sql += f" WHERE {where}"
        if limit:
            sql += f" LIMIT {int(limit)}"
        with self._lock:
            rows = self._conn.execute(sql, tuple(params)).fetchall()
        return [self._decode(table, dict(r)) for r in rows]

    def get(self, table: str, key: str) -> dict[str, Any] | None:
        if table not in _SCHEMAS:
            raise ValueError(f"unknown table '{table}'")
        pk = _SCHEMAS[table][0][0]
        rows = self.query(table, where=f'"{pk}" = ?', params=[key], limit=1)
        return rows[0] if rows else None

    def delete(self, table: str, key: str) -> bool:
        if table not in _SCHEMAS:
            raise ValueError(f"unknown table '{table}'")
        pk = _SCHEMAS[table][0][0]
        with self._lock:
            cur = self._conn.execute(f'DELETE FROM "{table}" WHERE "{pk}" = ?', (key,))
            self._conn.commit()
        return cur.rowcount > 0

    def tables(self) -> list[str]:
        return list(_SCHEMAS.keys())

    # -- codecs ------------------------------------------------------------- #

    def _encode(self, table: str, row: dict[str, Any]) -> dict[str, Any]:
        out = dict(row)
        for key in list(out.keys()):
            if (table, key) in _ENCRYPTED_COLUMNS and out[key] is not None:
                out[key] = EncryptedColumn(str(out[key]))
        return out

    def _decode(self, table: str, row: dict[str, Any]) -> dict[str, Any]:
        out = dict(row)
        for key in list(out.keys()):
            if (table, key) in _ENCRYPTED_COLUMNS and out[key] is not None:
                raw = decrypt_column(str(out[key]))
                try:
                    out[key] = float(raw)
                except (TypeError, ValueError):
                    out[key] = raw
        return out


# --------------------------------------------------------------------------- #
# Singleton accessor
# --------------------------------------------------------------------------- #

_store: BusinessStore | None = None
_store_lock = threading.Lock()


def get_store() -> BusinessStore:
    """Return the process-wide business store (created lazily)."""
    global _store
    with _store_lock:
        if _store is None:
            _store = BusinessStore()
        return _store


# --------------------------------------------------------------------------- #
# Export
# --------------------------------------------------------------------------- #

def export_rows(
    rows: list[dict[str, Any]],
    destination: Path | str,
    *,
    sheet_name: str = "Sheet1",
) -> str:
    """Export *rows* to ``.xlsx`` (openpyxl) or ``.csv`` (``.csv`` suffix).

    Falls back to CSV when writing an xlsx but ``openpyxl`` is unavailable.
    Returns the path actually written.
    """
    dest = Path(destination)
    if not rows:
        rows = []
    columns: list[str] = list(rows[0].keys()) if rows else []

    if dest.suffix.lower() in (".xlsx", ".xlsm"):
        try:
            from openpyxl import Workbook

            wb = Workbook()
            ws = wb.active
            ws.title = sheet_name[:31] or "Sheet1"
            if columns:
                ws.append(columns)
                for row in rows:
                    ws.append([_cell(row.get(c)) for c in columns])
            dest.parent.mkdir(parents=True, exist_ok=True)
            wb.save(str(dest))
            return str(dest)
        except Exception as exc:
            logger.warning("xlsx export failed (%s); falling back to CSV", exc)
            dest = dest.with_suffix(".csv")

    dest.parent.mkdir(parents=True, exist_ok=True)
    with open(dest, "w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        if columns:
            writer.writerow(columns)
            for row in rows:
                writer.writerow([_cell(row.get(c)) for c in columns])
    return str(dest)


def _cell(value: Any) -> Any:
    if isinstance(value, (dict, list, tuple)):
        return json.dumps(value, ensure_ascii=False)
    if value is None:
        return ""
    return value


def _now() -> float:
    return time.time()
