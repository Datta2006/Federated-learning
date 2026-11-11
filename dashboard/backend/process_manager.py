"""Local process manager for the broker, coordinator, and simulated workers.

Every process is launched explicitly by the dashboard, with its stdout/stderr
captured to a log file.  Duplicate launches are refused, crash exits are
reported with the tail of the log, and shutdown is graceful (SIGTERM, then
SIGKILL after a timeout).  Remote devices are never launched here; they only
connect over MQTT.
"""

from __future__ import annotations

import logging
import os
import shutil
import signal
import socket
import subprocess
import sys
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[2]
RUNTIME_DIR = PROJECT_ROOT / ".airfed_runtime"
LOGGER = logging.getLogger(__name__)


class ProcessError(RuntimeError):
    """Raised for invalid or duplicate process operations."""


def port_open(host: str, port: int, timeout: float = 0.4) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


@dataclass
class ManagedProcess:
    name: str
    kind: str
    command: list[str]
    popen: subprocess.Popen[bytes]
    log_path: Path
    started_at: float
    role: str | None = None
    _log_handle: Any = field(default=None, repr=False)

    def alive(self) -> bool:
        return self.popen.poll() is None

    def to_dict(self) -> dict[str, Any]:
        code = self.popen.poll()
        return {
            "name": self.name,
            "kind": self.kind,
            "role": self.role,
            "pid": self.popen.pid,
            "running": code is None,
            "exit_code": code,
            "started_at": _iso(self.started_at),
            "uptime_sec": round(max(0.0, time.time() - self.started_at), 1)
            if code is None
            else None,
            "command": list(self.command),
            "log_path": str(self.log_path),
        }


def _iso(ts: float | None) -> str | None:
    if ts is None:
        return None
    from datetime import datetime, timezone

    return (
        datetime.fromtimestamp(ts, tz=timezone.utc)
        .isoformat(timespec="milliseconds")
        .replace("+00:00", "Z")
    )


