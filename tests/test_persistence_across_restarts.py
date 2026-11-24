"""Test to verify data persists across application restarts.

This test simulates:
1. Creating an experiment with rounds
2. Closing the database (app shutdown)
3. Reopening the database (app restart)
4. Verifying all data is still present
"""

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
    ExperimentMetrics,
    TelemetryRecord,
    ForecastRecord,
    AlertRecord,
    get_db_session,
    init_database,
)
from dashboard.backend.experiment_tracker import ExperimentTracker


class TestPersistenceAcrossRestarts:
    """Tests for data persistence across database manager restarts."""

    def setup_method(self):
        """Reset singleton before each test."""
        DatabaseManager._instance = None

    def test_experiment_survives_database_restart(self, tmp_path):
        """Verify experiment data persists after closing and reopening database."""
        db_path = tmp_path / "persistence_test.db"

        # ============================================================
        # PHASE 1: Create and record experiment data
        # ============================================================
        dm1 = DatabaseManager(str(db_path))
        dm1.init_db()

        tracker = ExperimentTracker(dm1)

        # Start experiment
        exp_id = tracker.start_experiment(
            name="Persistence Test Run",
            experiment_type=ExperimentType.FEDERATED,
            config={"epochs": 10, "batch_size": 32, "learning_rate": 0.001},
            seed=42,
            epochs=10,
            batch_size=32,
            learning_rate=0.001,
            model_name="resnet50",
            model_version="1.0.0",
            gateway_config={"timeout": 30, "max_nodes": 100}
        )

        # Record 3 rounds with different outcomes
        for round_num in range(1, 4):
            tracker.record_round(
                experiment_id=exp_id,
                round_number=round_num,
                selected_nodes=[f"node-{i}" for i in range(1, 4)],
                received_count=3,
                dropped_nodes=["node-3"] if round_num == 2 else [],
                bytes_up=1024 * round_num,
                bytes_down=2048 * round_num,
                round_time_sec=60.0 * round_num,
                weighted_val_loss=0.5 - 0.1 * round_num,
                evaluated_version=f"v{round_num}",
                model_version="1.0.0",
                rejected_nodes={"node-3": "checksum mismatch"} if round_num == 2 else {},
                status="success"
            )

        # Complete experiment
        tracker.complete_experiment(
            exp_id,
            final_val_loss=0.25,
            final_val_acc=0.92,
            total_duration_sec=300.0
        )

        # Verify initial data exists
        with get_db_session(dm1) as session:
            exp_count = session.query(Experiment).count()
            round_count = session.query(RoundOutcome).count()
            metrics_count = session.query(ExperimentMetrics).count()

            assert exp_count == 1, f"Expected 1 experiment, got {exp_count}"
            assert round_count == 3, f"Expected 3 rounds, got {round_count}"
            assert metrics_count == 1, f"Expected 1 metrics record, got {metrics_count}"

        # ============================================================
        # PHASE 2: Close and restart (simulating app restart)
        # ============================================================
        dm1.close()

        # Create new manager with same db path (simulating app restart)
        dm2 = DatabaseManager(str(db_path))
        dm2.init_db()

        # ============================================================
        # PHASE 3: Verify persistence across restart
        # ============================================================
        with get_db_session(dm2) as session:
            # Get experiment
            exp = session.get(Experiment, exp_id)
            assert exp is not None, "Experiment not found after restart!"
            assert exp.status == "completed", f"Wrong status: {exp.status}"
            assert exp.name == "Persistence Test Run", f"Wrong name: {exp.name}"

            # Get rounds
            rounds = session.query(RoundOutcome).filter(
                RoundOutcome.experiment_id == exp_id
            ).order_by(RoundOutcome.round_number).all()
            assert len(rounds) == 3, f"Wrong round count: {len(rounds)}"

            # Verify rejected nodes in round 2 (dropped nodes go to rejected_nodes/rejected_details)
            round2 = rounds[1]
            assert round2.dropped_nodes == ["node-3"], f"Wrong dropped: {round2.dropped_nodes}"
            assert round2.rejected_count == 1, f"Wrong rejected_count: {round2.rejected_count}"

            # Get metrics
            metrics = session.query(ExperimentMetrics).filter(
                ExperimentMetrics.experiment_id == exp_id
            ).first()
            assert metrics is not None, "Metrics not found after restart!"
            assert metrics.final_val_loss == 0.25, f"Wrong final_val_loss: {metrics.final_val_loss}"
            assert metrics.final_val_acc == 0.92, f"Wrong final_val_acc: {metrics.final_val_acc}"
            assert metrics.total_rounds == 3, f"Wrong total_rounds: {metrics.total_rounds}"

    def test_multiple_experiments_persist(self, tmp_path):
        """Verify multiple experiments persist correctly across restarts."""
        db_path = tmp_path / "multi_exp_test.db"

        # Create database
        dm = DatabaseManager(str(db_path))
        dm.init_db()

        tracker = ExperimentTracker(dm)

        # Create 3 experiments
        exp_ids = []
        for i in range(3):
            exp_id = tracker.start_experiment(
                name=f"Experiment {i+1}",
                experiment_type=ExperimentType.FEDERATED,
                config={"epochs": 10},
                seed=42 + i,
                epochs=10,
                batch_size=32,
                learning_rate=0.001,
                model_name="model",
                model_version="1.0.0",
                gateway_config={},
            )
            exp_ids.append(exp_id)
            tracker.complete_experiment(exp_id, final_val_loss=0.1 * (i+1))

        # Close and restart
        dm.close()
        dm2 = DatabaseManager(str(db_path))
        dm2.init_db()

        # Verify all experiments exist
        with get_db_session(dm2) as session:
            experiments = session.query(Experiment).order_by(Experiment.name).all()
            assert len(experiments) == 3, f"Expected 3 experiments, got {len(experiments)}"

            for i, exp in enumerate(experiments):
                assert exp.name == f"Experiment {i+1}", f"Wrong name: {exp.name}"
                assert exp.status == "completed", f"Wrong status: {exp.status}"

    def test_round_data_with_rejected_nodes(self, tmp_path):
        """Verify rejected nodes data persists correctly."""
        db_path = tmp_path / "rejected_nodes_test.db"

        dm = DatabaseManager(str(db_path))
        dm.init_db()

        tracker = ExperimentTracker(dm)

        # Create experiment with rejected nodes
        exp_id = tracker.start_experiment(
            name="Rejected Nodes Test",
            experiment_type=ExperimentType.FEDERATED,
            config={"epochs": 10},
            seed=42,
            epochs=10,
            batch_size=32,
            learning_rate=0.001,
            model_name="model",
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

        # Close and restart
        dm.close()
        dm2 = DatabaseManager(str(db_path))
        dm2.init_db()

        # Verify rejected_details was stored correctly
        with get_db_session(dm2) as session:
            round = session.query(RoundOutcome).filter(
                RoundOutcome.experiment_id == exp_id
            ).first()

            assert round is not None, "Round not found after restart!"
            assert round.rejected_count == 1, f"Wrong rejected_count: {round.rejected_count}"
            assert round.rejected_details == [{"node": "node3", "reason": "checksum mismatch"}], \
                f"Wrong rejected_details: {round.rejected_details}"


class TestTelemetryPersistence:
    """Tests for MQTT telemetry data persistence."""

    def setup_method(self):
        """Reset singleton before each test."""
        DatabaseManager._instance = None

    def test_telemetry_record_persists(self, tmp_path):
        """Verify TelemetryRecord persists across database restarts."""
        db_path = tmp_path / "telemetry_test.db"

        # Create database
        dm = DatabaseManager(str(db_path))
        dm.init_db()

        # Create experiment first
        tracker = ExperimentTracker(dm)
        exp_id = tracker.start_experiment(
            name="Telemetry Test",
            experiment_type=ExperimentType.FEDERATED,
            config={"epochs": 10},
            seed=42,
            epochs=10,
            batch_size=32,
            learning_rate=0.001,
            model_name="model",
            model_version="1.0.0",
            gateway_config={},
        )

        # Record telemetry data
        with get_db_session(dm) as session:
            telemetry = TelemetryRecord(
                experiment_id=exp_id,
                topic="airfed/fl/telemetry",
                node_id="node-1",
                message_type="round_stats",
                payload={
                    "round": 1,
                    "bytes_up": 1024,
                    "bytes_down": 2048,
                    "accuracy": 0.85,
                },
            )
            session.add(telemetry)
            session.flush()

        # Close and restart
        dm.close()
        dm2 = DatabaseManager(str(db_path))
        dm2.init_db()

        # Verify telemetry persisted
        with get_db_session(dm2) as session:
            records = session.query(TelemetryRecord).filter(
                TelemetryRecord.experiment_id == exp_id
            ).all()
            assert len(records) == 1, f"Expected 1 record, got {len(records)}"
            assert records[0].topic == "airfed/fl/telemetry"
            assert records[0].node_id == "node-1"
            assert records[0].payload["accuracy"] == 0.85


class TestForecastPersistence:
    """Tests for forecast/prediction data persistence."""

    def setup_method(self):
        """Reset singleton before each test."""
        DatabaseManager._instance = None

    def test_forecast_record_persists(self, tmp_path):
        """Verify ForecastRecord persists across database restarts."""
        db_path = tmp_path / "forecast_test.db"

        # Create database
        dm = DatabaseManager(str(db_path))
        dm.init_db()

        # Create experiment
        tracker = ExperimentTracker(dm)
        exp_id = tracker.start_experiment(
            name="Forecast Test",
            experiment_type=ExperimentType.FEDERATED,
            config={"epochs": 10},
            seed=42,
            epochs=10,
            batch_size=32,
            learning_rate=0.001,
            model_name="model",
            model_version="1.0.0",
            gateway_config={},
        )

        # Record forecast data
        with get_db_session(dm) as session:
            forecast = ForecastRecord(
                experiment_id=exp_id,
                forecast_type="accuracy_prediction",
                version="v1.0.0",
                predictions=[0.85, 0.87, 0.89, 0.91, 0.92],
                confidence_interval=(0.80, 0.95),
                mae=0.03,
                rmse=0.04,
            )
            session.add(forecast)
            session.flush()

        # Close and restart
        dm.close()
        dm2 = DatabaseManager(str(db_path))
        dm2.init_db()

        # Verify forecast persisted
        with get_db_session(dm2) as session:
            forecasts = session.query(ForecastRecord).filter(
                ForecastRecord.experiment_id == exp_id
            ).all()
            assert len(forecasts) == 1
            assert forecasts[0].forecast_type == "accuracy_prediction"
            assert forecasts[0].predictions == [0.85, 0.87, 0.89, 0.91, 0.92]
            assert forecasts[0].mae == 0.03
            assert forecasts[0].rmse == 0.04


class TestAlertPersistence:
    """Tests for alert/anomaly record persistence."""

    def setup_method(self):
        """Reset singleton before each test."""
        DatabaseManager._instance = None

    def test_alert_record_persists(self, tmp_path):
        """Verify AlertRecord persists across database restarts."""
        db_path = tmp_path / "alert_test.db"

        # Create database
        dm = DatabaseManager(str(db_path))
        dm.init_db()

        # Create experiment
        tracker = ExperimentTracker(dm)
        exp_id = tracker.start_experiment(
            name="Alert Test",
            experiment_type=ExperimentType.FEDERATED,
            config={"epochs": 10},
            seed=42,
            epochs=10,
            batch_size=32,
            learning_rate=0.001,
            model_name="model",
            model_version="1.0.0",
            gateway_config={},
        )

        # Record alert
        with get_db_session(dm) as session:
            alert = AlertRecord(
                experiment_id=exp_id,
                alert_type="convergence_warning",
                severity="warning",
                message="Validation loss plateau detected at round 15",
                details={
                    "round": 15,
                    "loss_value": 0.45,
                    "threshold": 0.40,
                },
                resolved=False,
            )
            session.add(alert)
            session.flush()

        # Close and restart
        dm.close()
        dm2 = DatabaseManager(str(db_path))
        dm2.init_db()

        # Verify alert persisted
        with get_db_session(dm2) as session:
            alerts = session.query(AlertRecord).filter(
                AlertRecord.experiment_id == exp_id
            ).all()
            assert len(alerts) == 1
            assert alerts[0].alert_type == "convergence_warning"
            assert alerts[0].severity == "warning"
            assert alerts[0].resolved is False
            assert alerts[0].message == "Validation loss plateau detected at round 15"


class TestCompleteExperimentWithTelemetryForecastAlert:
    """Integration test for complete experiment with all record types."""

    def setup_method(self):
        """Reset singleton before each test."""
        DatabaseManager._instance = None

    def test_full_experiment_with_all_record_types(self, tmp_path):
        """Verify complete experiment flow with telemetry, forecast, and alert records."""
        db_path = tmp_path / "full_integration_test.db"

        # Create database
        dm = DatabaseManager(str(db_path))
        dm.init_db()

        tracker = ExperimentTracker(dm)

        # Start experiment
        exp_id = tracker.start_experiment(
            name="Full Integration Test",
            experiment_type=ExperimentType.FEDERATED,
            config={"epochs": 10, "batch_size": 32},
            seed=123,
            epochs=10,
            batch_size=32,
            learning_rate=0.001,
            model_name="resnet50",
            model_version="2.0.0",
            gateway_config={"max_nodes": 50},
        )

        # Record rounds
        for round_num in range(1, 4):
            tracker.record_round(
                experiment_id=exp_id,
                round_number=round_num,
                selected_nodes=[f"node-{i}" for i in range(3)],
                received_count=3,
                dropped_nodes=[],
                bytes_up=1024,
                bytes_down=2048,
                round_time_sec=60.0,
                weighted_val_loss=0.5,
                evaluated_version=f"v{round_num}",
                model_version="2.0.0",
                status="success",
            )

        # Record telemetry (simulating MQTT message)
        with get_db_session(dm) as session:
            telemetry = TelemetryRecord(
                experiment_id=exp_id,
                topic="airfed/fl/telemetry",
                node_id="gateway-1",
                message_type="system_health",
                payload={"memory_mb": 512, "cpu_percent": 45.5},
            )
            session.add(telemetry)
            session.flush()

        # Record forecast
        with get_db_session(dm) as session:
            forecast = ForecastRecord(
                experiment_id=exp_id,
                forecast_type="final_model_performance",
                version="v3.0.0",
                predictions=[0.88, 0.89, 0.90],
                mae=0.02,
                rmse=0.03,
            )
            session.add(forecast)
            session.flush()

        # Record alert
        with get_db_session(dm) as session:
            alert = AlertRecord(
                experiment_id=exp_id,
                alert_type="schedule_warning",
                severity="info",
                message="Experiment running 10% behind schedule",
                resolved=True,  # Alert was resolved
            )
            session.add(alert)
            session.flush()

        # Complete experiment
        tracker.complete_experiment(
            exp_id, final_val_loss=0.3, final_val_acc=0.88
        )

        # Close and restart
        dm.close()
        dm2 = DatabaseManager(str(db_path))
        dm2.init_db()

        # Verify all data persisted
        with get_db_session(dm2) as session:
            # Experiment
            exp = session.get(Experiment, exp_id)
            assert exp is not None
            assert exp.name == "Full Integration Test"
            assert exp.status == "completed"

            # Rounds
            rounds = session.query(RoundOutcome).filter(
                RoundOutcome.experiment_id == exp_id
            ).all()
            assert len(rounds) == 3

            # Metrics
            metrics = session.query(ExperimentMetrics).filter(
                ExperimentMetrics.experiment_id == exp_id
            ).first()
            assert metrics is not None
            assert metrics.final_val_loss == 0.3

            # Telemetry
            telemetry_count = session.query(TelemetryRecord).filter(
                TelemetryRecord.experiment_id == exp_id
            ).count()
            assert telemetry_count == 1

            # Forecast
            forecast_count = session.query(ForecastRecord).filter(
                ForecastRecord.experiment_id == exp_id
            ).count()
            assert forecast_count == 1

            # Alert
            alert_count = session.query(AlertRecord).filter(
                AlertRecord.experiment_id == exp_id
            ).count()
            assert alert_count == 1
            alert = session.query(AlertRecord).filter(
                AlertRecord.experiment_id == exp_id
            ).first()
            assert alert.message == "Experiment running 10% behind schedule"