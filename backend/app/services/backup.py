"""Backup and restore of all plant data and media as a single zip.

Archive layout::

    manifest.json          format, versions, row counts, user id -> username map
    data/<table>.json      a JSON list of rows per table
    media/<path>           originals and thumbnails, at their path relative to the media dir

Restoring replaces every backed-up table and the media store. Users, API tokens and integration
credentials are never written to a backup, so they stay as they are on the server you restore to.
References to users (who logged an event, uploaded a photo...) are matched up by username.
"""

import json
import logging
import shutil
import uuid
import zipfile
from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path
from typing import Any

from sqlalchemy import Column, Connection, Date, DateTime, Table, bindparam, select, text
from sqlalchemy.types import TypeDecorator
from sqlalchemy.exc import DataError, IntegrityError
from sqlalchemy.orm import Session

from app import __version__
from app.config import get_settings
from app.db import Base, get_engine, new_session, utcnow
from app.models import Backup, User
from app.services.media import media_root

log = logging.getLogger("plantasaurus.backup")

FORMAT = "plantasaurus-backup"
FORMAT_VERSION = 1

# Every table must appear in exactly one of these; tests/test_backup.py enforces it so a new
# table can't be left out of backups (or leak secrets into them) by accident.
BACKED_UP_TABLES = (
    "plants",
    "areas",
    "spots",
    "positions",
    "plant_instances",
    "placements",
    "instance_events",
    "assessments",
    "media",
    "custom_field_definitions",
    "ha_devices",
)
EXCLUDED_TABLES = {
    "users": "accounts belong to the server, not the backup",
    "api_tokens": "secrets",
    "ha_config": "holds the Home Assistant access token",
    "opb_config": "holds the Open Plantbook client secret",
    "mcp_config": "a server setting (MCP on/off), kept as it is on the server you restore to",
    "backups": "the backup list itself",
}

# Friendly names for the counts shown in the UI.
COUNT_LABELS = {
    "plants": "plants",
    "plant_instances": "my plants",
    "areas": "areas",
    "spots": "spots",
    "instance_events": "events",
    "assessments": "assessments",
    "media": "photos",
    "custom_field_definitions": "custom fields",
}


class BackupError(Exception):
    """A backup archive can't be read or restored. The message is shown to the user."""


# --------------------------------------------------------------------------------------- tables


def backups_dir() -> Path:
    path = get_settings().data_dir / "backups"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _tables() -> list[Table]:
    return [Base.metadata.tables[name] for name in BACKED_UP_TABLES]


def _deferred_columns(table: Table) -> list[Column]:
    """Nullable foreign keys within the backed-up set.

    The schema has FK cycles (areas -> media -> events -> instances -> spots -> areas), so rows
    are inserted with these empty and filled in once every row exists.
    """
    return [
        col
        for col in table.columns
        if col.nullable and any(fk.column.table.name in BACKED_UP_TABLES for fk in col.foreign_keys)
    ]


def _user_columns(table: Table) -> list[Column]:
    return [col for col in table.columns if any(fk.column.table.name == "users" for fk in col.foreign_keys)]


def _insert_order() -> list[Table]:
    """Backed-up tables ordered so required (non-nullable) foreign keys point backwards."""
    tables = {t.name: t for t in _tables()}
    deps = {
        name: {
            fk.column.table.name
            for col in t.columns
            if not col.nullable
            for fk in col.foreign_keys
            if fk.column.table.name in tables and fk.column.table.name != name
        }
        for name, t in tables.items()
    }
    ordered: list[Table] = []
    while deps:
        ready = sorted(n for n, d in deps.items() if not d)
        if not ready:  # pragma: no cover - would need a cycle of NOT NULL foreign keys
            raise RuntimeError(f"Cyclic required foreign keys between {sorted(deps)}")
        for name in ready:
            ordered.append(tables[name])
            del deps[name]
        for d in deps.values():
            d.difference_update(ready)
    return ordered


def _sql_type(col: Column) -> Any:
    """The underlying SQL type, looking through TypeDecorators such as UTCDateTime."""
    return col.type.impl_instance if isinstance(col.type, TypeDecorator) else col.type


def _to_json(value: Any) -> Any:
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    return value


