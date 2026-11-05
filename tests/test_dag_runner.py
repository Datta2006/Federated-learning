"""Unit tests for the small Stage 4 DAG runner."""

from __future__ import annotations

import time

import pytest

from server.dag_runner import (
    DAG,
    Task,
    TaskTimeoutError,
    run_dag,
)


def test_dag_runs_tasks_in_dependency_order():
    order: list[str] = []

    def record(name: str):
        def task(context: dict) -> None:
            order.append(name)
            context[name] = True

        return task

    dag = DAG(
        [
            Task("check", record("check")),
            Task("select", record("select"), depends_on=("check",)),
            Task("broadcast", record("broadcast"), depends_on=("select",)),
            Task("wait", record("wait"), depends_on=("broadcast",)),
        ]
    )

    result = run_dag(dag)

    assert order == ["check", "select", "broadcast", "wait"]
    assert result.success is True


def test_dag_retries_a_failing_task_then_succeeds():
    attempts = {"count": 0}

    def flaky(context: dict) -> dict:
        attempts["count"] += 1
        if attempts["count"] < 3:
            raise RuntimeError("not yet")
        return {"value": 7}

    result = run_dag(DAG([Task("flaky", flaky, retries=2)]))

    assert result.success is True
    assert attempts["count"] == 3
    assert result.context["value"] == 7
    assert result.tasks["flaky"].attempts == 3


def test_dag_timeout_marks_the_task_failed_and_skips_dependents():
    def slow(context: dict) -> None:
        time.sleep(0.5)

    def dependent(context: dict) -> None:
        context["dependent"] = True

    result = run_dag(
        DAG(
            [
                Task("slow", slow, timeout=0.05),
                Task("dependent", dependent, depends_on=("slow",)),
            ]
        )
    )

    assert result.success is False
    assert result.tasks["slow"].status == "failed"
    assert isinstance(result.tasks["slow"].error, TaskTimeoutError)
    assert result.tasks["dependent"].status == "skipped"
    assert "dependent" not in result.context


def test_dag_failure_propagates_to_dependents_but_not_independent_tasks():
    def fail(context: dict) -> None:
        raise RuntimeError("boom")

    def dependent(context: dict) -> None:
        context["dependent"] = True

    def independent(context: dict) -> None:
        context["independent"] = True

    result = run_dag(
        DAG(
            [
                Task("fail", fail),
                Task("dependent", dependent, depends_on=("fail",)),
                Task("independent", independent),
            ]
        )
    )

    assert result.success is False
    assert result.tasks["fail"].status == "failed"
    assert result.tasks["dependent"].status == "skipped"
    assert result.tasks["independent"].status == "ok"
    assert result.context["independent"] is True


def test_dag_rejects_duplicate_names_and_cycles():
    with pytest.raises(ValueError, match="duplicate"):
        DAG([Task("a", lambda context: None), Task("a", lambda context: None)])

    with pytest.raises(ValueError, match="cycle"):
        DAG(
            [
                Task("a", lambda context: None, depends_on=("b",)),
                Task("b", lambda context: None, depends_on=("a",)),
            ]
        )
