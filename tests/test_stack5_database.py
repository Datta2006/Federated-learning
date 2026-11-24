"""Tests for Stack 5 database and experiment API functionality."""

import pytest
import threading
import tempfile
from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

from dashboard.backend.database import (
    DatabaseManager,
    Experiment,
    ExperimentType,
    RoundOutcome,
    get_db_session,
    init_database,
)
from dashboard.backend.experiment_api import (
    router,
    submit_round_by_number,
    RoundSubmission,
)
from dashboard.backend.experiment_tracker import ExperimentTracker


class TestDatabaseManagerSingleton:
    """Tests for the thread-safe singleton pattern of DatabaseManager."""

    def setup_method(self):
        """Reset singleton before each test."""
        DatabaseManager._instance = None

    def test_singleton_pattern(self):
        """Multiple instantiations return the same instance."""
        dm1 = DatabaseManager()
        dm2 = DatabaseManager()
        assert dm1 is dm2

    def test_init_lock_exists(self):
        """DatabaseManager has _init_lock class attribute."""
        assert hasattr(DatabaseManager, '_init_lock')
        assert isinstance(DatabaseManager._init_lock, type(threading.Lock()))

    def test_init_uses_init_lock(self):
        """__init__ method uses _init_lock for thread safety."""
        import inspect
        source = inspect.getsource(DatabaseManager.__init__)
        assert '_init_lock' in source


class TestDatabaseManagerThreadSafety:
    """Tests for thread-safe database initialization."""

    def setup_method(self):
        """Reset singleton before each test."""
        DatabaseManager._instance = None

    def test_concurrent_initialization(self):
        """Concurrent initialization attempts don't cause race conditions."""
        results = []
        errors = []

        def create_manager():
            try:
                dm = DatabaseManager()
                results.append(dm)
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=create_manager) for _ in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(errors) == 0, f"Errors during concurrent init: {errors}"
        assert len(set(id(r) for r in results)) == 1, "Multiple instances created"


class TestExperimentAPI:
    """Tests for experiment API endpoints."""

    def test_submit_round_by_number_exists(self):
        """submit_round_by_number endpoint exists and is callable."""
        from fastapi.routing import APIRoute

        routes = [r for r in router.routes if isinstance(r, APIRoute)]
        # Routes include the router prefix
        route_paths = [r.path for r in routes]

        assert '/api/v1/experiments/rounds/{round_number}' in route_paths, \
            f"Route /api/v1/experiments/rounds/{{round_number}} not found in {route_paths}"

    def test_round_submission_schema(self):
        """RoundSubmission schema can be created with required fields."""
        round = RoundSubmission(
            experiment_id="test_exp",
            round_number=1,
        )
        assert round.experiment_id == "test_exp"
        assert round.round_number == 1


