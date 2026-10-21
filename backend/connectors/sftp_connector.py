"""SFTP / FTPS / FTP connector — the universal, zero-cost batch route.

Almost every ERP, bank, retail or logistics system can drop a scheduled export on
an (S)FTP server. KAIROS keeps this fast by design:

* only files it has not processed yet are downloaded (name + size + mtime state)
* files still being written are skipped (min_age_seconds, or a `.done` marker)
* compressed exports (.gz / .zst) and Parquet are read directly
* exports should contain aggregated KPIs — a few KB per cycle, not raw dumps;
  if raw data is all a client has, use `aggregate` (or the edge agent) so it is
  reduced to KPIs before it is stored

Use SFTP or FTPS in production; plain FTP sends credentials unencrypted.
"""
from __future__ import annotations

import fnmatch
import ftplib
import logging
import posixpath
import tempfile
import time
from pathlib import Path

import pandas as pd

from backend.connectors.base import BaseConnector, ConnectorError, parse_since, secret, to_canonical
from backend.connectors.file_connector import load_files, post_aggregate_config

logger = logging.getLogger("kairos.connector.sftp")


class _Remote:
    """Tiny common interface over paramiko SFTP and ftplib."""

    def __init__(self, cfg: dict):
        self.cfg      = cfg
        self.protocol = cfg.get("protocol", "sftp").lower()
        self.host     = cfg.get("host")
        if not self.host:
            raise ConnectorError("'host' is required")
        self.user     = cfg.get("username", "anonymous")
        self.password = secret(cfg, "password")
        self.timeout  = int(cfg.get("timeout", 30))
        self._ssh = self._sftp = self._ftp = None

    def __enter__(self):
        if self.protocol == "sftp":
            import paramiko
            self._ssh = paramiko.SSHClient()
            self._ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            self._ssh.connect(
                self.host, port=int(self.cfg.get("port", 22)), username=self.user,
                password=self.password or None, key_filename=self.cfg.get("key_file") or None,
                timeout=self.timeout, allow_agent=False, look_for_keys=False,
            )
            self._sftp = self._ssh.open_sftp()
        elif self.protocol in ("ftp", "ftps"):
            cls = ftplib.FTP_TLS if self.protocol == "ftps" else ftplib.FTP
            self._ftp = cls(timeout=self.timeout)
            self._ftp.connect(self.host, int(self.cfg.get("port", 21)))
            self._ftp.login(self.user, self.password)
            if self.protocol == "ftps":
                self._ftp.prot_p()
        else:
            raise ConnectorError(f"Unknown protocol '{self.protocol}' (sftp | ftps | ftp)")
        return self

    def __exit__(self, *exc):
        for closer in (self._sftp, self._ssh):
            if closer:
                closer.close()
        if self._ftp:
            try:
                self._ftp.quit()
            except Exception:  # noqa: BLE001
                self._ftp.close()

    def listdir(self, folder: str) -> list[dict]:
        """[{name, size, mtime}] for regular files in folder."""
        if self._sftp:
            import stat
            return [
                {"name": a.filename, "size": a.st_size, "mtime": a.st_mtime}
                for a in self._sftp.listdir_attr(folder) if stat.S_ISREG(a.st_mode or 0)
            ]
        files = []
        try:
            for name, facts in self._ftp.mlsd(folder, facts=["type", "size", "modify"]):
                if facts.get("type") == "file":
                    mtime = time.mktime(time.strptime(facts["modify"][:14], "%Y%m%d%H%M%S")) if "modify" in facts else 0
                    files.append({"name": name, "size": int(facts.get("size", 0)), "mtime": mtime})
        except ftplib.error_perm:  # server without MLSD
            for path in self._ftp.nlst(folder):
                name = posixpath.basename(path)
                try:
                    size = self._ftp.size(posixpath.join(folder, name)) or 0
                except ftplib.error_perm:
                    continue
                files.append({"name": name, "size": size, "mtime": 0})
        return files

    def download(self, remote: str, local: Path) -> None:
        if self._sftp:
            self._sftp.get(remote, str(local))
        else:
            with open(local, "wb") as fh:
                self._ftp.retrbinary(f"RETR {remote}", fh.write, blocksize=1 << 20)


