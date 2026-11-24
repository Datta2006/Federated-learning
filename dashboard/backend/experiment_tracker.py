"""Experiment tracking module for FL runs.

Provides integration between the FL coordinator and SQLite persistence,
recording experiments, rounds, and metrics.
"""

from __future__ import annotations

import json
import threading
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

from sqlalchemy import select, func

from .database import (
    Experiment,
    ExperimentType,
    RoundOutcome,
    ExperimentMetrics,
    DatabaseManager,
    get_db_session,
)


class ExperimentTracker:
    """Tracks FL experiments and records them to SQLite.

    This class provides a bridge between the FL coordinator (which may be
    running in a separate process) and the SQLite database for persistent
    experiment tracking.
    """

    def __init__(self, db_manager: DatabaseManager = None):
        self.db_manager = db_manager or DatabaseManager()
        self._active_experiment_id: Optional[str] = None
        self._lock = threading.Lock()
        self._experiment_start_time: Optional[datetime] = None

    def start_experiment(
        self,
        name: str,
        experiment_type: str,
        config: dict[str, Any],
        seed: int,
        epochs: int,
        batch_size: int,
        learning_rate: float,
        model_name: str,
        model_version: str,
        gateway_config: dict[str, Any],
        description: str | None = None,
    ) -> str:
        """Start tracking a new experiment.

        Returns the experiment ID for later reference.
        """
        with self._lock:
            experiment_id = str(uuid.uuid4())[:8]  # Short ID
            now = datetime.utcnow()

            with get_db_session() as session:
                experiment = Experiment(
                    id=experiment_id,
                    name=name,
                    experiment_type=experiment_type,
                    config=config,
                    seed=seed,
                    epochs=epochs,
                    batch_size=batch_size,
                    learning_rate=learning_rate,
                    model_name=model_name,
                    model_version=model_version,
                    gateway_config=gateway_config,
                    description=description,
                    created_at=now,
                    status="running",
                )
                session.add(experiment)

            self._active_experiment_id = experiment_id
            self._experiment_start_time = now
            return experiment_id

    def set_experiment_status(self, experiment_id: str, status: str):
        """Update experiment status."""
        with get_db_session() as session:
            stmt = select(Experiment).where(Experiment.id == experiment_id)
            experiment = session.scalar(stmt)
            if experiment:
                experiment.status = status
                session.add(experiment)
                session.flush()

    def complete_experiment(
        self,
        experiment_id: str,
        final_val_loss: float | None = None,
        final_val_acc: float | None = None,
        final_test_loss: float | None = None,
        final_test_acc: float | None = None,
        total_duration_sec: float | None = None,
    ):
        """Mark experiment as complete and record final metrics."""
        with self._lock:
            now = datetime.utcnow()

            with get_db_session() as session:
                # Update experiment status
                stmt = select(Experiment).where(Experiment.id == experiment_id)
                experiment = session.scalar(stmt)
                if experiment:
                    experiment.completed_at = now
                    experiment.status = "completed"
                    session.add(experiment)
                    session.flush()

                # Get round count for this experiment
                round_count = session.query(RoundOutcome).filter(
                    RoundOutcome.experiment_id == experiment_id
                ).count()

                # Calculate duration if not provided
                duration = total_duration_sec
                if duration is None and self._experiment_start_time:
                    duration = (now - self._experiment_start_time).total_seconds()
                duration = duration or 0.0

                # Record metrics
                metrics = ExperimentMetrics(
                    experiment_id=experiment_id,
                    final_val_loss=final_val_loss,
                    final_val_acc=final_val_acc,
                    final_test_loss=final_test_loss,
                    final_test_acc=final_test_acc,
                    total_epochs=experiment.epochs if experiment else 0,
                    total_rounds=round_count,
                    total_round_duration_sec=duration,
                    experiment_duration_sec=duration,  # Also populate experiment_duration_sec
                    recorded_at=now,
                )
                session.add(metrics)
                session.flush()

            self._active_experiment_id = None
            self._experiment_start_time = None

    def record_round(
        self,
        experiment_id: str,
        round_number: int,
        selected_nodes: list[str],
        received_count: int,
        dropped_nodes: list[str],
        bytes_up: int,
        bytes_down: int,
        round_time_sec: float,
        weighted_val_loss: float | None = None,
        evaluated_version: str = "",
        model_version: str = "",
        accepted_nodes: list[str] = None,
        rejected_nodes: dict[str, str] = None,
        single_client: bool = False,
        aggregated: bool = False,
        status: str = "failed",
    ):
        """Record a round outcome."""
        accepted_nodes = accepted_nodes or []
        rejected_nodes = rejected_nodes or {}

        with get_db_session() as session:
            round_outcome = RoundOutcome(
                experiment_id=experiment_id,
                round_number=round_number,
                round_time_sec=round_time_sec,
                selected_count=len(selected_nodes),
                selected_nodes=selected_nodes,
                received_count=received_count,
                dropped_nodes=dropped_nodes,
                bytes_up=bytes_up,
                bytes_down=bytes_down,
                weighted_val_loss=weighted_val_loss,
                evaluated_version=evaluated_version,
                model_version=model_version,
                accepted_count=len(accepted_nodes),
                rejected_count=len(rejected_nodes),
                rejected_details=[{"node": k, "reason": v} for k, v in (rejected_nodes or {}).items()],
                single_client=single_client,
                aggregated=aggregated,
                status=status,
            )
            session.add(round_outcome)
            session.flush()

    def get_experiment(self, experiment_id: str) -> Optional[Experiment]:
        """Get experiment by ID."""
        with get_db_session() as session:
            stmt = select(Experiment).where(Experiment.id == experiment_id)
            return session.scalar(stmt)

    def list_experiments(
        self,
        limit: int = 100,
        offset: int = 0,
        status: str | None = None,
    ) -> list[Experiment]:
        """List experiments, optionally filtered by status."""
        with get_db_session() as session:
            stmt = select(Experiment)
            if status:
                stmt = stmt.where(Experiment.status == status)
            stmt = stmt.order_by(Experiment.created_at.desc()).limit(limit).offset(offset)
            return list(session.scalars(stmt).all())

    def get_rounds(
        self,
        experiment_id: str,
        limit: int = 1000,
    ) -> list[RoundOutcome]:
        """Get all rounds for an experiment."""
        with get_db_session() as session:
            stmt = (
                select(RoundOutcome)
                .where(RoundOutcome.experiment_id == experiment_id)
                .order_by(RoundOutcome.round_number)
                .limit(limit)
            )
            return list(session.scalars(stmt).all())

    def get_experiment_summary(self, experiment_id: str) -> dict[str, Any]:
        """Get experiment summary with metrics."""
        with get_db_session() as session:
            stmt = select(ExperimentMetrics).where(
                ExperimentMetrics.experiment_id == experiment_id
            )
            metrics = session.scalar(stmt)

            stmt = select(func.count(RoundOutcome.round_number)).where(
                RoundOutcome.experiment_id == experiment_id
            )
            round_count = session.scalar(stmt) or 0

            return {
                "experiment_id": experiment_id,
                "round_count": round_count,
                "metrics": {
                    "final_val_loss": metrics.final_val_loss if metrics else None,
                    "final_val_acc": metrics.final_val_acc if metrics else None,
                    "final_test_loss": metrics.final_test_loss if metrics else None,
                    "final_test_acc": metrics.final_test_acc if metrics else None,
                    "total_rounds": metrics.total_rounds if metrics else 0,
                    "total_duration_sec": metrics.experiment_duration_sec if metrics else None,
                } if metrics else None,
            }