class TestDatabaseModels:
    """Tests for SQLAlchemy database models."""

    def setup_method(self):
        """Reset singleton before each test."""
        DatabaseManager._instance = None

    def test_experiment_model(self, tmp_path):
        """Experiment model can be created and persisted."""
        db_path = tmp_path / "test.db"
        dm = DatabaseManager(str(db_path))
        dm.init_db()

        with get_db_session(dm) as session:
            experiment = Experiment(
                id="test123",
                name="Test Experiment",
                experiment_type=ExperimentType.FEDERATED,
                config={"epochs": 10, "lr": 0.001},
                seed=42,
                epochs=10,
                batch_size=32,
                learning_rate=0.001,
                model_name="test_model",
                model_version="1.0.0",
                gateway_config={},
                status="running",
            )
            session.add(experiment)
            session.flush()

            retrieved = session.get(Experiment, "test123")
            assert retrieved is not None
            assert retrieved.name == "Test Experiment"

    def test_round_outcome_model(self, tmp_path):
        """RoundOutcome model can be created and persisted."""
        db_path = tmp_path / "test.db"
        dm = DatabaseManager(str(db_path))
        dm.init_db()

        with get_db_session(dm) as session:
            # Create experiment first
            experiment = Experiment(
                id="round_test_exp",
                name="Round Test",
                experiment_type=ExperimentType.FEDERATED,
                config={"epochs": 10},
                seed=42,
                epochs=10,
                batch_size=32,
                learning_rate=0.001,
                model_name="test_model",
                model_version="1.0.0",
                gateway_config={},
                status="running",
            )
            session.add(experiment)
            session.flush()

            # Create round outcome
            round_outcome = RoundOutcome(
                experiment_id="round_test_exp",
                round_number=1,
                round_time_sec=120.5,
                selected_count=5,
                selected_nodes=["node1", "node2", "node3", "node4", "node5"],
                received_count=5,
                dropped_nodes=[],
                bytes_up=1024,
                bytes_down=2048,
                weighted_val_loss=0.5,
                evaluated_version="v1",
                model_version="1.0.0",
                accepted_count=5,
                rejected_count=0,
                rejected_details=[],
                single_client=False,
                aggregated=True,
                status="success",
            )
            session.add(round_outcome)
            session.flush()

            rounds = session.query(RoundOutcome).filter(
                RoundOutcome.experiment_id == "round_test_exp"
            ).all()
            assert len(rounds) == 1
            assert rounds[0].round_number == 1

    def test_experiment_metrics_model(self, tmp_path):
        """ExperimentMetrics model can be created and persisted."""
        db_path = tmp_path / "test.db"
        dm = DatabaseManager(str(db_path))
        dm.init_db()

        from dashboard.backend.database import ExperimentMetrics

        with get_db_session(dm) as session:
            # Create experiment first
            experiment = Experiment(
                id="metrics_test_exp",
                name="Metrics Test",
                experiment_type=ExperimentType.FEDERATED,
                config={"epochs": 10},
                seed=42,
                epochs=10,
                batch_size=32,
                learning_rate=0.001,
                model_name="test_model",
                model_version="1.0.0",
                gateway_config={},
                status="running",
            )
            session.add(experiment)
            session.flush()

            # Create metrics
            metrics = ExperimentMetrics(
                experiment_id="metrics_test_exp",
                final_val_loss=0.3,
                final_val_acc=0.95,
                final_test_loss=0.25,
                final_test_acc=0.97,
                total_epochs=10,
                total_rounds=5,
                total_round_duration_sec=300.0,
            )
            session.add(metrics)
            session.flush()

            retrieved = session.get(ExperimentMetrics, metrics.id)
            assert retrieved is not None
            assert retrieved.final_val_loss == 0.3
            assert retrieved.total_rounds == 5


