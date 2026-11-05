"""Tests for retained global-model delivery and late joiners."""

from __future__ import annotations

import subprocess
import threading
import uuid

import numpy as np
import pytest

from common.model_delivery import GlobalModelPublisher, GlobalModelReceiver
from common.mqtt_utils import create_client, loads
from common.weight_transfer import (
    global_announce_topic,
    global_chunk_filter,
    make_dummy_weights,
)
from tests.broker_utils import free_port, start_broker

pytest.importorskip("paho.mqtt.client")


def _dummy_model(seed: int, count: int = 500):
    return make_dummy_weights(count=count, seed=seed)


def _publish_directly(client, base_topic, weights, version):
    return GlobalModelPublisher(
        client,
        base_topic,
        chunk_size=2048,
        retain=True,
        wait=False,
    ).publish(
        weights,
        model_version=version,
        model_config={},
        kind="dummy",
    )


def test_receiver_buffers_chunks_that_arrive_before_the_announce():
    weights = _dummy_model(7)
    publisher = GlobalModelPublisher(None, "aq", chunk_size=2048, wait=False)
    published = publisher.build(weights, model_version="v0001", model_config={}, kind="dummy")
    receiver = GlobalModelReceiver("aq")

    # Deliver chunks first, then the announce, simulating unordered retained
    # delivery when a late subscriber connects.
    for index in reversed(range(len(published.chunks))):
        assert receiver.handle_message(
            published.chunk_topics[index], published.chunk_messages[index]
        ) is None

    result = receiver.handle_message(
        global_announce_topic("aq"), published.metadata
    )

    assert result is not None
    assert result.metadata["model_version"] == "v0001"
    np.testing.assert_array_equal(result.weights, weights)


def test_receiver_ignores_an_older_version_after_a_newer_announce():
    older = _dummy_model(1)
    newer = _dummy_model(2)
    publisher = GlobalModelPublisher(None, "aq", chunk_size=2048, wait=False)
    first = publisher.build(older, model_version="v0001", model_config={}, kind="dummy")
    second = publisher.build(newer, model_version="v0002", model_config={}, kind="dummy")
    receiver = GlobalModelReceiver("aq")

    assert receiver.handle_message(global_announce_topic("aq"), second.metadata) is None
    for index, message in enumerate(second.chunk_messages):
        result = receiver.handle_message(second.chunk_topics[index], message)
    assert result is not None
    assert result.metadata["model_version"] == "v0002"
    np.testing.assert_array_equal(result.weights, newer)

    # A stale retained chunk from v0001 must not complete or replace v0002.
    assert receiver.handle_message(first.chunk_topics[0], first.chunk_messages[0]) is None
    assert receiver.latest_version == "v0002"


def test_a_late_subscriber_gets_the_retained_global_model(tmp_path):
    port = free_port()
    broker = start_broker(tmp_path, port)
    client = create_client(
        f"publisher-{uuid.uuid4().hex[:6]}", "127.0.0.1", port, keepalive=10
    )
    connected = threading.Event()

    def on_connect(client, userdata, flags, reason_code, properties=None):
        del userdata, flags, reason_code, properties
        connected.set()

    client.on_connect = on_connect
    client.connect("127.0.0.1", port, 10)
    client.loop_start()
    try:
        assert connected.wait(timeout=5.0)
        weights = _dummy_model(11, count=900)
        _publish_directly(client, "aq", weights, "v0003")
        # Wait until the broker has accepted the retained publishes.
        client.publish("aq/test/sync", "done", qos=1).wait_for_publish(timeout=5.0)

        received: list = []
        done = threading.Event()
        subscriber = create_client(
            f"late-{uuid.uuid4().hex[:6]}", "127.0.0.1", port, keepalive=10
        )
        receiver = GlobalModelReceiver("aq")

        def on_sub_connect(client, userdata, flags, reason_code, properties=None):
            del userdata, flags, reason_code, properties
            client.subscribe(
                [(global_announce_topic("aq"), 1), (global_chunk_filter("aq"), 1)]
            )

        def on_message(client, userdata, message):
            del client, userdata
            result = receiver.handle_message(message.topic, loads(message.payload))
            if result is not None:
                received.append(result)
                done.set()

        subscriber.on_connect = on_sub_connect
        subscriber.on_message = on_message
        subscriber.connect("127.0.0.1", port, 10)
        subscriber.loop_start()
        try:
            assert done.wait(timeout=10.0), "late subscriber did not assemble the model"
            assert len(received) == 1
            assert received[0].metadata["model_version"] == "v0003"
            np.testing.assert_array_equal(received[0].weights, weights)
        finally:
            subscriber.disconnect()
            subscriber.loop_stop()
    finally:
        client.disconnect()
        client.loop_stop()
        broker.terminate()
        try:
            broker.wait(timeout=5)
        except subprocess.TimeoutExpired:  # pragma: no cover - cleanup
            broker.kill()
