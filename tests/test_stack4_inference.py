"""Tests for Stack 4: Edge Inference and Monitoring components."""

from __future__ import annotations

import json
import threading
import time
from unittest.mock import MagicMock, patch

import numpy as np
import pytest

from simulator.model_deployment import ModelDeploymentComponent, ModelCheckpoint
from simulator.inference import InferenceComponent, InferenceResult
from simulator.forecasting import ForecastingComponent, ForecastResult
from simulator.monitoring import MonitoringComponent, GatewayMetrics


class TestModelDeploymentComponent:
    """Tests for ModelDeploymentComponent."""

    def test_initialization(self):
        """Test component initialization."""
        comp = ModelDeploymentComponent(
            gateway_id="gw-01",
            base_topic="aq",
            mqtt_client=None,
            local_storage=None,
        )
        assert comp.gateway_id == "gw-01"
        assert comp.active_version is None
        assert comp.active_weights is None
        assert not comp.has_model

    def test_start_stop_subscription(self):
        """Test MQTT subscription lifecycle."""
        mock_client = MagicMock()
        comp = ModelDeploymentComponent(
            gateway_id="gw-01",
            base_topic="aq",
            mqtt_client=mock_client,
            local_storage=None,
        )
        result = comp.start()
        assert result["status"] == "subscribed"
        assert "aq/model/global" in result["topic"]
        mock_client.subscribe.assert_called_once()

        result = comp.stop()
        assert result["status"] == "unsubscribed"
        mock_client.unsubscribe.assert_called_once()

    def test_process_model_payload_valid(self):
        """Test processing a valid model payload."""
        import base64
        from common.model import build_model, flatten_weights

        # Create a mock model and get its weights
        model = build_model(window_hours=24, n_features=5)
        weights = model.get_weights()
        weights_b64 = base64.b64encode(flatten_weights(model)).decode("ascii")
        shapes = [w.shape for w in weights]

        payload = {
            "model_version": 1,
            "parameters": sum(w.size for w in weights),
            "weights_b64": weights_b64,
            "shapes": shapes,
            "metrics": {"val_loss": 0.5, "val_mae": 0.3},
        }

        comp = ModelDeploymentComponent(
            gateway_id="gw-01",
            base_topic="aq",
            mqtt_client=None,
            local_storage=None,
        )

        comp._process_model_payload(payload, "aq/model/global")

        assert comp.active_version == 1
        assert comp.active_weights is not None
        assert len(comp.active_weights) == len(weights)
        assert comp._checkpoints[1].version == 1
        assert comp._checkpoints[1].metrics["val_loss"] == 0.5

    def test_process_model_payload_missing_fields(self):
        """Test that missing fields are rejected."""
        comp = ModelDeploymentComponent(
            gateway_id="gw-01",
            base_topic="aq",
            mqtt_client=None,
            local_storage=None,
        )

        # Missing version
        comp._process_model_payload({"weights_b64": "abc"}, "aq/model/global")
        assert comp.active_version is None

        # Missing weights
        comp._process_model_payload({"model_version": 1}, "aq/model/global")
        assert comp.active_version is None

    def test_validate_architecture(self):
        """Test architecture validation."""
        from common.model import build_model

        model = build_model(window_hours=24, n_features=5)
        expected_hash = ModelDeploymentComponent._compute_architecture_hash(
            None, model.get_weights()
        )

        comp = ModelDeploymentComponent(
            gateway_id="gw-01",
            base_topic="aq",
            mqtt_client=None,
            local_storage=None,
            expected_architecture_hash=expected_hash,
        )

        # Valid weights should pass
        assert comp._validate_architecture(model.get_weights())

        # Invalid weights (different shape) should fail
        invalid_weights = [np.ones((10, 10), dtype=np.float32)]
        assert not comp._validate_architecture(invalid_weights)

    def test_rollback(self):
        """Test model rollback functionality."""
        import base64
        from common.model import build_model, flatten_weights

        model = build_model(window_hours=24, n_features=5)
        weights = model.get_weights()
        weights_b64 = base64.b64encode(flatten_weights(model)).decode("ascii")
        shapes = [w.shape for w in weights]

        comp = ModelDeploymentComponent(
            gateway_id="gw-01",
            base_topic="aq",
            mqtt_client=None,
            local_storage=None,
        )

        # Deploy version 1
        payload_v1 = {
            "model_version": 1,
            "parameters": sum(w.size for w in weights),
            "weights_b64": weights_b64,
            "shapes": shapes,
            "metrics": {"val_loss": 0.5},
        }
        comp._process_model_payload(payload_v1, "aq/model/global")

        # Deploy version 2 (different weights)
        weights_v2 = [w * 2 for w in weights]
        # Need a new model for v2 weights
        model_v2 = build_model(window_hours=24, n_features=5)
        model_v2.set_weights(weights_v2)
        weights_b64_v2 = base64.b64encode(flatten_weights(model_v2)).decode("ascii")
        payload_v2 = {
            "model_version": 2,
            "parameters": sum(w.size for w in weights_v2),
            "weights_b64": weights_b64_v2,
            "shapes": shapes,
            "metrics": {"val_loss": 0.4},
        }
        comp._process_model_payload(payload_v2, "aq/model/global")
        assert comp.active_version == 2

        # Rollback to version 1
        result = comp.rollback(1)
        assert result["status"] == "ok"
        assert result["rolled_back_to"] == 1
        assert comp.active_version == 1
        assert np.allclose(comp.active_weights[0], weights[0])

    def test_rollback_nonexistent(self):
        """Test rollback to non-existent version."""
        comp = ModelDeploymentComponent(
            gateway_id="gw-01",
            base_topic="aq",
            mqtt_client=None,
            local_storage=None,
        )
        result = comp.rollback(999)
        assert result["status"] == "error"
        assert "not found" in result["message"]

    def test_prune_checkpoints(self):
        """Test checkpoint pruning."""
        import base64
        from common.model import build_model, flatten_weights

        model = build_model(window_hours=24, n_features=5)
        weights = model.get_weights()
        weights_b64 = base64.b64encode(flatten_weights(model)).decode("ascii")
        shapes = [w.shape for w in weights]

        comp = ModelDeploymentComponent(
            gateway_id="gw-01",
            base_topic="aq",
            mqtt_client=None,
            local_storage=None,
            max_checkpoints=2,
        )

        # Deploy 3 versions
        for v in [1, 2, 3]:
            payload = {
                "model_version": v,
                "parameters": sum(w.size for w in weights),
                "weights_b64": weights_b64,
                "shapes": shapes,
                "metrics": {"val_loss": 0.5 - v * 0.1},
            }
            comp._process_model_payload(payload, "aq/model/global")

        # Only 2 should remain (max_checkpoints=2)
        assert len(comp._checkpoints) == 2
        assert 1 not in comp._checkpoints
        assert 2 in comp._checkpoints
        assert 3 in comp._checkpoints


