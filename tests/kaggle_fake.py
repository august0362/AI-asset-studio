"""A recorded-format fake of the ``kaggle`` CLI for offline tests of ``KaggleCliClient``.

It answers with the output formats recorded in ``tests/fixtures/kaggle_cli`` and really executes pushed kernels:
the package embedded in ``aas_kernel.py`` is unpacked into a sandbox (``/kaggle/input`` and ``/kaggle/working`` are
mapped to local folders) and ``runner.py`` runs as a subprocess, so the generated script is tested end to end.
"""

from __future__ import annotations

import ast
import base64
import json
import os
import shutil
import subprocess
import sys
import threading
from collections.abc import Iterator
from dataclasses import dataclass, field
from pathlib import Path

from kaggle_connector.client.cli import CliResult

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "kaggle_cli"
WARNING = (
    "Warning: Looks like you're using an outdated `kaggle` version (installed: 2.2.4), "
    "please consider upgrading to the latest version (2.2.5)"
)


def fixture(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


@dataclass
class FakeKernel:
    slug: str
    metadata: dict
    source: str
    sandbox: Path
    accelerator: str | None
    timeout: str | None
    lines: list[str] = field(default_factory=list)
    state: str = "QUEUED"
    status_calls: int = 0
    done: threading.Event = field(default_factory=threading.Event)


class _Lines:
    def __init__(self, kernel: FakeKernel, extra: list[str]) -> None:
        self._kernel = kernel
        self._extra = extra
        self.terminated = False

    def __iter__(self) -> Iterator[str]:
        yield WARNING
        sent = 0
        while not self.terminated:
            lines = self._kernel.lines
            while sent < len(lines):
                yield lines[sent]
                sent += 1
            if self._kernel.done.is_set() and sent >= len(self._kernel.lines):
                break
            self._kernel.done.wait(0.02)
        yield from self._extra

    def terminate(self) -> None:
        self.terminated = True


class FakeKaggleCli:
    """Implements ``CliRunner``. ``owner`` is the account the fake credentials resolve to."""

    def __init__(
        self,
        root: Path,
        *,
        owner: str = "aas-test-user",
        quota: str | None = "quota.json.txt",
        denied_status_calls: int = 1,
        queued_status_calls: int = 1,
        fail_push: str | None = None,
        status_errors: int = 0,
        secret_echo: str | None = None,
        break_entry: bool = False,
    ) -> None:
        self.root = root
        self.owner = owner
        self.quota = quota
        self.denied_status_calls = denied_status_calls
        self.queued_status_calls = queued_status_calls
        self.fail_push = fail_push
        self.status_errors = status_errors
        self.secret_echo = secret_echo  # a remote log line that (wrongly) prints a secret, to test redaction
        self.break_entry = break_entry  # the notebook's entrypoint raises (a deliberately failing run)
        self.calls: list[list[str]] = []
        self.kernels: dict[str, FakeKernel] = {}
        self.datasets: dict[str, Path] = {}
        self.deleted_datasets: list[str] = []
        self.deleted_kernels: list[str] = []
        self.pushed_sources: list[str] = []
        self.closed = False
        self._lock = threading.Lock()

    # --- CliRunner -------------------------------------------------------------------------------------------

    def run(self, args: list[str], *, timeout: float) -> CliResult:
        with self._lock:
            self.calls.append(list(args))
        head = tuple(args[:2])
        if head == ("config", "view"):
            return CliResult(0, fixture("config_view.txt").replace("aas-test-user", self.owner), "")
        if args[0] == "quota":
            if self.quota is None:
                return CliResult(2, WARNING + "\n", fixture("quota_old_cli.stderr.txt"))
            return CliResult(0, fixture(self.quota), "")
        if head == ("datasets", "create"):
            return self._dataset_create(Path(args[args.index("-p") + 1]))
        if head == ("datasets", "status"):
            ready = args[2] in self.datasets
            return CliResult(0, f"{WARNING}\n{'ready' if ready else 'failed'}\n", "")
        if head == ("datasets", "delete"):
            self.deleted_datasets.append(args[2])
            self.datasets.pop(args[2], None)
            return CliResult(0, f"{WARNING}\nDataset deleted\n", "")
        if head == ("kernels", "delete"):
            self.deleted_kernels.append(args[2])
            return CliResult(0, f"{WARNING}\nKernel deleted successfully\n", "")
        if head == ("kernels", "push"):
            return self._push(args)
        if head == ("kernels", "status"):
            return self._status(args[2])
        if head == ("kernels", "logs"):
            return self._blob(args[2])
        if head == ("kernels", "output"):
            return self._output(args[2], Path(args[args.index("-p") + 1]))
        return CliResult(2, "", f"unexpected command {args}")

    def follow(self, args: list[str]) -> _Lines:
        with self._lock:
            self.calls.append(list(args))
        kernel = self.kernels[args[-1].split("/", 1)[1]]
        return _Lines(kernel, [])

    def close(self) -> None:
        self.closed = True

    # --- behaviour -------------------------------------------------------------------------------------------

    def _dataset_create(self, folder: Path) -> CliResult:
        metadata = json.loads((folder / "dataset-metadata.json").read_text(encoding="utf-8"))
        ref = metadata["id"]
        if not ref.startswith(f"{self.owner}/"):
            return CliResult(0, f"{WARNING}\nDataset creation error: owner mismatch\n", "")
        stored = self.root / "datasets" / ref.split("/", 1)[1]
        shutil.copytree(folder, stored, ignore=shutil.ignore_patterns("dataset-metadata.json"))
        self.datasets[ref] = stored
        url = f"https://www.kaggle.com/datasets/{ref}"
        return CliResult(
            0, f"{WARNING}\nYour private Dataset is being created. Please check progress at {url}\n", ""
        )

    def _push(self, args: list[str]) -> CliResult:
        folder = Path(args[args.index("-p") + 1])
        metadata = json.loads((folder / "kernel-metadata.json").read_text(encoding="utf-8"))
        source = (folder / metadata["code_file"]).read_text(encoding="utf-8")
        self.pushed_sources.append(source + json.dumps(metadata))
        if self.fail_push:
            return CliResult(0, f"{WARNING}\nKernel push error: {self.fail_push}\n", "")
        slug = metadata["id"].split("/", 1)[1]
        accelerator = args[args.index("--accelerator") + 1] if "--accelerator" in args else None
        timeout = args[args.index("--timeout") + 1] if "--timeout" in args else None
        kernel = FakeKernel(slug, metadata, source, self.root / "kernels" / slug, accelerator, timeout)
        self.kernels[slug] = kernel
        threading.Thread(target=self._execute, args=(kernel,), daemon=True).start()
        url = f"https://www.kaggle.com/code/{self.owner}/{slug}"
        return CliResult(
            0, f"{WARNING}\nKernel version 1 successfully pushed.  Please check progress at {url}\n", ""
        )

    def _execute(self, kernel: FakeKernel) -> None:
        """Unpack the embedded package like the wrapper does, with Kaggle paths mapped into the sandbox."""
        tree = ast.parse(kernel.source)
        files = next(
            ast.literal_eval(node.value)
            for node in tree.body
            if isinstance(node, ast.Assign) and getattr(node.targets[0], "id", "") == "FILES"
        )
        package = kernel.sandbox / "pkg"
        working = kernel.sandbox / "working"
        package.mkdir(parents=True)
        working.mkdir(parents=True)
        for name, data in files.items():
            (package / name).write_bytes(base64.b64decode(data))
        if self.break_entry:
            (package / "entry.py").write_text(
                "def main(arguments, input_dir, output_dir, progress):\n"
                "    raise RuntimeError('Deliberate failure (M3 acceptance test)')\n",
                encoding="utf-8",
            )
        job = json.loads((package / "job.json").read_text(encoding="utf-8"))
        sources = kernel.metadata["dataset_sources"]
        job["input_dir"] = str(self.datasets[sources[0]]) if sources else str(kernel.sandbox / "no-input")
        job["output_dir"] = str(working / Path(job["output_dir"]).name)
        if job["telemetry"].get("mode") == "live":  # no real GPU here: a fixed, clearly fake T4×2 sample
            job["telemetry"] = {"mode": "fixed", "interval_seconds": 5, "fixed_sample": _FAKE_T4X2}
        (package / "job.json").write_text(json.dumps(job), encoding="utf-8")
        kernel.state = "RUNNING"
        env = {k: v for k, v in os.environ.items() if not k.upper().startswith(("KAGGLE", "AAS_PROFILE"))}
        env.update(PYTHONIOENCODING="utf-8", PYTHONUTF8="1")
        process = subprocess.Popen(
            [sys.executable, str(package / "runner.py"), str(package / "job.json")],
            cwd=working,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
            env=env,
        )
        assert process.stdout is not None
        if self.secret_echo:
            kernel.lines.append(f"debug: {self.secret_echo}")
        for raw in process.stdout:
            kernel.lines.append(raw.rstrip("\r\n").replace(str(self.root), "/kaggle"))
        code = process.wait()
        kernel.state = "COMPLETE" if code == 0 else "ERROR"
        kernel.done.set()

    def _status(self, ref: str) -> CliResult:
        owner, slug = ref.split("/", 1)
        kernel = self.kernels.get(slug)
        if kernel is not None:
            kernel.status_calls += 1
        if kernel is None or owner != self.owner or kernel.status_calls <= self.denied_status_calls:
            return CliResult(1, WARNING + "\n", fixture("status_cannot_access.stderr.txt"))
        if kernel.status_calls <= self.denied_status_calls + self.status_errors:
            return CliResult(1, WARNING + "\n\n", fixture("network_error.stderr.txt"))
        state = kernel.state
        if kernel.status_calls <= self.denied_status_calls + self.status_errors + self.queued_status_calls:
            state = "QUEUED"
        elif state == "RUNNING":
            pass
        text = f'{WARNING}\n{ref} has status "KernelWorkerStatus.{state}"\n'
        if state == "ERROR":
            text += 'Failure message: "Your notebook tried to raise an exception."\n'
        return CliResult(0, text, "")

    def _blob(self, ref: str) -> CliResult:
        kernel = self.kernels[ref.split("/", 1)[1]]
        if not kernel.done.is_set():
            return CliResult(0, WARNING + "\n\n", "")
        events = [
            {"stream_name": "stdout", "time": i * 0.1, "data": line + "\n"}
            for i, line in enumerate(kernel.lines)
        ]
        return CliResult(0, WARNING + "\n" + json.dumps(events) + "\n", "")

    def _output(self, ref: str, dest: Path) -> CliResult:
        kernel = self.kernels[ref.split("/", 1)[1]]
        if not kernel.done.is_set():
            return CliResult(1, "", "Kernel is still running")
        dest.mkdir(parents=True, exist_ok=True)
        shutil.copytree(kernel.sandbox / "working", dest, dirs_exist_ok=True)
        (dest / f"{kernel.slug}.log").write_text("[]", encoding="utf-8")
        return CliResult(0, f"{WARNING}\nOutput file downloaded to <dest>\n", "")

    def wait_done(self, timeout: float = 30.0) -> None:
        for kernel in list(self.kernels.values()):
            assert kernel.done.wait(timeout)


_FAKE_T4X2 = {
    "cpu_percent": 12.5,
    "ram_used_bytes": 2147483648,
    "ram_total_bytes": 33658159104,
    "gpu_source": "nvml",
    "gpus": [
        {
            "index": 0,
            "name": "Tesla T4 (fake)",
            "utilization_percent": 91.0,
            "vram_used_bytes": 9663676416,
            "vram_total_bytes": 16106127360,
            "temperature_c": 70.0,
        },
        {
            "index": 1,
            "name": "Tesla T4 (fake)",
            "utilization_percent": 3.0,
            "vram_used_bytes": 470089728,
            "vram_total_bytes": 16106127360,
            "temperature_c": None,
        },
    ],
}
