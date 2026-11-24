"""REST API endpoints for experiment management.

Provides CRUD operations for experiments, rounds, and metrics.
Designed to integrate with the existing FastAPI application.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any, Optional

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from .database import (
    Experiment,
    ExperimentType,
    RoundOutcome,
    ExperimentMetrics,
    DatabaseManager,
    get_db_session,
)
from .experiment_tracker import ExperimentTracker, create_experiment_from_stage4_path


router = APIRouter(prefix="/api/v1/experiments", tags=["experiments"])


# Pydantic schemas for API responses
class ExperimentSchema(BaseModel):
    """Schema for experiment response."""
    id: str
    name: str
    experiment_type: str
    seed: int
    epochs: int
    batch_size: int
    learning_rate: float
    model_name: str
    model_version: str
    status: str
    created_at: datetime
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class ExperimentDetailSchema(ExperimentSchema):
    """Extended schema for experiment detail."""
    config: dict[str, Any] = Field(default_factory=dict)
    gateway_config: dict[str, Any] = Field(default_factory=dict)
    description: Optional[str] = None


class RoundSchema(BaseModel):
    """Schema for round outcome response."""
    round_number: int
    status: str
    round_time_sec: float
    selected_count: int
    selected_nodes: list[str] = Field(default_factory=list)
    received_count: int
    dropped_nodes: list[str] = Field(default_factory=list)
    bytes_up: int
    bytes_down: int
    weighted_val_loss: Optional[float] = None
    model_version: str
    accepted_count: int
    rejected_count: int
    single_client: bool
    aggregated: bool
    timestamp: datetime

    class Config:
        from_attributes = True


class MetricsSchema(BaseModel):
    """Schema for experiment metrics response."""
    final_val_loss: Optional[float] = None
    final_val_acc: Optional[float] = None
    final_test_loss: Optional[float] = None
    final_test_acc: Optional[float] = None
    total_rounds: int = 0
    experiment_duration_sec: Optional[float] = None
    total_bytes_up: int = 0
    total_bytes_down: int = 0

    class Config:
        from_attributes = True


class ExperimentSummarySchema(BaseModel):
    """Schema for experiment summary."""
    experiment_id: str
    round_count: int
    metrics: Optional[MetricsSchema] = None


class ExperimentCreateRequest(BaseModel):
    """Request body for creating an experiment."""
    name: str
    experiment_type: str = Field(default=ExperimentType.FEDERATED)
    description: Optional[str] = None
    seed: int
    epochs: int
    batch_size: int
    learning_rate: float
    model_name: str
    model_version: str
    config: dict[str, Any] = Field(default_factory=dict)
    gateway_config: dict[str, Any] = Field(default_factory=dict)


class ExperimentUpdateRequest(BaseModel):
    """Request body for updating an experiment."""
    name: Optional[str] = None
    description: Optional[str] = None
    status: Optional[str] = None


class RoundSubmission(BaseModel):
    """Request body for submitting a round outcome."""
    experiment_id: str
    round_number: int
    selected_nodes: list[str] = Field(default_factory=list)
    received_count: int = 0
    dropped_nodes: list[str] = Field(default_factory=list)
    bytes_up: int = 0
    bytes_down: int = 0
    round_time_sec: float = 0.0
    weighted_val_loss: Optional[float] = None
    evaluated_version: str = ""
    model_version: str = ""
    accepted_nodes: list[str] = Field(default_factory=list)
    rejected_nodes: dict[str, str] = Field(default_factory=dict)
    single_client: bool = False
    aggregated: bool = False
    status: str = "failed"


# Database dependency
db_manager = DatabaseManager()
tracker = ExperimentTracker(db_manager)


# API Routes

@router.get("", response_model=list[ExperimentSchema])
async def list_experiments(
    limit: int = Query(100, ge=1, le=1000),
    offset: int = Query(0, ge=0),
    status: Optional[str] = Query(None),
):
    """List experiments, optionally filtered by status."""
    experiments = tracker.list_experiments(limit=limit, offset=offset, status=status)
    return [ExperimentSchema.model_validate(e) for e in experiments]


@router.get("/{experiment_id}", response_model=ExperimentDetailSchema)
async def get_experiment(experiment_id: str):
    """Get experiment by ID."""
    experiment = tracker.get_experiment(experiment_id)
    if not experiment:
        raise HTTPException(status_code=404, detail="Experiment not found")
    return ExperimentDetailSchema.model_validate(experiment)


@router.get("/{experiment_id}/summary", response_model=ExperimentSummarySchema)
async def get_experiment_summary(experiment_id: str):
    """Get experiment summary with metrics."""
    summary = tracker.get_experiment_summary(experiment_id)
    if not summary:
        raise HTTPException(status_code=404, detail="Experiment not found")
    return ExperimentSummarySchema.model_validate(summary)


@router.get("/{experiment_id}/rounds", response_model=list[RoundSchema])
async def get_experiment_rounds(experiment_id: str, limit: int = Query(1000, ge=1, le=10000)):
    """Get all rounds for an experiment."""
    rounds = tracker.get_rounds(experiment_id, limit=limit)
    return [RoundSchema.model_validate(r) for r in rounds]


@router.post("", response_model=ExperimentSchema, status_code=201)
async def create_experiment(request: ExperimentCreateRequest):
    """Create a new experiment."""
    experiment_id = tracker.start_experiment(
        name=request.name,
        experiment_type=request.experiment_type,
        config=request.config,
        seed=request.seed,
        epochs=request.epochs,
        batch_size=request.batch_size,
        learning_rate=request.learning_rate,
        model_name=request.model_name,
        model_version=request.model_version,
        gateway_config=request.gateway_config,
        description=request.description,
    )

    experiment = tracker.get_experiment(experiment_id)
    if not experiment:
        raise HTTPException(status_code=500, detail="Failed to create experiment")

    return ExperimentSchema.model_validate(experiment)


@router.patch("/{experiment_id}", response_model=ExperimentSchema)
async def update_experiment(experiment_id: str, request: ExperimentUpdateRequest):
    """Update an experiment."""
    with get_db_session() as session:
        from sqlalchemy import select
        from .database import Experiment
        stmt = select(Experiment).where(Experiment.id == experiment_id)
        experiment = session.scalar(stmt)

        if not experiment:
            raise HTTPException(status_code=404, detail="Experiment not found")

        if request.name is not None:
            experiment.name = request.name
        if request.description is not None:
            experiment.description = request.description
        if request.status is not None:
            experiment.status = request.status

        session.add(experiment)
        session.flush()

    return ExperimentSchema.model_validate(experiment)


@router.post("/rounds", status_code=201)
async def submit_round(round: RoundSubmission):
    """Submit a round outcome."""
    # Verify experiment exists
    experiment = tracker.get_experiment(round.experiment_id)
    if not experiment:
        raise HTTPException(status_code=404, detail="Experiment not found")

    tracker.record_round(
        experiment_id=round.experiment_id,
        round_number=round.round_number,
        selected_nodes=round.selected_nodes,
        received_count=round.received_count,
        dropped_nodes=round.dropped_nodes,
        bytes_up=round.bytes_up,
        bytes_down=round.bytes_down,
        round_time_sec=round.round_time_sec,
        weighted_val_loss=round.weighted_val_loss,
        evaluated_version=round.evaluated_version,
        model_version=round.model_version,
        accepted_nodes=round.accepted_nodes,
        rejected_nodes=round.rejected_nodes,
        single_client=round.single_client,
        aggregated=round.aggregated,
        status=round.status,
    )

    return JSONResponse(content={"status": "ok", "round": round.round_number})


@router.post("/rounds/{round_number}", status_code=201, response_model=dict)
async def submit_round_by_number(
    round_number: int,
    experiment_id: str = Query(..., description="Experiment ID"),
    round: RoundSubmission = None,
):
    """Submit a round outcome by round number with request body."""
    experiment = tracker.get_experiment(experiment_id)
    if not experiment:
        raise HTTPException(status_code=404, detail="Experiment not found")

    if round is None:
        round = RoundSubmission(
            experiment_id=experiment_id,
            round_number=round_number,
        )

    tracker.record_round(
        experiment_id=experiment_id,
        round_number=round_number,
        selected_nodes=round.selected_nodes,
        received_count=round.received_count,
        dropped_nodes=round.dropped_nodes,
        bytes_up=round.bytes_up,
        bytes_down=round.bytes_down,
        round_time_sec=round.round_time_sec,
        weighted_val_loss=round.weighted_val_loss,
        evaluated_version=round.evaluated_version,
        model_version=round.model_version,
        accepted_nodes=round.accepted_nodes,
        rejected_nodes=round.rejected_nodes,
        single_client=round.single_client,
        aggregated=round.aggregated,
        status=round.status,
    )

    return {"status": "ok", "round": round_number}


@router.post("/{experiment_id}/complete")
async def complete_experiment(
    experiment_id: str,
    val_loss: Optional[float] = Query(None),
    val_acc: Optional[float] = Query(None),
    test_loss: Optional[float] = Query(None),
    test_acc: Optional[float] = Query(None),
    duration_sec: Optional[float] = Query(None),
):
    """Mark experiment as complete."""
    experiment = tracker.get_experiment(experiment_id)
    if not experiment:
        raise HTTPException(status_code=404, detail="Experiment not found")

    tracker.complete_experiment(
        experiment_id,
        final_val_loss=val_loss,
        final_val_acc=val_acc,
        final_test_loss=test_loss,
        final_test_acc=test_acc,
        total_duration_sec=duration_sec,
    )

    return JSONResponse(content={"status": "completed"})


@router.delete("/{experiment_id}", status_code=204)
async def delete_experiment(experiment_id: str):
    """Delete an experiment and all its data."""
    from sqlalchemy import select, delete
    from .database import Experiment, RoundOutcome, ExperimentMetrics

    with get_db_session() as session:
        # Check experiment exists
        stmt = select(Experiment).where(Experiment.id == experiment_id)
        experiment = session.scalar(stmt)
        if not experiment:
            raise HTTPException(status_code=404, detail="Experiment not found")

        # Delete related data first
        session.execute(delete(RoundOutcome).where(RoundOutcome.experiment_id == experiment_id))
        session.execute(delete(ExperimentMetrics).where(ExperimentMetrics.experiment_id == experiment_id))

        # Delete experiment
        session.execute(delete(Experiment).where(Experiment.id == experiment_id))

    return JSONResponse(content=None, status_code=204)


@router.post("/recover-stage4")
async def recover_stage4_experiment(stage4_path: str):
    """Create an experiment record from a Stage 4 experiment directory."""
    path = Path(stage4_path)
    if not path.exists():
        raise HTTPException(status_code=404, detail=f"Stage4 path not found: {stage4_path}")

    try:
        experiment_id = create_experiment_from_stage4_path(path)
        return {"experiment_id": experiment_id, "status": "recovered"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# WebSocket-style real-time updates would go here
# For now, we provide polling endpoints


def setup_experiment_routes(app):
    """Add experiment routes to the FastAPI app."""
    app.include_router(router)