class TestInferenceComponent:
    """Tests for InferenceComponent."""

    @pytest.fixture
    def inference_component(self):
        """Create an InferenceComponent with a mock model deployment."""
        from common.model import build_model
        import base64

        mock_deployment = MagicMock()
        model = build_model(window_hours=24, n_features=5)
        mock_deployment.active_weights = model.get_weights()
        mock_deployment.active_version = 1
        mock_deployment._active_architecture_hash = "test_hash"

        comp = InferenceComponent(
            gateway_id="gw-01",
            model_deployment=mock_deployment,
            window_hours=24,
            horizon=1,
        )
        # Manually set the model since we're mocking the deployment
        comp._model = model
        comp._model_version = 1
        return comp

    def test_preprocess_window(self, inference_component):
        """Test window preprocessing matches training exactly."""
        pm25 = np.random.uniform(0, 100, 24).astype(np.float32)
        temp = np.random.uniform(10, 30, 24).astype(np.float32)
        rh = np.random.uniform(30, 80, 24).astype(np.float32)
        timestamps = np.array([f"2026-01-01T{h:02d}:00:00" for h in range(24)], dtype="datetime64[ns]")

        window = inference_component.preprocess_window(pm25, temp, rh, timestamps)

        assert window is not None
        assert window.shape == (24, 5)  # 3 features + 2 cyclic hour
        assert window.dtype == np.float32
        # First 3 columns should be scaled to [0, 1] (pm25, temp, rh)
        assert np.all(window[:, 0] >= 0)
        assert np.all(window[:, 0] <= 1)
        assert np.all(window[:, 1] >= 0)
        assert np.all(window[:, 1] <= 1)
        assert np.all(window[:, 2] >= 0)
        assert np.all(window[:, 2] <= 1)
        # Last 2 columns are sine/cosine of hour (can be negative)
        assert window[:, 3].min() >= -1 and window[:, 3].max() <= 1
        assert window[:, 4].min() >= -1 and window[:, 4].max() <= 1

    def test_preprocess_window_wrong_length(self, inference_component):
        """Test preprocessing rejects wrong window length."""
        pm25 = np.random.uniform(0, 100, 12).astype(np.float32)
        temp = np.random.uniform(10, 30, 12).astype(np.float32)
        rh = np.random.uniform(30, 80, 12).astype(np.float32)
        timestamps = np.array([f"2026-01-01T{h:02d}:00:00" for h in range(12)], dtype="datetime64[ns]")

        window = inference_component.preprocess_window(pm25, temp, rh, timestamps)
        assert window is None

    def test_infer_without_model(self):
        """Test inference returns None when model not loaded."""
        mock_deployment = MagicMock()
        mock_deployment.active_weights = None
        mock_deployment.active_version = None

        comp = InferenceComponent(
            gateway_id="gw-01",
            model_deployment=mock_deployment,
            window_hours=24,
            horizon=1,
        )

        pm25 = np.random.uniform(0, 100, 24).astype(np.float32)
        temp = np.random.uniform(10, 30, 24).astype(np.float32)
        rh = np.random.uniform(30, 80, 24).astype(np.float32)
        timestamps = np.array([f"2026-01-01T{h:02d}:00:00" for h in range(24)], dtype="datetime64[ns]")

        result = comp.infer(pm25, temp, rh, timestamps)
        assert result is None

    def test_infer_with_model(self, inference_component):
        """Test inference with loaded model."""
        pm25 = np.random.uniform(0, 100, 24).astype(np.float32)
        temp = np.random.uniform(10, 30, 24).astype(np.float32)
        rh = np.random.uniform(30, 80, 24).astype(np.float32)
        timestamps = np.array([f"2026-01-01T{h:02d}:00:00" for h in range(24)], dtype="datetime64[ns]")

        result = inference_component.infer(pm25, temp, rh, timestamps)

        assert result is not None
        assert isinstance(result, InferenceResult)
        assert isinstance(result.pm25_current, float)
        assert isinstance(result.pm25_predicted, float)
        assert isinstance(result.pm25_delta_pred, float)
        assert result.model_version == 1
        assert result.inference_ms > 0

    def test_infer_batch(self, inference_component):
        """Test batch inference."""
        windows = []
        for _ in range(3):
            pm25 = np.random.uniform(0, 100, 24).astype(np.float32)
            temp = np.random.uniform(10, 30, 24).astype(np.float32)
            rh = np.random.uniform(30, 80, 24).astype(np.float32)
            timestamps = np.array([f"2026-01-01T{h:02d}:00:00" for h in range(24)], dtype="datetime64[ns]")
            windows.append((pm25, temp, rh, timestamps))

        results = inference_component.infer_batch(windows)

        assert len(results) == 3
        for result in results:
            assert result is not None
            assert isinstance(result, InferenceResult)

    def test_get_stats(self, inference_component):
        """Test stats collection."""
        stats = inference_component.get_stats()
        assert stats["gateway_id"] == "gw-01"
        assert stats["window_hours"] == 24
        assert stats["horizon"] == 1
        assert "model_loaded" in stats
        assert "model_version" in stats


