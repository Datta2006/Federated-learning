"""SQLite database models and session management for Stack 5 persistence.

This module provides SQLAlchemy ORM models for persistent storage of:
- Experiments and their configurations
- Telemetry data from FL runs
- Forecast results
- Alerts
- Round outcomes

Thread-safe session management for concurrent FastAPI and MQTT access.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from sqlalchemy import (
    DateTime,
    Integer,
    String,
    JSON,
    Boolean,
    Text,
    ForeignKey,
    Float as SAFloat,
    create_engine,
    Index,
)
from sqlalchemy.orm import (
    DeclarativeBase,
    Mapped,
    mapped_column,
    relationship,
    sessionmaker,
)
from contextlib import contextmanager


class Base(DeclarativeBase):
    """Base class for all SQLAlchemy models."""
    pass


@dataclass(frozen=True)
class ExperimentType:
    """Experiment type constants."""
    FEDERATED = "federated"
    CENTRALIZED = "centralized"
    HYPERPARAMETER_SEARCH = "hyperparameter_search"
    ABLATION = "ablation"
    PRODUCTION = "production"


class Experiment(Base):
    """SQLAlchemy model for FL experiment metadata.

    Tracks the core experiment configuration and lifecycle.
    """
    __tablename__ = "experiments"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    name: Mapped[str] = mapped_column(String(256), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    experiment_type: Mapped[str] = mapped_column(String(32), nullable=False)

    # Configuration stored as JSON
    config: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)

    # Training parameters
    seed: Mapped[int] = mapped_column(Integer, nullable=False)
    epochs: Mapped[int] = mapped_column(Integer, nullable=False)
    batch_size: Mapped[int] = mapped_column(Integer, nullable=False)
    learning_rate: Mapped[float] = mapped_column(SAFloat, nullable=False)

    # Model settings
    model_name: Mapped[str] = mapped_column(String(128), nullable=False)
    model_version: Mapped[str] = mapped_column(String(128), nullable=False)

    # Gateway participation
    gateway_config: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)

    # Timing
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)
    started_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    # Status
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="pending")

    # Relationships
    rounds: Mapped[list["RoundOutcome"]] = relationship("RoundOutcome", back_populates="experiment", cascade="all, delete-orphan")
    metrics: Mapped[list["ExperimentMetrics"]] = relationship("ExperimentMetrics", back_populates="experiment", cascade="all, delete-orphan")
    telemetry_records: Mapped[list["TelemetryRecord"]] = relationship("TelemetryRecord", back_populates="experiment", cascade="all, delete-orphan")
    forecasts: Mapped[list["ForecastRecord"]] = relationship("ForecastRecord", back_populates="experiment", cascade="all, delete-orphan")
    alerts: Mapped[list["AlertRecord"]] = relationship("AlertRecord", back_populates="experiment", cascade="all, delete-orphan")

    # Indexes
    __table_args__ = (
        Index("idx_experiments_status_created", "status", "created_at"),
        Index("idx_experiments_type_created", "experiment_type", "created_at"),
    )


class RoundOutcome(Base):
    """SQLAlchemy model for FL round outcomes.

    Records the results of each federated learning round including
    selection, aggregation, and validation metrics.
    """
    __tablename__ = "round_outcomes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    experiment_id: Mapped[str] = mapped_column(String(64), ForeignKey("experiments.id"), nullable=False)

    # Round metadata
    round_number: Mapped[int] = mapped_column(Integer, nullable=False)
    round_time_sec: Mapped[float] = mapped_column(SAFloat, nullable=False)

    # Selection stats
    selected_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    selected_nodes: Mapped[list[str]] = mapped_column(JSON, nullable=False)  # Node IDs
    received_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    dropped_nodes: Mapped[list[str]] = mapped_column(JSON, nullable=False)  # Node IDs

    # Data transfer
    bytes_up: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    bytes_down: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    # Aggregation results
    weighted_val_loss: Mapped[float | None] = mapped_column(SAFloat, nullable=True)
    evaluated_version: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    model_version: Mapped[str] = mapped_column(String(64), nullable=False, default="")

    # Node acceptance/rejection
    accepted_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    rejected_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    rejected_details: Mapped[list[dict[str, str]]] = mapped_column(JSON, nullable=False)  # [{"node": "reason"}, ...]

    # Flags
    single_client: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    aggregated: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    # Status
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="failed")

    # Timestamp
    timestamp: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)

    # Relationships
    experiment: Mapped["Experiment"] = relationship("Experiment", back_populates="rounds")

    # Indexes
    __table_args__ = (
        Index("idx_rounds_experiment_round", "experiment_id", "round_number"),
    )


class ExperimentMetrics(Base):
    """SQLAlchemy model for experiment-level metrics.

    Stores aggregated metrics for the entire experiment run.
    """
    __tablename__ = "experiment_metrics"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    experiment_id: Mapped[str] = mapped_column(String(64), ForeignKey("experiments.id"), nullable=False)

    # Final evaluation results
    final_val_loss: Mapped[float | None] = mapped_column(SAFloat, nullable=True)
    final_val_acc: Mapped[float | None] = mapped_column(SAFloat, nullable=True)
    final_test_loss: Mapped[float | None] = mapped_column(SAFloat, nullable=True)
    final_test_acc: Mapped[float | None] = mapped_column(SAFloat, nullable=True)

    # Training metrics
    total_epochs: Mapped[int] = mapped_column(Integer, nullable=False)
    total_rounds: Mapped[int] = mapped_column(Integer, nullable=False)
    total_round_duration_sec: Mapped[float] = mapped_column(SAFloat, nullable=False)

    # Gateway statistics
    total_bytes_up: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    total_bytes_down: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    # Timing
    experiment_duration_sec: Mapped[float | None] = mapped_column(SAFloat, nullable=True)

    # Performance metrics
    avg_round_time_sec: Mapped[float | None] = mapped_column(SAFloat, nullable=True)
    avg_communication_efficiency: Mapped[float | None] = mapped_column(SAFloat, nullable=True)

    # Timestamp
    recorded_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)

    # Relationships
    experiment: Mapped["Experiment"] = relationship("Experiment", back_populates="metrics")


class TelemetryRecord(Base):
    """SQLAlchemy model for raw telemetry data.

    Stores MQTT telemetry messages for query and analysis.
    """
    __tablename__ = "telemetry"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    experiment_id: Mapped[str] = mapped_column(String(64), ForeignKey("experiments.id"), nullable=False)

    # Message metadata
    topic: Mapped[str] = mapped_column(String(512), nullable=False)
    node_id: Mapped[str] = mapped_column(String(128), nullable=False)
    message_type: Mapped[str] = mapped_column(String(64), nullable=False)

    # Payload (raw JSON)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)

    # Timestamp
    received_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)

    # Relationships
    experiment: Mapped["Experiment"] = relationship("Experiment", back_populates="telemetry_records")

    # Indexes
    __table_args__ = (
        Index("idx_telemetry_experiment_node", "experiment_id", "node_id"),
        Index("idx_telemetry_topic", "topic"),
        Index("idx_telemetry_received_at", "received_at"),
    )


class ForecastRecord(Base):
    """SQLAlchemy model for prediction/forecast results.

    Stores model forecasts for later analysis and comparison.
    """
    __tablename__ = "forecasts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    experiment_id: Mapped[str] = mapped_column(String(64), ForeignKey("experiments.id"), nullable=False)

    # Forecast metadata
    forecast_type: Mapped[str] = mapped_column(String(64), nullable=False)
    version: Mapped[str] = mapped_column(String(128), nullable=False)

    # Results
    predictions: Mapped[list[float]] = mapped_column(JSON, nullable=False)
    confidence_interval: Mapped[tuple[float | None, float | None] | None] = mapped_column(JSON, nullable=True)

    # Evaluation
    mae: Mapped[float | None] = mapped_column(SAFloat, nullable=True)
    rmse: Mapped[float | None] = mapped_column(SAFloat, nullable=True)

    # Timestamp
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)

    # Relationships
    experiment: Mapped["Experiment"] = relationship("Experiment", back_populates="forecasts")

    # Indexes
    __table_args__ = (
        Index("idx_forecasts_experiment_type", "experiment_id", "forecast_type"),
    )


class AlertRecord(Base):
    """SQLAlchemy model for system alerts and anomalies.

    Stores alerts generated during FL training for later review.
    """
    __tablename__ = "alerts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    experiment_id: Mapped[str] = mapped_column(String(64), ForeignKey("experiments.id"), nullable=False)

    # Alert details
    alert_type: Mapped[str] = mapped_column(String(64), nullable=False)
    severity: Mapped[str] = mapped_column(String(32), nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    details: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=True)

    # Timestamp
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    # Resolution status
    resolved: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    # Relationships
    experiment: Mapped["Experiment"] = relationship("Experiment", back_populates="alerts")

    # Indexes
    __table_args__ = (
        Index("idx_alerts_experiment_severity", "experiment_id", "severity"),
        Index("idx_alerts_created_at", "created_at"),
    )


class DatabaseManager:
    """Thread-safe database manager with session handling.

    Provides context-managed sessions and handles engine lifecycle.
    All operations are safe for concurrent access from FastAPI and MQTT.
    """

    _instance = None
    _lock = threading.Lock()
    _init_lock = threading.Lock()

    def __new__(cls, db_path: str | Path | None = None, **engine_kwargs) -> "DatabaseManager":
        """Singleton pattern ensures single database connection."""
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
        return cls._instance

    def __init__(self, db_path: str | Path | None = None, **engine_kwargs):
        with self._init_lock:
            if self._initialized:
                return

        self.db_path = self._resolve_db_path(db_path)
        self._engine_kwargs = engine_kwargs
        self._engine = None
        self._SessionLocal = None
        self._session_lock = threading.Lock()
        self._initialized = True

    def _resolve_db_path(self, db_path: str | Path | None) -> Path:
        """Resolve database path to absolute location."""
        if db_path is None:
            # Default to project data directory
            project_root = Path(__file__).resolve().parents[4]  # Go up to project root
            data_dir = project_root / "dashboard" / "backend" / "data"
            data_dir.mkdir(parents=True, exist_ok=True)
            return data_dir / "experiments.db"
        return Path(db_path).resolve()

    @property
    def engine(self):
        """Lazily create and return the SQLAlchemy engine."""
        if self._engine is None:
            self._engine = create_engine(
                f"sqlite:///{self.db_path}",
                connect_args={"check_same_thread": False},
                pool_pre_ping=True,
                **self._engine_kwargs
            )
        return self._engine

    @property
    def SessionLocal(self):
        """Lazily create and return the session factory."""
        if self._SessionLocal is None:
            self._SessionLocal = sessionmaker(
                bind=self.engine,
                autocommit=False,
                autoflush=False,
                expire_on_commit=False,
            )
        return self._SessionLocal

    def get_session(self):
        """Get a thread-local session.

        Use as a context manager:
            with db_manager.get_session() as session:
                # work with session
        """
        return SessionScope(self.SessionLocal())

    def init_db(self):
        """Initialize database tables.

        Call this on application startup.
        """
        with self._session_lock:
            # Create all tables defined in this module
            Base.metadata.create_all(self.engine)

    def close(self):
        """Close database resources."""
        with self._session_lock:
            if self._SessionLocal:
                self._SessionLocal.close_all()
            if self._engine:
                self._engine.dispose()
            self._initialized = False


class SessionScope:
    """Thread-safe session scope context manager."""

    def __init__(self, session):
        self.session = session

    def __enter__(self):
        return self.session

    def __exit__(self, exc_type, exc_val, exc_tb):
        try:
            if exc_type is None:
                self.session.commit()
            else:
                self.session.rollback()
        finally:
            self.session.close()
        return False


@contextmanager
def get_db_session(db_manager: DatabaseManager = None):
    """Convenience context manager for database sessions.

    Usage:
        with get_db_session() as session:
            experiment = session.query(Experiment).first()
    """
    if db_manager is None:
        db_manager = DatabaseManager()

    with db_manager.get_session() as session:
        yield session


# Global session manager instance
_db_manager: DatabaseManager | None = None


def get_db_manager(db_path: str | Path | None = None) -> DatabaseManager:
    """Get or create the global database manager."""
    global _db_manager
    if _db_manager is None:
        _db_manager = DatabaseManager(db_path)
    return _db_manager


def init_database(db_path: str | Path | None = None) -> DatabaseManager:
    """Initialize the database and return the manager.

    Call this during application startup.
    """
    manager = DatabaseManager(db_path)
    manager.init_db()
    return manager


# Models re-exported for public API
__all__ = [
    "Base",
    "Experiment",
    "ExperimentType",
    "RoundOutcome",
    "ExperimentMetrics",
    "TelemetryRecord",
    "ForecastRecord",
    "AlertRecord",
    "DatabaseManager",
    "get_db_manager",
    "init_database",
    "get_db_session",
]