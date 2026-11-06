"""AI Asset Studio notebook runner (docs/CONTRACTS.md §6.4).

Runs INSIDE the remote notebook, or in the mock sandbox. Single file, standard library only (psutil and pynvml are
used when present). It never imports the backend, ``models`` or ``kaggle_connector``.

Usage: ``python runner.py [job.json]``. Prints ``AAS_PROGRESS`` / ``AAS_TELEMETRY`` lines to stdout and writes
``<output_dir>/manifest.json``. Exit code 0 on success, 1 on failure.
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import subprocess
import sys
import threading
from datetime import UTC, datetime, timedelta
from pathlib import Path

MAX_LINE_BYTES = 4096


def _now(offset_seconds: float = 0) -> str:
    moment = datetime.now(UTC) - timedelta(seconds=offset_seconds)
    return moment.strftime("%Y-%m-%dT%H:%M:%SZ")


def _emit(prefix: str, payload: dict) -> None:
    line = f"{prefix} {json.dumps(payload, separators=(',', ':'))}"
    if len(line.encode("utf-8")) > MAX_LINE_BYTES:
        payload = {**payload, "gpus": [], "errors": ["line truncated"]} if "gpus" in payload else payload
        line = f"{prefix} {json.dumps(payload, separators=(',', ':'))}"[:MAX_LINE_BYTES]
    print(line, flush=True)


def _live_sample(job_id: str) -> dict:
    sample = {
        "v": 1,
        "job_id": job_id,
        "at": _now(),
        "cpu_percent": None,
        "ram_used_bytes": None,
        "ram_total_bytes": None,
        "gpu_source": "none",
        "gpus": [],
        "errors": [],
    }
    try:
        import psutil

        memory = psutil.virtual_memory()
        sample.update(
            cpu_percent=psutil.cpu_percent(interval=None),
            ram_used_bytes=int(memory.used),
            ram_total_bytes=int(memory.total),
        )
    except Exception as exc:
        sample["errors"].append(f"host: {exc.__class__.__name__}")
    try:
        import pynvml

        pynvml.nvmlInit()
        gpus = []
        for index in range(pynvml.nvmlDeviceGetCount()):
            handle = pynvml.nvmlDeviceGetHandleByIndex(index)
            memory = pynvml.nvmlDeviceGetMemoryInfo(handle)
            name = pynvml.nvmlDeviceGetName(handle)
            try:
                temperature = float(pynvml.nvmlDeviceGetTemperature(handle, 0))
            except Exception:
                temperature = None
            gpus.append(
                {
                    "index": index,
                    "name": name.decode() if isinstance(name, bytes) else name,
                    "utilization_percent": float(pynvml.nvmlDeviceGetUtilizationRates(handle).gpu),
                    "vram_used_bytes": int(memory.used),
                    "vram_total_bytes": int(memory.total),
                    "temperature_c": temperature,
                }
            )
        sample.update(gpu_source="nvml", gpus=gpus)
        return sample
    except Exception:  # noqa: S110 - pynvml missing or no driver: fall back to nvidia-smi
        pass
    try:
        out = subprocess.run(
            [  # noqa: S607 - nvidia-smi from PATH inside the notebook image
                "nvidia-smi",
                "--query-gpu=index,name,utilization.gpu,memory.used,memory.total,temperature.gpu",
                "--format=csv,noheader,nounits",
            ],
            capture_output=True,
            text=True,
            timeout=10,
            check=True,
        ).stdout
        gpus = []
        for row in out.strip().splitlines():
            index, name, util, used, total, temp = (part.strip() for part in row.split(","))
            number = lambda v: None if v in ("", "[N/A]", "N/A") else float(v)  # noqa: E731
            gpus.append(
                {
                    "index": int(index),
                    "name": name,
                    "utilization_percent": number(util),
                    "vram_used_bytes": None if number(used) is None else int(number(used) * 1024 * 1024),
                    "vram_total_bytes": None if number(total) is None else int(number(total) * 1024 * 1024),
                    "temperature_c": number(temp),
                }
            )
        sample.update(gpu_source="nvidia_smi", gpus=gpus)
    except FileNotFoundError:
        pass
    except Exception as exc:
        sample["errors"].append(f"gpu: {exc.__class__.__name__}")
    return sample


class TelemetryReporter(threading.Thread):
    """Daemon thread. ``mode``: ``off`` | ``live`` (psutil/NVML) | ``fixed`` (mock values, stated by the client)."""

    def __init__(self, job_id: str, config: dict) -> None:
        super().__init__(daemon=True, name="aas-telemetry")
        self.job_id = job_id
        self.mode = config.get("mode", "off")
        self.interval = min(60, max(5, int(config.get("interval_seconds", 15))))
        self.fixed = config.get("fixed_sample") or {}
        self.age = float(config.get("age_seconds", 0))
        self.stop_event = threading.Event()

    def sample(self) -> dict:
        if self.mode == "fixed":
            return {"v": 1, "job_id": self.job_id, "at": _now(self.age), "errors": [], **self.fixed}
        return _live_sample(self.job_id)

    def run(self) -> None:
        if self.mode == "off":
            return
        while not self.stop_event.is_set():
            try:
                _emit("AAS_TELEMETRY", self.sample())
            except Exception as exc:  # telemetry never fails the job
                print(f"telemetry reporter error: {exc.__class__.__name__}", flush=True)
            self.stop_event.wait(self.interval)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def run(job_path: Path) -> int:
    job = json.loads(job_path.read_text(encoding="utf-8"))
    base = job_path.parent
    job_id = job["job_id"]
    input_dir = Path(job["input_dir"]) if Path(job["input_dir"]).is_absolute() else base / job["input_dir"]
    output_dir = (
        Path(job["output_dir"]) if Path(job["output_dir"]).is_absolute() else base / job["output_dir"]
    )
    output_dir.mkdir(parents=True, exist_ok=True)

    def progress(stage: str, percent: float | None = None, message: str | None = None) -> None:
        _emit(
            "AAS_PROGRESS",
            {"v": 1, "job_id": job_id, "at": _now(), "stage": stage, "percent": percent, "message": message},
        )

    reporter = TelemetryReporter(job_id, job.get("telemetry", {}))
    reporter.start()
    error = None
    progress("starting", 0, "Runner started")
    try:
        spec = importlib.util.spec_from_file_location("aas_entry", base / job["entrypoint"])
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        module.main(job["arguments"], input_dir, output_dir, progress)
    except Exception as exc:
        # Type and message only: no traceback, so no local paths or source lines leak into logs.
        error = {"code": "KAGGLE_KERNEL_ERROR", "message": f"{exc.__class__.__name__}: {exc}"[:500]}
        print(f"ERROR entrypoint failed: {error['message']}", flush=True)
    finally:
        reporter.stop_event.set()
        reporter.join(timeout=5)

    outputs = []
    for expected in job.get("expected_outputs", []):
        path = output_dir / expected["name"]
        if path.is_file():
            outputs.append(
                {
                    "name": expected["name"],
                    "kind": expected["kind"],
                    "format": expected["format"],
                    "size_bytes": path.stat().st_size,
                    "sha256": _sha256(path),
                }
            )
    manifest = {
        "v": 1,
        "job_id": job_id,
        "status": "error" if error else "ok",
        "error": error,
        "outputs": outputs,
    }
    (output_dir / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    if error is None:
        progress("finished", 100, "Outputs written")
    return 1 if error else 0


def main(argv: list[str]) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", line_buffering=True)
    job_path = Path(argv[1]) if len(argv) > 1 else Path(__file__).with_name("job.json")
    return run(job_path.resolve())


if __name__ == "__main__":
    sys.exit(main(sys.argv))