class TestForecastingComponent:
    """Tests for ForecastingComponent."""

    @pytest.fixture
    def forecasting_component(self):
        """Create a ForecastingComponent with mock inference component."""
        from common.model import build_model
        import base64

        mock_deployment = MagicMock()
        model = build_model(window_hours=24, n_features=5)
        mock_deployment.active_weights = model.get_weights()
        mock_deployment.active_version = 1
        mock_deployment._active_architecture_hash = "test_hash"

        mock_inference = MagicMock()
        mock_inference._model = model
        mock_inference._model_version = 1
        mock_inference._ensure_model_loaded.return_value = True

        comp = ForecastingComponent(
            gateway_id="gw-01",
            inference_component=mock_inference,
            model_deployment=mock_deployment,
            window_hours=24,
            default_horizon=6,
        )
        # The forecasting component uses the inference component's model directly
        # So we need to make sure the inference mock has the model
        return comp

    def test_check_thresholds(self, forecasting_component):
        """Test WHO AQI threshold checking."""
        pm25_values = [3.0, 10.0, 20.0, 40.0, 60.0, 100.0]
        crossed = forecasting_component._check_thresholds(pm25_values)

        # Should detect crossings for each threshold
        threshold_names = [c["threshold"] for c in crossed]
        assert "good" in threshold_names  # 5.0
        assert "moderate" in threshold_names  # 15.0
        assert "unhealthy_sensitive" in threshold_names  # 25.0
        assert "unhealthy" in threshold_names  # 37.5
        assert "very_unhealthy" in threshold_names  # 50.0
        assert "hazardous" in threshold_names  # 75.0

    def test_forecast_without_model(self):
        """Test forecast returns None when model not loaded."""
        mock_deployment = MagicMock()
        mock_deployment.active_weights = None

        mock_inference = MagicMock()
        mock_inference._ensure_model_loaded.return_value = False

        comp = ForecastingComponent(
            gateway_id="gw-01",
            inference_component=mock_inference,
            model_deployment=mock_deployment,
        )

        pm25 = np.random.uniform(0, 100, 24).astype(np.float32)
        temp = np.random.uniform(10, 30, 24).astype(np.float32)
        rh = np.random.uniform(30, 80, 24).astype(np.float32)
        timestamps = np.array([f"2026-01-01T{h:02d}:00:00" for h in range(24)], dtype="datetime64[ns]")

        result = comp.forecast(pm25, temp, rh, timestamps)
        assert result is None

    def test_forecast_with_model(self, forecasting_component):
        """Test multi-horizon forecast."""
        pm25 = np.random.uniform(0, 100, 24).astype(np.float32)
        temp = np.random.uniform(10, 30, 24).astype(np.float32)
        rh = np.random.uniform(30, 80, 24).astype(np.float32)
        timestamps = np.array([f"2026-01-01T{h:02d}:00:00" for h in range(24)], dtype="datetime64[ns]")

        result = forecasting_component.forecast(pm25, temp, rh, timestamps, horizon=6)

        assert result is not None
        assert isinstance(result, ForecastResult)
        assert len(result.pm25_forecast) == 6
        assert result.horizon == 6
        assert isinstance(result.pm25_current, float)
        assert isinstance(result.thresholds_crossed, list)
        assert result.inference_ms > 0
        assert result.model_version == 1

    def test_forecast_batch(self, forecasting_component):
        """Test batch forecasting."""
        windows = []
        for _ in range(2):
            pm25 = np.random.uniform(0, 100, 24).astype(np.float32)
            temp = np.random.uniform(10, 30, 24).astype(np.float32)
            rh = np.random.uniform(30, 80, 24).astype(np.float32)
            timestamps = np.array([f"2026-01-01T{h:02d}:00:00" for h in range(24)], dtype="datetime64[ns]")
            windows.append((pm25, temp, rh, timestamps))

        results = forecasting_component.forecast_batch(windows, horizon=3)

        assert len(results) == 2
        for result in results:
            assert result is not None
            assert len(result.pm25_forecast) == 3

    def test_get_stats(self, forecasting_component):
        """Test stats collection."""
        stats = forecasting_component.get_stats()
        assert stats["gateway_id"] == "gw-01"
        assert stats["window_hours"] == 24
        assert stats["default_horizon"] == 6
        assert "alert_thresholds" in stats
        assert "model_loaded" in stats