def _from_json(col: Column, value: Any) -> Any:
    if value is None or not isinstance(value, str):
        return value
    kind = _sql_type(col)
    if isinstance(kind, DateTime):
        return datetime.fromisoformat(value)
    if isinstance(kind, Date):
        return date.fromisoformat(value)
    return value


def _schema_revision(conn: Connection) -> str | None:
    try:
        return conn.execute(text("SELECT version_num FROM alembic_version")).scalar()
    except Exception:  # pragma: no cover - database created without migrations
        return None


def _known_revisions() -> set[str]:
    from alembic.config import Config
    from alembic.script import ScriptDirectory

    cfg = Config()
    cfg.set_main_option("script_location", str(Path(__file__).resolve().parents[2] / "alembic"))
    return {script.revision for script in ScriptDirectory.from_config(cfg).walk_revisions()}


def _safe_media_path(rel: str) -> Path | None:
    root = media_root().resolve()
    path = (root / rel).resolve()
    return path if path.is_relative_to(root) and path != root else None


def _media_rels(rows: Iterable[dict[str, Any]]) -> list[str]:
    return [rel for row in rows for rel in (row.get("path"), row.get("thumb_path")) if rel]


# --------------------------------------------------------------------------------------- backup


def write_archive(dest: Path) -> dict[str, int]:
    """Write a backup of the current data to `dest`. Returns per-table and media counts."""
    counts: dict[str, int] = {}
    tmp = dest.with_name(dest.name + ".partial")
    try:
        # One read transaction, so every table comes from the same snapshot.
        with get_engine().connect() as conn, conn.begin(), zipfile.ZipFile(
            tmp, "w", compression=zipfile.ZIP_DEFLATED
        ) as zf:
            media_rows: list[dict[str, Any]] = []
            for table in _tables():
                rows = [
                    {k: _to_json(v) for k, v in row._mapping.items()}
                    for row in conn.execute(select(table).order_by(*table.primary_key.columns))
                ]
                counts[table.name] = len(rows)
                zf.writestr(f"data/{table.name}.json", json.dumps(rows, ensure_ascii=False))
                if table.name == "media":
                    media_rows = rows

            files = missing = 0
            for rel in _media_rels(media_rows):
                path = _safe_media_path(rel)
                if path is None or not path.is_file():
                    missing += 1
                    continue
                # Images are already compressed.
                zf.write(path, f"media/{rel}", compress_type=zipfile.ZIP_STORED)
                files += 1
            counts["media_files"] = files
            if missing:
                counts["missing_media_files"] = missing

            users = {str(uid): name for uid, name in conn.execute(select(User.id, User.username))}
            manifest = {
                "format": FORMAT,
                "format_version": FORMAT_VERSION,
                "app_version": __version__,
                "schema_revision": _schema_revision(conn),
                "created_at": utcnow().isoformat(),
                "counts": counts,
                "users": users,
            }
            zf.writestr("manifest.json", json.dumps(manifest, indent=2, ensure_ascii=False))
        tmp.replace(dest)
    finally:
        tmp.unlink(missing_ok=True)
    return counts


def start_backup(db: Session, user: User | None, note: str | None = None) -> Backup:
    if db.scalar(select(Backup.id).where(Backup.status.in_(("pending", "running"))).limit(1)):
        raise BackupError("A backup is already being built")
    backup = Backup(status="pending", created_by_id=user.id if user else None, note=note, counts={})
    db.add(backup)
    db.commit()
    return backup


def run_backup(backup_id: int) -> None:
    """Build the zip for a pending backup. Runs outside the request, with its own session."""
    db = new_session()
    try:
        backup = db.get(Backup, backup_id)
        if backup is None or backup.status != "pending":
            return
        backup.status = "running"
        db.commit()
        filename = f"plantasaurus-{utcnow():%Y%m%d-%H%M%S}-{backup.id}.zip"
        try:
            counts = write_archive(backups_dir() / filename)
        except Exception as exc:
            log.exception("Backup %s failed", backup_id)
            backup.status, backup.error = "failed", str(exc) or exc.__class__.__name__
        else:
            backup.status, backup.filename, backup.counts = "ready", filename, counts
            backup.size_bytes = (backups_dir() / filename).stat().st_size
        backup.completed_at = utcnow()
        db.commit()
    finally:
        db.close()