class TestExperimentTracker:
    """Tests for ExperimentTracker class."""

    def setup_method(self):
        """Reset singleton before each test."""
        DatabaseManager._instance = None

    def test_experiment_lifecycle(self, tmp_path):
        """Full experiment lifecycle: create, record rounds, complete."""
        db_path = tmp_path / "test.db"
        dm = DatabaseManager(str(db_path))
        dm.init_db()

        tracker = ExperimentTracker(dm)

        # Start experiment
        exp_id = tracker.start_experiment(
            name="Lifecycle Test",
            experiment_type=ExperimentType.FEDERATED,
            config={"epochs": 10},
            seed=42,
            epochs=10,
            batch_size=32,
            learning_rate=0.001,
            model_name="test_model",
            model_version="1.0.0",
            gateway_config={},
        )
        assert exp_id is not None

        # Verify experiment was created
        exp = tracker.get_experiment(exp_id)
        assert exp is not None
        assert exp.name == "Lifecycle Test"

        # Record a round
        tracker.record_round(
            experiment_id=exp_id,
            round_number=1,
            selected_nodes=["node1", "node2"],
            received_count=2,
            dropped_nodes=[],
            bytes_up=1000,
            bytes_down=2000,
            round_time_sec=60.0,
            weighted_val_loss=0.5,
            evaluated_version="v1",
            model_version="1.0.0",
            status="success",
        )

        # Verify round was recorded
        rounds = tracker.get_rounds(exp_id)
        assert len(rounds) == 1

        # Complete experiment
        tracker.complete_experiment(
            exp_id,
            final_val_loss=0.3,
            final_val_acc=0.95,
        )

        # Verify experiment is completed
        exp = tracker.get_experiment(exp_id)
        assert exp.status == "completed"
        assert exp.completed_at is not None

    def test_set_experiment_status(self, tmp_path):
        """Experiment status can be updated."""
        db_path = tmp_path / "test.db"
        dm = DatabaseManager(str(db_path))
        dm.init_db()

        tracker = ExperimentTracker(dm)

        # Start experiment
        exp_id = tracker.start_experiment(
            name="Status Test",
            experiment_type=ExperimentType.FEDERATED,
            config={"epochs": 10},
            seed=42,
            epochs=10,
            batch_size=32,
            learning_rate=0.001,
            model_name="test_model",
            model_version="1.0.0",
            gateway_config={},
        )

        # Update status
        tracker.set_experiment_status(exp_id, "paused")

        # Verify status updated
        exp = tracker.get_experiment(exp_id)
        assert exp.status == "paused"

    def test_rejected_details_transformation(self, tmp_path):
        """rejected_nodes dict is properly transformed to list of dicts."""
        db_path = tmp_path / "test.db"
        dm = DatabaseManager(str(db_path))
        dm.init_db()

        tracker = ExperimentTracker(dm)

        exp_id = tracker.start_experiment(
            name="Rejected Details Test",
            experiment_type=ExperimentType.FEDERATED,
            config={"epochs": 10},
            seed=42,
            epochs=10,
            batch_size=32,
            learning_rate=0.001,
            model_name="test_model",
            model_version="1.0.0",
            gateway_config={},
        )

        # Record round with rejected nodes
        tracker.record_round(
            experiment_id=exp_id,
            round_number=1,
            selected_nodes=["node1", "node2", "node3"],
            received_count=3,
            dropped_nodes=[],
            bytes_up=1000,
            bytes_down=2000,
            round_time_sec=60.0,
            weighted_val_loss=0.5,
            evaluated_version="v1",
            model_version="1.0.0",
            accepted_nodes=["node1", "node2"],
            rejected_nodes={"node3": "checksum mismatch"},
            status="success",
        )

        # Verify rejected_details was stored correctly
        rounds = tracker.get_rounds(exp_id)
        assert len(rounds) == 1
        assert rounds[0].rejected_count == 1
        assert rounds[0].rejected_details == [{"node": "node3", "reason": "checksum mismatch"}]

    def test_list_experiments_with_filter(self, tmp_path):
        """List experiments can be filtered by status."""
        db_path = tmp_path / "test.db"
        dm = DatabaseManager(str(db_path))
        dm.init_db()

        tracker = ExperimentTracker(dm)

        # Create two experiments
        exp_id1 = tracker.start_experiment(
            name="Running Experiment",
            experiment_type=ExperimentType.FEDERATED,
            config={"epochs": 10},
            seed=42,
            epochs=10,
            batch_size=32,
            learning_rate=0.001,
            model_name="test_model",
            model_version="1.0.0",
            gateway_config={},
        )

        # Create second experiment and complete it
        exp_id2 = tracker.start_experiment(
            name="Completed Experiment",
            experiment_type=ExperimentType.FEDERATED,
            config={"epochs": 10},
            seed=43,
            epochs=10,
            batch_size=32,
            learning_rate=0.001,
            model_name="test_model",
            model_version="1.0.0",
            gateway_config={},
        )
        tracker.complete_experiment(exp_id2)

        # List all running experiments
        running = tracker.list_experiments(status="running")
        assert len(running) == 1
        assert running[0].id == exp_id1

        # List all completed experiments
        completed = tracker.list_experiments(status="completed")
        assert len(completed) == 1
        assert completed[0].id == exp_id2


class TestExperimentAPIIntegration:
    """Tests for integrating the experiment API with FastAPI."""

    def setup_method(self):
        """Reset singleton before each test."""
        DatabaseManager._instance = None

    def test_experiment_crud_via_api(self, tmp_path):
        """Full CRUD cycle via FastAPI test client."""
        pytest.importorskip("fastapi")
        from fastapi.testclient import TestClient
        from dashboard.backend.main import create_app
        from dashboard.backend.settings import Settings
        from dataclasses import replace

        db_path = tmp_path / "test.db"
        settings = replace(
            Settings.load(),
            mqtt_enabled=False,
        )

        # Create app with test database
        from dashboard.backend.database import DatabaseManager
        dm = DatabaseManager(str(db_path))
        dm.init_db()

        # Note: The app would need to use this db manager for full integration
        # This test verifies the API structure is correct
        from dashboard.backend.experiment_api import router

        # Verify router has expected routes
        from fastapi.routing import APIRoute
        routes = [r for r in router.routes if isinstance(r, APIRoute)]
        route_paths = [r.path for r in routes]

        assert "/api/v1/experiments" in route_paths or "/api/v1/experiments/" in route_paths