class TestMonitoringComponent:
    """Tests for MonitoringComponent."""

    def test_initialization(self):
        """Test component initialization."""
        comp = MonitoringComponent(
            gateway_id="gw-01",
            mqtt_client=None,
            local_storage=None,
            inference_component=None,
            model_deployment=None,
            collection_interval_seconds=30,
            history_limit=1000,
        )
        assert comp.gateway_id == "gw-01"
        assert comp.collection_interval == 30
        assert comp.history_limit == 1000
        assert not comp._running

    def test_configure_snmp(self):
        """Test SNMPv3 configuration."""
        comp = MonitoringComponent(
            gateway_id="gw-01",
            mqtt_client=None,
            local_storage=None,
            inference_component=None,
            model_deployment=None,
        )

        config = comp.configure_snmp(
            enabled=True,
            port=161,
            user="test_user",
            auth_proto="SHA",
            priv_proto="AES",
        )

        assert config["enabled"] is True
        assert config["port"] == 161
        assert config["user"] == "test_user"
        assert config["auth_protocol"] == "SHA"
        assert config["priv_protocol"] == "AES"

    def test_get_snmp_metrics(self):
        """Test SNMP-compatible metrics format."""
        comp = MonitoringComponent(
            gateway_id="gw-01",
            mqtt_client=None,
            local_storage=None,
            inference_component=None,
            model_deployment=None,
        )

        # Mock collect to return basic metrics
        with patch.object(comp, "_collect_system") as mock_sys:
            mock_sys.return_value = type("obj", (object,), {
                "cpu_percent": 50.0,
                "memory_percent": 60.0,
                "disk_percent": 70.0,
                "battery_percent": 80.0,
            })()
            with patch.object(comp, "_collect_mqtt") as mock_mqtt:
                mock_mqtt.return_value = type("obj", (object,), {
                    "messages_published": 100,
                    "messages_received": 50,
                    "connected": True,
                })()
                with patch.object(comp, "_collect_inference") as mock_inf:
                    mock_inf.return_value = type("obj", (object,), {
                        "inference_count": 10,
                        "avg_inference_ms": 25.0,
                        "model_version": 1,
                    })()
                    with patch.object(comp, "_collect_storage") as mock_stor:
                        mock_stor.return_value = type("obj", (object,), {
                            "total_size_bytes": 1024,
                            "total_files": 5,
                        })()
                        metrics = comp.get_snmp_metrics()

        assert "1.3.6.1.4.1.99999.1.1" in metrics  # CPU
        assert "1.3.6.1.4.1.99999.1.2" in metrics  # Memory
        assert "1.3.6.1.4.1.99999.1.3" in metrics  # Disk
        assert "1.3.6.1.4.1.99999.1.4" in metrics  # Battery
        assert "1.3.6.1.4.1.99999.2.1" in metrics  # MQTT pub
        assert "1.3.6.1.4.1.99999.2.2" in metrics  # MQTT recv
        assert "1.3.6.1.4.1.99999.2.3" in metrics  # MQTT connected
        assert "1.3.6.1.4.1.99999.3.1" in metrics  # Inference count
        assert "1.3.6.1.4.1.99999.3.2" in metrics  # Avg latency
        assert "1.3.6.1.4.1.99999.3.3" in metrics  # Model version
        assert "1.3.6.1.4.1.99999.4.1" in metrics  # Storage total
        assert "1.3.6.1.4.1.99999.4.2" in metrics  # Storage files

    def test_start_stop_collection(self):
        """Test background collection lifecycle."""
        comp = MonitoringComponent(
            gateway_id="gw-01",
            mqtt_client=None,
            local_storage=None,
            inference_component=None,
            model_deployment=None,
            collection_interval_seconds=1,  # Fast for testing
        )

        result = comp.start()
        assert result["status"] == "started"
        assert comp._running
        time.sleep(0.5)  # Let it collect at least once
        result = comp.stop()
        assert result["status"] == "stopped"
        assert not comp._running
        assert comp._collection_count > 0

    def test_collect_single_snapshot(self):
        """Test single metrics collection."""
        comp = MonitoringComponent(
            gateway_id="gw-01",
            mqtt_client=None,
            local_storage=None,
            inference_component=None,
            model_deployment=None,
        )

        metrics = comp.collect()

        assert metrics is not None
        assert isinstance(metrics, GatewayMetrics)
        assert metrics.gateway_id == "gw-01"
        assert hasattr(metrics, "system")
        assert hasattr(metrics, "network")
        assert hasattr(metrics, "mqtt")
        assert hasattr(metrics, "storage")
        assert hasattr(metrics, "inference")

    def test_record_mqtt_events(self):
        """Test MQTT event recording."""
        comp = MonitoringComponent(
            gateway_id="gw-01",
            mqtt_client=None,
            local_storage=None,
            inference_component=None,
            model_deployment=None,
        )

        comp.record_mqtt_publish(success=True)
        comp.record_mqtt_publish(success=True)
        comp.record_mqtt_publish(success=False)
        comp.record_mqtt_receive(success=True)
        comp.record_mqtt_reconnect()

        stats = comp.get_stats()
        assert stats["mqtt"]["published"] == 2
        assert stats["mqtt"]["publish_errors"] == 1
        assert stats["mqtt"]["received"] == 1
        assert stats["mqtt"]["reconnect_count"] == 1

    def test_record_inference_events(self):
        """Test inference event recording."""
        comp = MonitoringComponent(
            gateway_id="gw-01",
            mqtt_client=None,
            local_storage=None,
            inference_component=None,
            model_deployment=None,
        )

        comp.record_inference(10.0, success=True)
        comp.record_inference(20.0, success=True)
        comp.record_inference(30.0, success=False)

        stats = comp.get_stats()
        assert stats["inference"]["count"] == 2
        assert stats["inference"]["errors"] == 1
        assert stats["inference"]["avg_ms"] == 15.0
        assert stats["inference"]["last_ms"] == 20.0

    def test_get_history(self):
        """Test metrics history retrieval."""
        comp = MonitoringComponent(
            gateway_id="gw-01",
            mqtt_client=None,
            local_storage=None,
            inference_component=None,
            model_deployment=None,
            collection_interval_seconds=1,
        )

        comp.start()
        time.sleep(0.5)
        comp.stop()

        history = comp.get_history(limit=10)
        assert len(history) > 0
        for entry in history:
            assert "gateway_id" in entry
            assert "timestamp" in entry