class SFTPConnector(BaseConnector):
    type        = "sftp"
    label       = "SFTP / FTPS / FTP"
    description = "Fetches only new export files (compressed CSV/Parquet) from an (S)FTP folder."
    CONFIG_FIELDS = [
        {"name": "protocol", "label": "Protocol", "type": "select", "options": ["sftp", "ftps", "ftp"],
         "required": True, "default": "sftp"},
        {"name": "host", "label": "Host", "type": "text", "required": True},
        {"name": "port", "label": "Port", "type": "number", "required": False},
        {"name": "username", "label": "Username", "type": "text", "required": True},
        {"name": "password_env", "label": "Password env var", "type": "text", "required": False,
         "help": "Name of the env var that holds the password (kept out of config)"},
        {"name": "password", "label": "Password (dev only)", "type": "password", "required": False, "secret": True},
        {"name": "folder", "label": "Remote folder", "type": "text", "required": True, "default": "/"},
        {"name": "pattern", "label": "File pattern", "type": "text", "required": False, "default": "*.csv*"},
    ]

    def _candidates(self, remote: _Remote, processed: dict) -> list[dict]:
        folder   = self.config.get("folder", "/")
        pattern  = self.config.get("pattern", "*")
        min_age  = float(self.config.get("min_age_seconds", 0))
        marker   = self.config.get("require_done_marker", False)
        listing  = remote.listdir(folder)
        names    = {f["name"] for f in listing}
        now      = time.time()
        out = []
        for f in sorted(listing, key=lambda x: (x["mtime"], x["name"])):
            if not fnmatch.fnmatch(f["name"], pattern) or f["name"].endswith(".done"):
                continue
            if marker and f"{f['name']}.done" not in names:
                continue                      # producer has not finished writing yet
            if min_age and f["mtime"] and now - f["mtime"] < min_age:
                continue                      # still being uploaded
            seen = processed.get(f["name"])
            if seen and seen.get("size") == f["size"] and seen.get("mtime") == f["mtime"]:
                continue                      # already ingested, unchanged
            out.append(f)
        return out

    def fetch_raw(self, state: dict):
        processed = dict(state.get("files", {}))
        frames, total_bytes, names, aggregated = [], 0, [], False
        t0 = time.perf_counter()
        with _Remote(self.config) as remote, tempfile.TemporaryDirectory(prefix="kairos_sftp_") as tmp:
            todo = self._candidates(remote, processed)
            max_files = int(self.config.get("max_files_per_run", 500))
            for f in todo[:max_files]:
                remote_path = posixpath.join(self.config.get("folder", "/"), f["name"])
                local = Path(tmp) / f["name"]
                remote.download(remote_path, local)
                total_bytes += local.stat().st_size
                df, aggregated = load_files([str(local)], self.config, since=None)
                frames.append(df)
                names.append(f["name"])
                processed[f["name"]] = {"size": f["size"], "mtime": f["mtime"]}
        self._aggregated = aggregated
        raw = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()
        new_state = {**state, "files": processed}
        elapsed = time.perf_counter() - t0
        return raw, new_state, {
            "files": len(names), "file_names": names[:20], "bytes": total_bytes,
            "transfer_seconds": round(elapsed, 3),
        }

    def fetch(self, state=None):
        # files are tracked individually, so don't drop rows older than the timestamp watermark
        self.config.setdefault("incremental", False)
        return super().fetch(state)

    def canonicalise(self, raw: pd.DataFrame) -> pd.DataFrame:
        if raw.empty:
            return to_canonical(raw, self.config)
        if getattr(self, "_aggregated", False):
            return to_canonical(raw, post_aggregate_config(self.config))
        return to_canonical(raw, self.config)

    def preview(self, limit: int = 20) -> pd.DataFrame:
        with _Remote(self.config) as remote, tempfile.TemporaryDirectory(prefix="kairos_sftp_") as tmp:
            todo = self._candidates(remote, {})
            if not todo:
                raise ConnectorError("Connected, but no files match the pattern")
            f = todo[-1]
            local = Path(tmp) / f["name"]
            remote.download(posixpath.join(self.config.get("folder", "/"), f["name"]), local)
            df, self._aggregated = load_files([str(local)], self.config, limit=limit)
            return df
