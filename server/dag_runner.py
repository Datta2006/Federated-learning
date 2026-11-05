"""A small dependency-aware task runner for the federated round pipelines.

The runner is deliberately generic: a :class:`Task` names a callable, its
dependencies, retry budget, and optional timeout.  The server round DAG and the
node pipeline DAG both use it.  It is not an Airflow replacement; it only
provides topological ordering, retries, per-task timeouts, and failure
propagation.
"""

from __future__ import annotations

import logging
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

LOGGER = logging.getLogger(__name__)

TaskFunction = Callable[[dict[str, Any]], dict[str, Any] | None]


class TaskTimeoutError(RuntimeError):
    """Raised when a task exceeds its per-task timeout."""


@dataclass
class Task:
    """One unit of work in a DAG."""

    name: str
    func: TaskFunction
    depends_on: tuple[str, ...] = ()
    retries: int = 0
    timeout: float | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.name, str) or not self.name:
            raise ValueError("task name must be a non-empty string")
        if not callable(self.func):
            raise TypeError(f"task {self.name!r} func must be callable")
        if self.retries < 0:
            raise ValueError(f"task {self.name!r} retries must be non-negative")
        if self.timeout is not None and self.timeout <= 0:
            raise ValueError(f"task {self.name!r} timeout must be positive")


@dataclass
class TaskResult:
    """Outcome of one task attempt sequence."""

    name: str
    status: str
    attempts: int = 0
    seconds: float = 0.0
    error: BaseException | None = None


@dataclass
class DAGResult:
    """Outcome of a whole DAG run."""

    tasks: dict[str, TaskResult] = field(default_factory=dict)
    context: dict[str, Any] = field(default_factory=dict)
    success: bool = False


class DAG:
    """Validate task dependencies and compute a deterministic topological order."""

    def __init__(self, tasks: list[Task]) -> None:
        self.tasks = list(tasks)
        self._by_name: dict[str, Task] = {}
        for task in self.tasks:
            if task.name in self._by_name:
                raise ValueError(f"duplicate task name {task.name!r}")
            self._by_name[task.name] = task

        for task in self.tasks:
            for dependency in task.depends_on:
                if dependency not in self._by_name:
                    raise ValueError(
                        f"task {task.name!r} depends on unknown task {dependency!r}"
                    )
                if dependency == task.name:
                    raise ValueError(f"task {task.name!r} depends on itself")

        self.order = self._topological_order()

    def get(self, name: str) -> Task:
        """Return the task named *name*."""
        return self._by_name[name]

    def _topological_order(self) -> list[str]:
        indegree = {task.name: len(task.depends_on) for task in self.tasks}
        dependents: dict[str, list[str]] = {task.name: [] for task in self.tasks}
        for task in self.tasks:
            for dependency in task.depends_on:
                dependents[dependency].append(task.name)

        ready = [task.name for task in self.tasks if indegree[task.name] == 0]
        order: list[str] = []
        while ready:
            name = ready.pop(0)
            order.append(name)
            for dependent in dependents[name]:
                indegree[dependent] -= 1
                if indegree[dependent] == 0:
                    ready.append(dependent)

        if len(order) != len(self.tasks):
            raise ValueError("task dependency graph contains a cycle")
        return order


def _call_with_timeout(
    func: TaskFunction, context: dict[str, Any], timeout: float | None
) -> dict[str, Any] | None:
    """Run *func* in a daemon thread so a timeout cannot hang the process.

    Python cannot safely kill a running thread.  A timed-out task is reported
    failed and the caller stops waiting; if the underlying call later returns,
    its result is ignored.
    """
    if timeout is None:
        return func(context)

    outcome: dict[str, Any] = {}

    def target() -> None:
        try:
            outcome["value"] = func(context)
        except BaseException as exc:  # noqa: BLE001 - forwarded to the caller
            outcome["error"] = exc

    thread = threading.Thread(target=target, daemon=True)
    thread.start()
    thread.join(timeout)
    if thread.is_alive():
        raise TaskTimeoutError(f"task exceeded {timeout:.3f}s")
    if "error" in outcome:
        raise outcome["error"]
    return outcome.get("value")


def run_dag(
    dag: DAG,
    context: dict[str, Any] | None = None,
    *,
    logger: logging.Logger | None = None,
) -> DAGResult:
    """Execute *dag* in dependency order, logging each task and skipping dependents."""
    log = logger or LOGGER
    state: dict[str, Any] = dict(context or {})
    results: dict[str, TaskResult] = {}

    for name in dag.order:
        task = dag.get(name)
        blocked = [
            dependency
            for dependency in task.depends_on
            if results.get(dependency) is None or results[dependency].status != "ok"
        ]
        if blocked:
            log.warning("task %s skipped; dependency failed: %s", name, blocked)
            results[name] = TaskResult(
                name=name,
                status="skipped",
                error=RuntimeError(f"dependency failed: {blocked}"),
            )
            continue

        started = time.monotonic()
        attempts = 0
        failure: BaseException | None = None
        for attempt in range(task.retries + 1):
            attempts = attempt + 1
            try:
                value = _call_with_timeout(task.func, state, task.timeout)
            except BaseException as exc:  # noqa: BLE001 - reported in TaskResult
                failure = exc
                if attempt < task.retries:
                    log.warning(
                        "task %s failed (attempt %d/%d): %s; retrying",
                        name,
                        attempts,
                        task.retries + 1,
                        exc,
                    )
                    continue
                break
            if isinstance(value, dict):
                state.update(value)
            results[name] = TaskResult(
                name=name,
                status="ok",
                attempts=attempts,
                seconds=time.monotonic() - started,
            )
            log.info("task %s ok in %.3fs", name, results[name].seconds)
            break
        else:  # pragma: no cover - loop always breaks or records failure
            failure = RuntimeError("task retry loop ended unexpectedly")

        if name not in results:
            results[name] = TaskResult(
                name=name,
                status="failed",
                attempts=attempts,
                seconds=time.monotonic() - started,
                error=failure,
            )
            log.error("task %s failed: %s", name, failure)

    success = all(result.status == "ok" for result in results.values())
    return DAGResult(tasks=results, context=state, success=success)