class TestGatewayIntegration:
    """Integration tests for Gateway with Stack 4 components."""

    def test_gateway_has_stack4_components(self):
        """Test that gateway has all Stack 4 components."""
        from simulator.entities import GatewayNode, Position
        from simulator.topology import NetworkTopology
        from simulator.rpl import RPLEngine
        from simulator.gateway import create_gateway, Gateway
        from unittest.mock import MagicMock

        gateway_node = GatewayNode("gw-01", "Test Gateway", position=Position(0, 0))
        topology = NetworkTopology("test")
        topology.add_gateway_node(gateway_node)
        rpl_engine = RPLEngine(topology)

        # Mock the MQTT client to avoid connection
        with patch("paho.mqtt.client.Client") as mock_client_class:
            mock_client = MagicMock()
            mock_client_class.return_value = mock_client

            gateway = create_gateway(
                gateway_node=gateway_node,
                topology=topology,
                rpl_engine=rpl_engine,
                broker_host="localhost",
                broker_port=1883,
            )

        assert hasattr(gateway, "model_deployment")
        assert hasattr(gateway, "inference")
        assert hasattr(gateway, "forecasting")
        assert hasattr(gateway, "monitoring")

    def test_gateway_stats_includes_stack4(self):
        """Test gateway stats includes Stack 4 components."""
        from simulator.entities import GatewayNode, Position
        from simulator.topology import NetworkTopology
        from simulator.rpl import RPLEngine
        from simulator.gateway import create_gateway, Gateway
        from unittest.mock import MagicMock

        gateway_node = GatewayNode("gw-01", "Test Gateway", position=Position(0, 0))
        topology = NetworkTopology("test")
        topology.add_gateway_node(gateway_node)
        rpl_engine = RPLEngine(topology)

        # Mock the MQTT client to avoid connection
        with patch("paho.mqtt.client.Client") as mock_client_class:
            mock_client = MagicMock()
            mock_client_class.return_value = mock_client

            gateway = create_gateway(
                gateway_node=gateway_node,
                topology=topology,
                rpl_engine=rpl_engine,
                broker_host="localhost",
                broker_port=1883,
            )

        stats = gateway.get_stats()
        assert "model_deployment" in stats
        assert "inference" in stats
        assert "forecasting" in stats
        assert "monitoring" in stats

    def test_gateway_to_dict_includes_stack4(self):
        """Test gateway serialization includes Stack 4."""
        from simulator.entities import GatewayNode, Position
        from simulator.topology import NetworkTopology
        from simulator.rpl import RPLEngine
        from simulator.gateway import create_gateway, Gateway
        from unittest.mock import MagicMock

        gateway_node = GatewayNode("gw-01", "Test Gateway", position=Position(0, 0))
        topology = NetworkTopology("test")
        topology.add_gateway_node(gateway_node)
        rpl_engine = RPLEngine(topology)

        # Mock the MQTT client to avoid connection
        with patch("paho.mqtt.client.Client") as mock_client_class:
            mock_client = MagicMock()
            mock_client_class.return_value = mock_client

            gateway = create_gateway(
                gateway_node=gateway_node,
                topology=topology,
                rpl_engine=rpl_engine,
                broker_host="localhost",
                broker_port=1883,
            )

        d = gateway.to_dict()
        assert "model_deployment" in d
        assert "inference" in d
        assert "forecasting" in d
        assert "monitoring" in d


if __name__ == "__main__":
    pytest.main([__file__, "-v"])