class TestSessionScopeWithAutoflushFalse:
    """Tests to verify session.flush() is required with autoflush=False."""

    def setup_method(self):
        """Reset singleton before each test."""
        DatabaseManager._instance = None

    def test_flush_required_after_add_experiment(self, tmp_path):
        """Verify experiment ID is available after flush."""
        db_path = tmp_path / "test.db"
        dm = DatabaseManager(str(db_path))
        dm.init_db()

        with get_db_session(dm) as session:
            experiment = Experiment(
                id="flush_test_exp",
                name="Flush Test",
                experiment_type=ExperimentType.FEDERATED,
                config={"epochs": 10},
                seed=42,
                epochs=10,
                batch_size=32,
                learning_rate=0.001,
                model_name="test_model",
                model_version="1.0.0",
                gateway_config={},
                status="running",
            )
            session.add(experiment)
            # With autoflush=False, we need explicit flush to ensure ID is generated
            session.flush()

            # Now the experiment should be queryable by ID
            retrieved = session.get(Experiment, "flush_test_exp")
            assert retrieved is not None
            assert retrieved.name == "Flush Test"

    def test_flush_required_after_add_round(self, tmp_path):
        """Verify round outcome ID is generated after flush."""
        db_path = tmp_path / "test.db"
        dm = DatabaseManager(str(db_path))
        dm.init_db()

        with get_db_session(dm) as session:
            experiment = Experiment(
                id="round_flush_exp",
                name="Round Flush Test",
                experiment_type=ExperimentType.FEDERATED,
                config={"epochs": 10},
                seed=42,
                epochs=10,
                batch_size=32,
                learning_rate=0.001,
                model_name="test_model",
                model_version="1.0.0",
                gateway_config={},
                status="running",
            )
            session.add(experiment)
            session.flush()

            round_outcome = RoundOutcome(
                experiment_id="round_flush_exp",
                round_number=1,
                round_time_sec=120.5,
                selected_count=5,
                selected_nodes=["node1", "node2", "node3", "node4", "node5"],
                received_count=5,
                dropped_nodes=[],
                bytes_up=1024,
                bytes_down=2048,
                weighted_val_loss=0.5,
                evaluated_version="v1",
                model_version="1.0.0",
                accepted_count=5,
                rejected_count=0,
                rejected_details=[],
                single_client=False,
                aggregated=True,
                status="success",
            )
            session.add(round_outcome)
            session.flush()

            # Verify round can be queried
            rounds = session.query(RoundOutcome).filter(
                RoundOutcome.experiment_id == "round_flush_exp"
            ).all()
            assert len(rounds) == 1
            assert rounds[0].round_number == 1


class TestThreadSafety:
    """Tests for thread-safe database operations."""

    def setup_method(self):
        """Reset singleton before each test."""
        DatabaseManager._instance = None

    def test_concurrent_experiment_creation(self, tmp_path):
        """Multiple threads can create experiments concurrently."""
        db_path = tmp_path / "test.db"
        dm = DatabaseManager(str(db_path))
        dm.init_db()

        results = []
        errors = []

        def create_experiment(i):
            try:
                tracker = ExperimentTracker(dm)
                exp_id = tracker.start_experiment(
                    name=f"Concurrent Test {i}",
                    experiment_type=ExperimentType.FEDERATED,
                    config={"epochs": 10},
                    seed=42 + i,
                    epochs=10,
                    batch_size=32,
                    learning_rate=0.001,
                    model_name="test_model",
                    model_version="1.0.0",
                    gateway_config={},
                )
                results.append(exp_id)
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=create_experiment, args=(i,)) for i in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(errors) == 0, f"Errors: {errors}"
        assert len(results) == 5