class ProcessManager:
    def __init__(
        self,
        *,
        host: str = "127.0.0.1",
        port: int = 1883,
        base_topic: str = "aq",
        python: str | None = None,
        runtime_dir: Path | None = None,
        coordinator_args: list[str] | None = None,
    ) -> None:
        self.host = host
        self.port = int(port)
        self.base_topic = base_topic
        self.python = python or sys.executable
        self.runtime_dir = Path(runtime_dir or RUNTIME_DIR)
        self.runtime_dir.mkdir(parents=True, exist_ok=True)
        self.coordinator_args = list(coordinator_args or [])
        self._lock = threading.RLock()
        self._processes: dict[str, ManagedProcess] = {}
        self._crashes: list[dict[str, Any]] = []
        self._broker_owned = False
        self._shutdown = False

    # --------------------------------------------------------------- helpers
    def _log_path(self, name: str) -> Path:
        return self.runtime_dir / f"{name}.log"

    def _open_log(self, name: str) -> Any:
        path = self._log_path(name)
        path.parent.mkdir(parents=True, exist_ok=True)
        return path.open("ab", buffering=0)

    def _pid_path(self, name: str) -> Path:
        return self.runtime_dir / f"{name}.pid"

    def _pid_alive(self, pid: int) -> bool:
        try:
            os.kill(pid, 0)
            return True
        except OSError:
            return False

    def _external_pid(self, name: str) -> int | None:
        path = self._pid_path(name)
        if not path.exists():
            return None
        try:
            pid = int(path.read_text(encoding="utf-8").strip())
        except (OSError, ValueError):
            return None
        if pid > 0 and self._pid_alive(pid):
            return pid
        try:
            path.unlink()
        except OSError:
            pass
        return None

    def _record_started(self, process: ManagedProcess) -> None:
        self._processes[process.name] = process
        self._pid_path(process.name).write_text(
            str(process.popen.pid), encoding="utf-8"
        )

    def _cleanup_dead(self) -> None:
        for name, process in list(self._processes.items()):
            if process.alive():
                continue
            code = process.popen.poll()
            self._crashes.append(
                {
                    "name": name,
                    "kind": process.kind,
                    "exit_code": code,
                    "at": _iso(time.time()),
                    "log_tail": self._tail(process.log_path, 30),
                }
            )
            self._crashes = self._crashes[-20:]
            try:
                process._log_handle.close()
            except Exception:  # pragma: no cover
                LOGGER.debug("could not close log for %s", name, exc_info=True)
            self._processes.pop(name, None)
            try:
                self._pid_path(name).unlink()
            except OSError:
                pass

    @staticmethod
    def _tail(path: Path, lines: int) -> list[str]:
        try:
            with path.open("r", encoding="utf-8", errors="replace") as handle:
                return [line.rstrip("\n") for line in handle.readlines()[-lines:]]
        except OSError:
            return []

    def _launch(
        self,
        *,
        name: str,
        kind: str,
        command: list[str],
        env: dict[str, str] | None = None,
        role: str | None = None,
    ) -> ManagedProcess:
        external = self._external_pid(name)
        if external is not None:
            raise ProcessError(
                f"{name} is already running as PID {external} (pid file "
                f"{self._pid_path(name)}); stop it before re-launching"
            )
        existing = self._processes.get(name)
        if existing is not None and existing.alive():
            raise ProcessError(f"{name} is already running as PID {existing.popen.pid}")
        log_path = self._log_path(name)
        handle = self._open_log(name)
        handle.write(
            (
                f"\n=== {time.strftime('%Y-%m-%dT%H:%M:%S')} starting {name} ===\n"
                f"$ {' '.join(command)}\n"
            ).encode()
        )
        environment = dict(os.environ)
        environment.setdefault("PYTHONUNBUFFERED", "1")
        environment.update(env or {})
        try:
            popen = subprocess.Popen(
                command,
                cwd=str(PROJECT_ROOT),
                stdout=handle,
                stderr=subprocess.STDOUT,
                env=environment,
                start_new_session=True,
            )
        except OSError as exc:
            handle.write(f"launch failed: {exc}\n".encode())
            handle.close()
            raise ProcessError(f"could not launch {name}: {exc}") from exc
        process = ManagedProcess(
            name=name,
            kind=kind,
            command=command,
            popen=popen,
            log_path=log_path,
            started_at=time.time(),
            role=role,
            _log_handle=handle,
        )
        self._record_started(process)
        return process

    # --------------------------------------------------------------- broker
    def broker_reachable(self) -> bool:
        return port_open(self.host, self.port)

    def start_broker(self, *, wait_sec: float = 5.0) -> dict[str, Any]:
        with self._lock:
            self._cleanup_dead()
            if self.broker_reachable():
                return {
                    "ok": True,
                    "owned": self._broker_owned,
                    "message": f"broker already reachable at {self.host}:{self.port}",
                    "process": self.status_of("broker"),
                }
            binary = shutil.which("mosquitto") or (
                "/usr/local/bin/mosquitto"
                if Path("/usr/local/bin/mosquitto").exists()
                else None
            )
            if not binary:
                raise ProcessError(
                    "mosquitto is not installed or not on PATH; install it with "
                    "`brew install mosquitto` (macOS) or `apt install mosquitto`"
                )
            command = [binary, "-p", str(self.port), "-v"]
            self._launch(name="broker", kind="broker", command=command)
            self._broker_owned = True
            deadline = time.time() + wait_sec
            while time.time() < deadline:
                if self.broker_reachable():
                    return {
                        "ok": True,
                        "owned": True,
                        "message": f"started mosquitto on port {self.port}",
                        "process": self.status_of("broker"),
                    }
                time.sleep(0.15)
            process = self._processes.get("broker")
            if process is not None and not process.alive():
                raise ProcessError(
                    "mosquitto exited at startup: "
                    + " | ".join(self._tail(process.log_path, 8))
                )
            raise ProcessError(
                f"mosquitto did not open {self.host}:{self.port} within {wait_sec:.0f}s"
            )

    # ----------------------------------------------------------- coordinator
    def start_coordinator(
        self,
        *,
        dummy: bool = False,
        extra_args: list[str] | None = None,
    ) -> dict[str, Any]:
        with self._lock:
            self._cleanup_dead()
            existing = self._processes.get("coordinator")
            if existing is not None and existing.alive():
                return {
                    "ok": True,
                    "message": f"coordinator already running as PID {existing.popen.pid}",
                    "process": existing.to_dict(),
                }
            if not self.broker_reachable():
                raise ProcessError(
                    "broker is not reachable; start the broker before the coordinator"
                )
            command = [
                self.python,
                "-m",
                "server.fl_coordinator",
                "--control",
                "--host",
                self.host,
                "--port",
                str(self.port),
                *self.coordinator_args,
            ]
            if dummy:
                command.append("--dummy")
            command.extend(extra_args or [])
            self._launch(name="coordinator", kind="coordinator", command=command)
            return {
                "ok": True,
                "message": "coordinator launched",
                "process": self.status_of("coordinator"),
            }

    # --------------------------------------------------------------- workers
    def start_workers(
        self,
        *,
        count: int,
        role: str = "training",
        simulation: bool = True,
        dummy: bool = False,
        prefix: str = "sim",
        extra_args: list[str] | None = None,
    ) -> dict[str, Any]:
        if count < 1 or count > 200:
            raise ProcessError("worker count must be between 1 and 200")
        if role not in {"training", "inference"}:
            raise ProcessError("worker role must be 'training' or 'inference'")
        if not dummy and simulation and not (
            PROJECT_ROOT / "data" / "beijing_pm25.csv"
        ).exists():
            raise ProcessError(
                "dataset data/beijing_pm25.csv is missing; cannot launch real "
                "simulation workers"
            )
        with self._lock:
            self._cleanup_dead()
            if not self.broker_reachable():
                raise ProcessError(
                    "broker is not reachable; start the broker before workers"
                )
            started: list[dict[str, Any]] = []
            skipped: list[str] = []
            for index in range(count):
                worker_id = f"{prefix}-{index + 1}"
                existing = self._processes.get(worker_id)
                if existing is not None and existing.alive():
                    skipped.append(worker_id)
                    continue
                command = [
                    self.python,
                    "-m",
                    "node.fl_node",
                    "--node-id",
                    worker_id,
                    "--dynamic",
                    "--host",
                    self.host,
                    "--port",
                    str(self.port),
                ]
                if dummy:
                    command.extend(
                        [
                            "--dummy",
                            "--dummy-value",
                            str(1.0 + index),
                            "--dummy-samples",
                            str(100 + 10 * index),
                            "--dummy-count",
                            "9025",
                        ]
                    )
                else:
                    command.extend(
                        [
                            "--simulation",
                            "--shard-index",
                            str(index),
                            "--shard-count",
                            str(count),
                        ]
                    )
                if role == "inference":
                    command.append("--inference-only")
                command.extend(extra_args or [])
                process = self._launch(
                    name=worker_id,
                    kind="worker",
                    command=command,
                    role=role,
                )
                started.append(process.to_dict())
            return {
                "ok": True,
                "started": started,
                "skipped": skipped,
                "message": (
                    f"launched {len(started)} {role} worker(s)"
                    + (f"; already running: {', '.join(skipped)}" if skipped else "")
                ),
            }

    def stop_worker(self, worker_id: str, *, timeout: float = 10.0) -> bool:
        return self.stop(worker_id, timeout=timeout)

    def stop_workers(self, *, timeout: float = 10.0) -> list[str]:
        with self._lock:
            names = [
                name
                for name, process in self._processes.items()
                if process.kind == "worker" and process.alive()
            ]
        for name in names:
            self.stop(name, timeout=timeout)
        return names

    # ------------------------------------------------------------------ stop
    def stop(self, name: str, *, timeout: float = 10.0) -> bool:
        with self._lock:
            process = self._processes.get(name)
            if process is None or process.popen.poll() is not None:
                self._cleanup_dead()
                return False
        try:
            os.killpg(os.getpgid(process.popen.pid), signal.SIGTERM)
        except (OSError, ProcessLookupError):
            try:
                process.popen.terminate()
            except OSError:
                pass
        try:
            process.popen.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            try:
                os.killpg(os.getpgid(process.popen.pid), signal.SIGKILL)
            except (OSError, ProcessLookupError):
                try:
                    process.popen.kill()
                except OSError:
                    pass
            try:
                process.popen.wait(timeout=3.0)
            except subprocess.TimeoutExpired:  # pragma: no cover
                pass
        with self._lock:
            try:
                process._log_handle.close()
            except Exception:  # pragma: no cover
                LOGGER.debug("could not close log for %s", name, exc_info=True)
            self._processes.pop(name, None)
            try:
                self._pid_path(name).unlink()
            except OSError:
                pass
        return True

    def stop_all(self, *, timeout: float = 8.0) -> list[str]:
        self._shutdown = True
        with self._lock:
            names = [name for name in self._processes]
        # Workers first, then the coordinator, then an owned broker.
        order = sorted(
            names,
            key=lambda name: (
                0 if name.startswith("sim") else 1 if name == "coordinator" else 2
            ),
        )
        stopped = []
        for name in order:
            if self.stop(name, timeout=timeout):
                stopped.append(name)
        return stopped

    # ---------------------------------------------------------------- status
    def status_of(self, name: str) -> dict[str, Any] | None:
        with self._lock:
            process = self._processes.get(name)
            return process.to_dict() if process is not None else None

    def logs(self, name: str, *, lines: int = 120) -> dict[str, Any]:
        process = self._processes.get(name)
        path = process.log_path if process is not None else self._log_path(name)
        if not path.exists():
            raise ProcessError(f"no log for {name}")
        return {
            "name": name,
            "path": str(path),
            "lines": self._tail(path, lines),
            "running": bool(process is not None and process.alive()),
        }

    def status(self) -> dict[str, Any]:
        with self._lock:
            self._cleanup_dead()
            processes = [process.to_dict() for process in self._processes.values()]
            crashes = list(self._crashes)
        return {
            "broker": {
                "host": self.host,
                "port": self.port,
                "reachable": self.broker_reachable(),
                "owned": self._broker_owned,
            },
            "processes": sorted(processes, key=lambda item: (item["kind"], item["name"])),
            "coordinator": next(
                (item for item in processes if item["kind"] == "coordinator"), None
            ),
            "workers": [item for item in processes if item["kind"] == "worker"],
            "crashes": crashes,
            "runtime_dir": str(self.runtime_dir),
        }

    def recent_crashes(self) -> list[dict[str, Any]]:
        with self._lock:
            self._cleanup_dead()
            return list(self._crashes)


__all__ = [
    "ManagedProcess",
    "ProcessError",
    "ProcessManager",
    "port_open",
]