def backup_path(backup: Backup) -> Path | None:
    if not backup.filename:
        return None
    path = backups_dir() / backup.filename
    return path if path.is_file() else None


def delete_backup(db: Session, backup: Backup) -> None:
    if backup.status in ("pending", "running"):
        raise BackupError("This backup is still being built")
    if path := backup_path(backup):
        path.unlink()
    db.delete(backup)
    db.commit()


def recover_interrupted() -> None:
    """On startup: jobs that were running when the server stopped will never finish."""
    db = new_session()
    try:
        for backup in db.scalars(select(Backup).where(Backup.status.in_(("pending", "running")))):
            backup.status, backup.error, backup.completed_at = "failed", "Interrupted by a server restart", utcnow()
        db.commit()
    finally:
        db.close()
    for leftover in backups_dir().glob("*.partial"):
        leftover.unlink(missing_ok=True)


# -------------------------------------------------------------------------------------- restore


@dataclass
class Archive:
    manifest: dict[str, Any]
    tables: dict[str, list[dict[str, Any]]]
    media_entries: set[str] = field(default_factory=set)


def read_archive(zf: zipfile.ZipFile) -> Archive:
    names = set(zf.namelist())

    def load(name: str) -> Any:
        try:
            return json.loads(zf.read(name))
        except (KeyError, ValueError) as exc:
            raise BackupError(f"{name} is missing or damaged") from exc

    if "manifest.json" not in names:
        raise BackupError("This is not a Plantasaurus backup (no manifest.json)")
    manifest = load("manifest.json")
    if not isinstance(manifest, dict) or manifest.get("format") != FORMAT:
        raise BackupError("This is not a Plantasaurus backup")
    if not isinstance(manifest.get("format_version"), int) or manifest["format_version"] > FORMAT_VERSION:
        raise BackupError("This backup was made by a newer version of Plantasaurus. Upgrade, then restore it.")
    revision = manifest.get("schema_revision")
    if revision and revision not in _known_revisions():
        raise BackupError("This backup was made by a newer version of Plantasaurus. Upgrade, then restore it.")

    tables: dict[str, list[dict[str, Any]]] = {}
    for name in BACKED_UP_TABLES:
        member = f"data/{name}.json"
        rows = load(member) if member in names else []
        if not isinstance(rows, list) or not all(isinstance(r, dict) for r in rows):
            raise BackupError(f"{member} is damaged")
        tables[name] = rows

    for rel in _media_rels(tables["media"]):
        if not isinstance(rel, str) or _safe_media_path(rel) is None:
            raise BackupError(f"Backup contains an invalid media path: {rel!r}")
    media_entries = {n.removeprefix("media/") for n in names if n.startswith("media/") and not n.endswith("/")}
    return Archive(manifest=manifest, tables=tables, media_entries=media_entries)


def _prepare_rows(
    table: Table, rows: list[dict[str, Any]], user_map: dict[int, int | None]
) -> list[dict[str, Any]]:
    """Keep only columns this schema has (older backups may lack some; defaults fill them in)."""
    if not rows:
        return []
    present = [c for c in table.columns if c.name in rows[0]]
    user_cols = {c.name for c in _user_columns(table)}
    out = []
    for row in rows:
        values = {c.name: _from_json(c, row.get(c.name)) for c in present}
        for name in user_cols & values.keys():
            values[name] = user_map.get(values[name]) if values[name] is not None else None
        out.append(values)
    return out


