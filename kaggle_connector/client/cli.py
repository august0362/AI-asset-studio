"""The official ``kaggle`` CLI as a subprocess (D-007), plus parsers for its recorded output formats.

Credentials exist only in the child process environment, next to an isolated temporary ``KAGGLE_CONFIG_DIR``;
every inherited ``KAGGLE_*`` and ``AAS_PROFILE_*`` variable is removed first. Captured output is redacted before it
leaves :class:`KaggleCli`. Output formats were recorded with CLI 2.2.4 on 2026-11-06 (DECISIONS DF-05..DF-07).
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import tempfile
import threading
from collections.abc import Iterable, Iterator
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Protocol

_TOKEN_PATTERN = re.compile(r"KGAT_[A-Za-z0-9_\-]+")
_KEY_ASSIGNMENT = re.compile(r"(KAGGLE_(?:KEY|API_TOKEN)\s*[=:]\s*)\S+", re.IGNORECASE)
NOISE_PREFIXES = ("Warning: Looks like you're using an outdated `kaggle` version",)
USER_PLACEHOLDER = "<kaggle-user>"


# --- redaction -------------------------------------------------------------------------------------------------


class SecretRedactor:
    """Replaces the token (and any ``KGAT_…`` string) with ``[REDACTED]`` and the account name with a placeholder."""

    def __init__(self, secrets: Iterable[str] = (), users: Iterable[str] = ()) -> None:
        self._secrets = sorted({s for s in secrets if s and len(s) >= 4}, key=len, reverse=True)
        self._users = [
            re.compile(re.escape(u), re.IGNORECASE) for u in {u for u in users if u and len(u) >= 3}
        ]

    def add_user(self, user: str) -> None:
        if user and len(user) >= 3:
            self._users.append(re.compile(re.escape(user), re.IGNORECASE))

    def secrets_only(self, text: str) -> str:
        for secret in self._secrets:
            text = text.replace(secret, "[REDACTED]")
        text = _KEY_ASSIGNMENT.sub(r"\1[REDACTED]", text)
        return _TOKEN_PATTERN.sub("[REDACTED]", text)

    def __call__(self, text: str) -> str:
        text = self.secrets_only(text)
        for pattern in self._users:
            text = pattern.sub(USER_PLACEHOLDER, text)
        return text


# --- subprocess --------------------------------------------------------------------------------------------------


@dataclass(frozen=True)
class CliResult:
    """One finished CLI call. ``stdout``/``stderr`` have secrets removed; the account name is still present."""

    returncode: int | None  # None: killed after the timeout
    stdout: str
    stderr: str

    @property
    def timed_out(self) -> bool:
        return self.returncode is None

    @property
    def ok(self) -> bool:
        return self.returncode == 0

    @property
    def text(self) -> str:
        return "\n".join(part for part in (self.stdout, self.stderr) if part)


class LineStream(Protocol):
    def __iter__(self) -> Iterator[str]: ...

    def terminate(self) -> None: ...


class CliRunner(Protocol):
    """What :class:`KaggleCliClient` needs. Tests replace it with a recorded fake."""

    def run(self, args: list[str], *, timeout: float) -> CliResult: ...

    def follow(self, args: list[str]) -> LineStream: ...

    def close(self) -> None: ...


class _ProcessLines:
    def __init__(self, process: subprocess.Popen, redact: SecretRedactor) -> None:
        self._process = process
        self._redact = redact

    def __iter__(self) -> Iterator[str]:
        assert self._process.stdout is not None
        for raw in self._process.stdout:
            yield self._redact.secrets_only(raw.rstrip("\r\n"))
        self._process.wait()

    def terminate(self) -> None:
        if self._process.poll() is None:
            self._process.kill()
            self._process.wait(timeout=10)


class KaggleCli:
    """Runs ``kaggle`` for exactly one profile. Holds that profile's credentials in memory only."""

    def __init__(
        self,
        *,
        token: str | None,
        username: str,
        legacy_key: str | None = None,
        executable: str | None = None,
        redact: SecretRedactor | None = None,
    ) -> None:
        if not token and not legacy_key:
            raise ValueError("a Kaggle API token (or legacy key) is required")
        self._token = token
        self._key = legacy_key
        self._username = username
        self._executable = executable or shutil.which("kaggle") or "kaggle"
        self._redact = redact or SecretRedactor([s for s in (token, legacy_key) if s])
        self._config_dir = tempfile.mkdtemp(prefix="aas-kcfg-")
        self._children: set[subprocess.Popen] = set()
        self._lock = threading.Lock()

    def _env(self) -> dict[str, str]:
        env = {k: v for k, v in os.environ.items() if not k.upper().startswith(("KAGGLE", "AAS_PROFILE"))}
        env.update(KAGGLE_CONFIG_DIR=self._config_dir, PYTHONIOENCODING="utf-8", PYTHONUTF8="1")
        env["KAGGLE_USERNAME"] = self._username
        if self._token:
            env["KAGGLE_API_TOKEN"] = self._token
        else:
            env["KAGGLE_KEY"] = self._key or ""
        return env

    def run(self, args: list[str], *, timeout: float) -> CliResult:
        try:
            done = subprocess.run(
                [self._executable, *args],
                env=self._env(),
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=timeout,
                check=False,
            )
        except subprocess.TimeoutExpired as exc:
            out = exc.stdout.decode("utf-8", "replace") if isinstance(exc.stdout, bytes) else exc.stdout or ""
            return CliResult(None, self._redact.secrets_only(out), "timed out")
        except OSError as exc:  # CLI missing or not executable
            return CliResult(127, "", f"kaggle CLI could not be started ({exc.__class__.__name__})")
        return CliResult(
            done.returncode, self._redact.secrets_only(done.stdout), self._redact.secrets_only(done.stderr)
        )

    def follow(self, args: list[str]) -> LineStream:
        process = subprocess.Popen(
            [self._executable, *args],
            env=self._env(),
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            stdin=subprocess.DEVNULL,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        with self._lock:
            self._children.add(process)
        return _ProcessLines(process, self._redact)

    def close(self) -> None:
        with self._lock:
            children, self._children = self._children, set()
        for child in children:
            if child.poll() is None:
                child.kill()
        shutil.rmtree(self._config_dir, ignore_errors=True)


# --- parsers -----------------------------------------------------------------------------------------------------


def payload_lines(text: str) -> list[str]:
    """Output lines without the CLI's version warning and blank lines."""
    return [line for line in text.splitlines() if line.strip() and not line.startswith(NOISE_PREFIXES)]


def is_noise(line: str) -> bool:
    return line.startswith(NOISE_PREFIXES)


def _json_payload(text: str, opener: str):
    for index, line in enumerate(lines := text.splitlines()):
        if line.lstrip().startswith(opener):
            try:
                return json.loads("\n".join(lines[index:]))
            except json.JSONDecodeError:
                return None
    return None


def parse_hours(value: object) -> float | None:
    """``"25.13h"`` → 25.13. Anything else → ``None`` (never guessed)."""
    if isinstance(value, int | float) and not isinstance(value, bool):
        return float(value)
    if isinstance(value, str):
        match = re.fullmatch(r"\s*(\d+(?:\.\d+)?)\s*h?\s*", value)
        if match:
            return float(match.group(1))
    return None


def parse_reset(value: object) -> datetime | None:
    """``refreshAt`` has no zone; it is read as UTC (assumption recorded in DF-05)."""
    if not isinstance(value, str) or not value:
        return None
    try:
        moment = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return (moment if moment.tzinfo else moment.replace(tzinfo=UTC)).astimezone(UTC)


@dataclass(frozen=True)
class QuotaValues:
    gpu_total: float | None
    gpu_used: float | None
    gpu_remaining: float | None
    tpu_total: float | None
    tpu_used: float | None
    tpu_remaining: float | None
    reset_at: datetime | None


def parse_quota(stdout: str) -> QuotaValues | None:
    """``kaggle quota --format json``: rows of ``{resource, used, remaining, total, refreshAt}``; ``None`` if absent."""
    data = _json_payload(stdout, "[")
    if not isinstance(data, list):
        return None
    rows = {str(r.get("resource", "")).upper(): r for r in data if isinstance(r, dict)}
    if not rows:
        return None
    gpu, tpu = rows.get("GPU", {}), rows.get("TPU", {})
    return QuotaValues(
        gpu_total=parse_hours(gpu.get("total")),
        gpu_used=parse_hours(gpu.get("used")),
        gpu_remaining=parse_hours(gpu.get("remaining")),
        tpu_total=parse_hours(tpu.get("total")),
        tpu_used=parse_hours(tpu.get("used")),
        tpu_remaining=parse_hours(tpu.get("remaining")),
        reset_at=parse_reset(gpu.get("refreshAt") or tpu.get("refreshAt")),
    )


_STATUS_LINE = re.compile(r'has status "(?:KernelWorkerStatus\.)?([A-Za-z_]+)"')
_FAILURE_LINE = re.compile(r'^Failure message: "(.*)"\s*$', re.MULTILINE)


def parse_kernel_status(text: str) -> tuple[str, str | None] | None:
    """``owner/slug has status "KernelWorkerStatus.RUNNING"`` → ``("RUNNING", failure_message)``."""
    match = _STATUS_LINE.search(text)
    if not match:
        return None
    failure = _FAILURE_LINE.search(text)
    return match.group(1).upper(), failure.group(1) if failure else None


_PUSH_OK = re.compile(r"Kernel version (\d+)? ?successfully pushed")
_CODE_URL = re.compile(r"kaggle\.com/code/([^/\s]+)/([^/\s]+)")


@dataclass(frozen=True)
class PushResult:
    version: int | None
    owner: str | None
    slug: str | None


def parse_push(text: str) -> PushResult | None:
    """``None`` unless the CLI reported success. Push errors print with exit code 0, so the text decides."""
    ok = _PUSH_OK.search(text)
    if not ok or "Kernel push error" in text or "not valid dataset sources" in text:
        return None
    url = _CODE_URL.search(text)
    return PushResult(
        version=int(ok.group(1)) if ok.group(1) else None,
        owner=url.group(1) if url else None,
        slug=url.group(2) if url else None,
    )


_CONFIG_USER = re.compile(r"^- username: (\S+)\s*$", re.MULTILINE)
_CONFIG_AUTH = re.compile(r"^- auth_method: (\S+)\s*$", re.MULTILINE)


def parse_config_user(text: str) -> tuple[str | None, str | None]:
    """``kaggle config view`` → (account username resolved from the credentials, auth method)."""
    user, method = _CONFIG_USER.search(text), _CONFIG_AUTH.search(text)
    value = user.group(1) if user else None
    return (None if value in (None, "None") else value), (method.group(1) if method else None)


def parse_dataset_status(text: str) -> str | None:
    """``kaggle datasets status`` prints one lower-case word (``ready``, ``failed``, ``blobs_received`` …)."""
    for line in reversed(payload_lines(text)):
        word = line.strip()
        if re.fullmatch(r"[a-z_]+", word):
            return word
    return None


def parse_log_blob(stdout: str) -> list[str] | None:
    """``kaggle kernels logs`` (one-shot): a JSON array of ``{stream_name, time, data}``. → log lines, in order.

    Empty while the session runs (the blob is persisted at the end). ``None`` if the output is not that format.
    """
    data = _json_payload(stdout, "[")
    if not isinstance(data, list):
        return None
    lines: list[str] = []
    for event in data:
        if isinstance(event, dict) and isinstance(event.get("data"), str):
            lines.extend(event["data"].splitlines())
    return lines


# --- failure classification ----------------------------------------------------------------------------------------

_RATE = re.compile(r"\b429\b|Too Many Requests|rate limit", re.IGNORECASE)
_AUTH = re.compile(
    r"\b401\b|Unauthorized|Unauthenticated|invalid (?:api )?(?:token|credentials)", re.IGNORECASE
)
_DENIED = re.compile(r"Permission '[a-z.]+' was denied|\b403\b|Forbidden", re.IGNORECASE)
_NETWORK = re.compile(
    r"Connection aborted|RemoteDisconnected|ConnectionError|Connection reset|Max retries exceeded|"
    r"timed out|Read timed out|Temporary failure in name resolution|NameResolutionError|"
    r"\b50[0234]\b|Server Error|Bad Gateway|Service Unavailable|SSLError|ChunkedEncodingError",
    re.IGNORECASE,
)
_QUOTA = re.compile(r"quota", re.IGNORECASE)
_OLD_CLI = re.compile(r"invalid choice: 'quota'|unrecognized arguments: --format", re.IGNORECASE)


@dataclass(frozen=True)
class Failure:
    kind: str  # rate_limited | auth | denied | network | quota | unsupported | other
    transient: bool


def classify(result: CliResult) -> Failure:
    text = result.text
    if result.timed_out:
        return Failure("network", True)
    if _OLD_CLI.search(text):
        return Failure("unsupported", False)
    if _RATE.search(text):
        return Failure("rate_limited", True)
    if _AUTH.search(text):
        return Failure("auth", False)
    if _DENIED.search(text):
        return Failure("denied", False)
    if _NETWORK.search(text):
        return Failure("network", True)
    if _QUOTA.search(text):
        return Failure("quota", False)
    return Failure("other", False)
