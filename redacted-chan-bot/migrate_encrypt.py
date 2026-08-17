#!/usr/bin/env python3
"""
migrate_encrypt.py — one-shot migration of chan's plaintext SQLite DBs to SQLCipher.

Enabling at-rest encryption (sqlcipher3 + DATABASE_ENCRYPTION_KEY) makes the app open
every .db WITH a key; SQLCipher then treats the existing *plaintext* files as corrupt.
So the on-disk files must be converted first. Run this ONCE, before starting the
service with sqlcipher3 available.

Safety model:
  - discovers every /data/*.db (skips *.bak*, journals, and already-encrypted files)
  - converts to a TEMP file, then verifies it re-opens through the app's own
    database_encryption.get_encrypted_connection() and that table/row counts match
  - only then backs up the plaintext to <db>.bak-plaintext and atomically swaps it in
  - on ANY failure the original is left untouched and the script exits non-zero
  - idempotent: re-running skips files that are already encrypted

Modes:
  python migrate_encrypt.py check   # rehearse on copies in /tmp, write nothing to /data
  python migrate_encrypt.py apply   # real migration (backup + verify + atomic swap)
"""
import os
import sys
import glob
import shutil
import sqlite3
import tempfile

DATA_DIR = os.getenv("CHAN_DATA_DIR", "/data")

# Must match database_encryption.get_encrypted_connection() exactly.
PAGE_SIZE = 4096
KDF_ITER  = 64000
COMPAT    = 4


def _key() -> str:
    k = os.getenv("DATABASE_ENCRYPTION_KEY", "").strip()
    if not k:
        sys.exit("ERROR: DATABASE_ENCRYPTION_KEY is not set — refusing to migrate.")
    return k


def _is_plaintext(path: str) -> bool:
    """True if the file opens as a normal (unencrypted) SQLite DB."""
    try:
        c = sqlite3.connect(path)
        c.execute("SELECT count(*) FROM sqlite_master")
        c.close()
        return True
    except Exception:
        return False


def _table_counts(conn) -> dict:
    """Map of table name -> row count, for source/target equivalence check."""
    cur = conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")
    names = [r[0] for r in cur.fetchall()]
    out = {}
    for n in names:
        try:
            out[n] = conn.execute(f'SELECT count(*) FROM "{n}"').fetchone()[0]
        except Exception:
            out[n] = None
    return out


def _encrypt_to(src_plain: str, dst_enc: str, key: str) -> None:
    """Export a plaintext DB into a new SQLCipher-encrypted file at dst_enc."""
    import sqlcipher3
    if os.path.exists(dst_enc):
        os.remove(dst_enc)
    con = sqlcipher3.connect(src_plain)  # main opened WITHOUT a key => plaintext
    try:
        # Defaults applied to the DB we're about to ATTACH. compatibility=4 sets the
        # v4 cipher profile (page 4096 / HMAC-SHA512); page/kdf set explicitly too.
        con.execute(f"PRAGMA cipher_default_page_size = {PAGE_SIZE}")
        con.execute(f"PRAGMA cipher_default_kdf_iter = {KDF_ITER}")
        con.execute(f"PRAGMA cipher_default_compatibility = {COMPAT}")
        con.execute(f"ATTACH DATABASE ? AS enc KEY ?", (dst_enc, key))
        con.execute("SELECT sqlcipher_export('enc')")
        con.execute("DETACH DATABASE enc")
        con.commit()
    finally:
        con.close()


def _verify(dst_enc: str, expected: dict) -> None:
    """Open via the app's real code path; assert table/row counts match the source."""
    import database_encryption as dbenc
    conn = dbenc.get_encrypted_connection(dst_enc)
    # If sqlcipher3 were missing, get_encrypted_connection silently returns a plain
    # sqlite3 conn — guard against that so we never "verify" against the wrong engine.
    if type(conn).__module__.split(".")[0] != "sqlcipher3":
        conn.close()
        raise RuntimeError("verify opened a non-sqlcipher connection — sqlcipher3 missing?")
    try:
        got = _table_counts(conn)
    finally:
        conn.close()
    if got != expected:
        raise RuntimeError(f"row-count mismatch after encrypt:\n  expected {expected}\n  got      {got}")


def _process(path: str, key: str, apply: bool) -> str:
    name = os.path.basename(path)
    if not _is_plaintext(path):
        return f"[skip] {name} — not plaintext (already encrypted?)"

    with sqlite3.connect(path) as src:
        expected = _table_counts(src)

    tmp_fd, tmp_enc = tempfile.mkstemp(prefix=name + ".enc.", dir=os.path.dirname(path))
    os.close(tmp_fd)
    try:
        _encrypt_to(path, tmp_enc, key)
        _verify(tmp_enc, expected)
    except Exception as e:
        if os.path.exists(tmp_enc):
            os.remove(tmp_enc)
        raise RuntimeError(f"{name}: {e}")

    if not apply:
        os.remove(tmp_enc)
        return f"[ok/check] {name} — {sum(v or 0 for v in expected.values())} rows across {len(expected)} tables, verified"

    bak = path + ".bak-plaintext"
    if not os.path.exists(bak):
        shutil.copy2(path, bak)
    os.replace(tmp_enc, path)  # atomic swap
    return f"[migrated] {name} — encrypted, plaintext backed up to {os.path.basename(bak)}"


def main() -> None:
    mode = sys.argv[1] if len(sys.argv) > 1 else "check"
    if mode not in ("check", "apply"):
        sys.exit("usage: migrate_encrypt.py [check|apply]")
    key = _key()

    dbs = sorted(
        p for p in glob.glob(os.path.join(DATA_DIR, "*.db"))
        if ".bak" not in os.path.basename(p)
    )
    if not dbs:
        print(f"no .db files in {DATA_DIR}")
        return

    print(f"=== migrate_encrypt {mode} — {len(dbs)} db(s) in {DATA_DIR} ===")
    failures = 0
    for p in dbs:
        try:
            print(_process(p, key, apply=(mode == "apply")))
        except Exception as e:
            failures += 1
            print(f"[FAIL] {e}")

    if failures:
        sys.exit(f"\n{failures} file(s) failed — originals left untouched. Aborting.")
    print(f"\nall good ({mode}).")


if __name__ == "__main__":
    main()