def _replace_tables(conn: Connection, archive: Archive, user_map: dict[int, int | None]) -> dict[str, int]:
    order = _insert_order()

    # Clear: unlink everything first so delete order can't trip over foreign keys.
    for table in order:
        if cols := _deferred_columns(table):
            conn.execute(table.update().values({c.name: None for c in cols}))
    for table in reversed(order):
        conn.execute(table.delete())

    counts: dict[str, int] = {}
    deferred_values: list[tuple[Table, list[Column], list[dict[str, Any]]]] = []
    for table in order:
        rows = _prepare_rows(table, archive.tables.get(table.name, []), user_map)
        counts[table.name] = len(rows)
        if not rows:
            continue
        deferred = [c for c in _deferred_columns(table) if c.name in rows[0]]
        if deferred:
            deferred_values.append((table, deferred, rows))
            rows = [{**r, **{c.name: None for c in deferred}} for r in rows]
        conn.execute(table.insert(), rows)

    # Now every row exists, put the links back. Columns with onupdate (updated_at) are set to
    # their backed-up value too, or the update would stamp them with the current time.
    for table, deferred, rows in deferred_values:
        pk = list(table.primary_key.columns)
        cols = deferred + [c for c in table.columns if c.onupdate is not None and c.name in rows[0]]
        stmt = table.update().where(*(c == bindparam(f"_pk_{c.name}") for c in pk))
        stmt = stmt.values({c.name: bindparam(f"_v_{c.name}") for c in cols})
        params = [
            {**{f"_pk_{c.name}": r[c.name] for c in pk}, **{f"_v_{c.name}": r[c.name] for c in cols}}
            for r in rows
            if any(r[c.name] is not None for c in deferred)
        ]
        if params:
            conn.execute(stmt, params)
    return counts


def _prune_media(keep: set[str]) -> None:
    """Remove files in the media dir that no media row refers to any more."""
    root = media_root().resolve()
    keep_paths = {p for rel in keep if (p := _safe_media_path(rel))}
    for path in sorted(root.rglob("*"), reverse=True):
        if path.is_file() and path not in keep_paths:
            path.unlink(missing_ok=True)
        elif path.is_dir() and not any(path.iterdir()):
            path.rmdir()


def restore_archive(zip_path: Path) -> dict[str, int]:
    """Replace all plant data and media with the contents of a backup zip."""
    try:
        zf = zipfile.ZipFile(zip_path)
    except (zipfile.BadZipFile, OSError) as exc:
        raise BackupError("The file is not a valid zip") from exc

    with zf:
        archive = read_archive(zf)

        engine = get_engine()
        with engine.connect() as conn:
            current_users = {name: uid for uid, name in conn.execute(select(User.id, User.username))}
        user_map = {
            int(old_id): current_users.get(name) for old_id, name in (archive.manifest.get("users") or {}).items()
        }

        # Extract media first; files have unique names, so this doesn't disturb current data.
        # If the database part fails, the files we added are removed again.
        added: list[Path] = []
        files = 0
        try:
            for rel in _media_rels(archive.tables["media"]):
                if rel not in archive.media_entries:
                    continue
                dest = _safe_media_path(rel)
                assert dest is not None  # checked in read_archive
                if not dest.exists():
                    added.append(dest)
                dest.parent.mkdir(parents=True, exist_ok=True)
                with zf.open(f"media/{rel}") as src, open(dest, "wb") as out:
                    shutil.copyfileobj(src, out)
                files += 1

            with engine.begin() as conn:
                counts = _replace_tables(conn, archive, user_map)
        except Exception as exc:
            for path in added:
                path.unlink(missing_ok=True)
            if isinstance(exc, (IntegrityError, DataError)):
                raise BackupError(f"The backup's data is inconsistent, so nothing was restored ({exc.orig})") from exc
            raise

    _prune_media(set(_media_rels(archive.tables["media"])))
    counts["media_files"] = files
    return counts


def restore_with_safety_backup(db: Session, user: User, zip_path: Path) -> tuple[dict[str, int], int]:
    """Back up the current data, then restore. Returns restore counts and the safety backup's id."""
    try:
        with zipfile.ZipFile(zip_path) as zf:
            read_archive(zf)  # fail fast, before taking a safety backup
    except (zipfile.BadZipFile, OSError) as exc:
        raise BackupError("The file is not a valid zip") from exc

    safety = start_backup(db, user, note="Automatic, before restore")
    run_backup(safety.id)
    db.refresh(safety)
    if safety.status != "ready":
        raise BackupError(f"Could not back up the current data first, so nothing was restored: {safety.error}")
    return restore_archive(zip_path), safety.id


def upload_path() -> Path:
    return backups_dir() / f".upload-{uuid.uuid4().hex}.zip.partial"