class FLRunRecorder:
    """Records FL training runs to the database.

    This class is designed to be called by the FL coordinator during
    training to record experiment metadata and round outcomes.
    """

    def __init__(self, db_path: str | Path | None = None):
        from .database import DatabaseManager
        self.db_manager = DatabaseManager(db_path)
        self.tracker = ExperimentTracker(self.db_manager)
        self.current_experiment_id: Optional[str] = None

    @property
    def active_experiment_id(self) -> Optional[str]:
        """Get the current active experiment ID."""
        return self.current_experiment_id

    def start_run(
        self,
        config: dict[str, Any],
        seed: int,
        model_name: str,
        model_version: str,
        gateway_participation: dict[str, Any],
    ) -> str:
        """Start recording a FL run.

        Args:
            config: FL configuration (epochs, batch_size, lr, etc.)
            seed: Random seed for reproducibility
            model_name: Name of the model architecture
            model_version: Version string for model tracking
            gateway_participation: Dict mapping gateway IDs to participation config

        Returns:
            experiment_id for this run
        """
        experiment_id = self.tracker.start_experiment(
            name=f"FL_run_{datetime.utcnow().isoformat()}",
            experiment_type=ExperimentType.FEDERATED,
            config=config,
            seed=seed,
            epochs=config.get("epochs", 10),
            batch_size=config.get("batch_size", 32),
            learning_rate=config.get("learning_rate", 0.001),
            model_name=model_name,
            model_version=model_version,
            gateway_config=gateway_participation,
            description="Federated Learning experiment run",
        )

        self.current_experiment_id = experiment_id
        return experiment_id

    def record_round_completion(
        self,
        round_number: int,
        selected_nodes: list[str],
        received_count: int,
        dropped_nodes: list[str],
        bytes_up: int,
        bytes_down: int,
        round_time_sec: float,
        weighted_val_loss: float | None = None,
        model_version: str = "",
        accepted_nodes: list[str] = None,
        rejected_nodes: dict[str, str] = None,
        status: str = "failed",
    ):
        """Record a round completion event."""
        if not self.current_experiment_id:
            return

        self.tracker.record_round(
            experiment_id=self.current_experiment_id,
            round_number=round_number,
            selected_nodes=selected_nodes,
            received_count=received_count,
            dropped_nodes=dropped_nodes,
            bytes_up=bytes_up,
            bytes_down=bytes_down,
            round_time_sec=round_time_sec,
            weighted_val_loss=weighted_val_loss,
            evaluated_version=f"model_{round_number}",
            model_version=model_version,
            accepted_nodes=accepted_nodes or [],
            rejected_nodes=rejected_nodes or {},
            status=status,
        )

    def complete_run(
        self,
        final_val_loss: float | None = None,
        final_val_acc: float | None = None,
        total_duration_sec: float | None = None,
    ):
        """Mark run as complete."""
        if self.current_experiment_id:
            self.tracker.complete_experiment(
                self.current_experiment_id,
                final_val_loss=final_val_loss,
                final_val_acc=final_val_acc,
                total_duration_sec=total_duration_sec,
            )
            self.current_experiment_id = None


def create_experiment_from_stage4_path(stage4_path: Path) -> str:
    """Create an experiment record from a Stage 4 experiment directory.

    Reads the config and result.json from the stage4 run directory
    and creates a corresponding experiment record.
    """
    result_path = stage4_path / "result.json"
    config_path = stage4_path / "config.json"

    if not result_path.exists():
        raise FileNotFoundError(f"Result file not found: {result_path}")

    # Read result file
    with open(result_path) as f:
        result = json.load(f)

    # Read config if available
    config = {}
    if config_path.exists():
        with open(config_path) as f:
            config = json.load(f)

    # Extract run information from path
    # Expected format: .stage4_runs/{timestamp}/seed-{n}/
    seed_match = stage4_path.name
    if seed_match.startswith("seed-"):
        seed = int(seed_match[5:])
    else:
        seed = 0

    # Create config from available data
    run_config = {
        "epochs": result.get("epochs", config.get("epochs", 10)),
        "batch_size": result.get("batch_size", config.get("batch_size", 32)),
        "learning_rate": config.get("learning_rate", 0.001),
        "rounds": result.get("rounds_completed", len(result.get("round_results", []))),
    }

    from .database import DatabaseManager
    db_manager = DatabaseManager()
    tracker = ExperimentTracker(db_manager)

    experiment_id = tracker.start_experiment(
        name=f"Stage4_{stage4_path.parent.name}",
        experiment_type=ExperimentType.FEDERATED,
        config=run_config,
        seed=seed,
        epochs=run_config["epochs"],
        batch_size=run_config["batch_size"],
        learning_rate=run_config["learning_rate"],
        model_name=config.get("model_name", "unknown"),
        model_version=config.get("model_version", "0.0.1"),
        gateway_config=config.get("gateway_config", {}),
        description=f"Recovered from stage4 run at {stage4_path}",
    )

    return experiment_id


# Module-level active experiment ID for record_fl_round convenience function
_active_experiment_id: Optional[str] = None
_experiment_tracker: ExperimentTracker | None = None


def get_experiment_tracker() -> ExperimentTracker:
    """Get or create the global experiment tracker."""
    global _experiment_tracker
    if _experiment_tracker is None:
        _experiment_tracker = ExperimentTracker()
    return _experiment_tracker


def set_active_experiment(experiment_id: str):
    """Set the active experiment ID for record_fl_round convenience function."""
    global _active_experiment_id
    _active_experiment_id = experiment_id


def get_active_experiment_id() -> Optional[str]:
    """Get the current active experiment ID."""
    return _active_experiment_id


def record_fl_round(
    round_number: int,
    selected_nodes: list[str],
    received_count: int,
    dropped_nodes: list[str],
    bytes_up: int,
    bytes_down: int,
    round_time_sec: float,
    weighted_val_loss: float | None = None,
    status: str = "failed",
):
    """Convenience function to record a round from the FL coordinator."""
    tracker = get_experiment_tracker()
    if _active_experiment_id:
        tracker.record_round(
            experiment_id=_active_experiment_id,
            round_number=round_number,
            selected_nodes=selected_nodes,
            received_count=received_count,
            dropped_nodes=dropped_nodes,
            bytes_up=bytes_up,
            bytes_down=bytes_down,
            round_time_sec=round_time_sec,
            weighted_val_loss=weighted_val_loss,
            status=status,
        )


__all__ = [
    "ExperimentTracker",
    "FLRunRecorder",
    "get_experiment_tracker",
    "record_fl_round",
    "create_experiment_from_stage4_path",
    "set_active_experiment",
    "get_active_experiment_id",
]