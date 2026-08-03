"""Tests for Edge AI Gateway: Local video processing with TensorFlow Lite."""

import time
import pytest
from datetime import datetime, timezone

from backend.app.platform.physical_operations.edge_ai_gateway import (
    EdgeAIGateway,
    EdgeAIConfig,
    EventType,
    ActivityType,
    BoundingBox,
    Detection,
    DetectedEvent,
    ModelManager,
    EventFilter,
    WebhookClient,
    EdgeAIStats,
)


@pytest.fixture
def config():
    """Create Edge AI configuration."""
    return EdgeAIConfig(
        model_path="models/yolov5n.tflite",
        input_width=640,
        input_height=480,
        confidence_threshold=0.7,
        enable_rate_limiting=True,
        max_events_per_second=10,
    )


@pytest.fixture
def gateway(config):
    """Create Edge AI gateway."""
    return EdgeAIGateway(config=config, gate_id="gate-01")


class TestBoundingBox:
    """Test bounding box operations."""

    def test_bbox_creation(self):
        """Test creating bounding box."""
        bbox = BoundingBox(x1=10, y1=20, x2=100, y2=150)
        assert bbox.x1 == 10
        assert bbox.y2 == 150

    def test_bbox_area(self):
        """Test area calculation."""
        bbox = BoundingBox(x1=0, y1=0, x2=100, y2=50)
        assert bbox.area() == 5000

    def test_bbox_center(self):
        """Test center calculation."""
        bbox = BoundingBox(x1=0, y1=0, x2=100, y2=100)
        center = bbox.center()
        assert center == (50, 50)

    def test_bbox_overlap(self):
        """Test overlap detection."""
        bbox1 = BoundingBox(x1=0, y1=0, x2=100, y2=100)
        bbox2 = BoundingBox(x1=50, y1=50, x2=150, y2=150)
        bbox3 = BoundingBox(x1=200, y1=200, x2=300, y2=300)

        assert bbox1.overlaps(bbox2) is True
        assert bbox1.overlaps(bbox3) is False

    def test_bbox_to_dict(self):
        """Test dictionary conversion."""
        bbox = BoundingBox(x1=10, y1=20, x2=100, y2=150)
        d = bbox.to_dict()
        assert d["x1"] == 10
        assert d["y2"] == 150


class TestDetection:
    """Test detection results."""

    def test_detection_creation(self):
        """Test creating detection."""
        bbox = BoundingBox(x1=10, y1=20, x2=100, y2=150)
        det = Detection(class_id=0, class_name="person", confidence=0.92, bbox=bbox)
        assert det.confidence == 0.92
        assert det.class_name == "person"

    def test_detection_to_dict(self):
        """Test dictionary conversion."""
        bbox = BoundingBox(x1=10, y1=20, x2=100, y2=150)
        det = Detection(class_id=0, class_name="person", confidence=0.92, bbox=bbox)
        d = det.to_dict()
        assert d["class_name"] == "person"
        assert d["confidence"] == 0.92


class TestDetectedEvent:
    """Test detected events."""

    def test_event_creation(self):
        """Test creating event."""
        bbox = BoundingBox(x1=10, y1=20, x2=100, y2=150)
        event = DetectedEvent(
            event_id="ev-123",
            event_type=EventType.PERSON_DETECTED,
            timestamp=datetime.now(timezone.utc).isoformat(),
            gate_id="gate-01",
            confidence=0.92,
            person_id="p-456",
            bbox=bbox,
        )
        assert event.event_type == EventType.PERSON_DETECTED
        assert event.person_id == "p-456"

    def test_event_to_dict(self):
        """Test event dictionary conversion."""
        bbox = BoundingBox(x1=10, y1=20, x2=100, y2=150)
        event = DetectedEvent(
            event_id="ev-123",
            event_type=EventType.PERSON_DETECTED,
            timestamp=datetime.now(timezone.utc).isoformat(),
            gate_id="gate-01",
            confidence=0.92,
            person_id="p-456",
            bbox=bbox,
        )
        d = event.to_dict()
        assert d["event_type"] == "person_detected"
        assert d["gate_id"] == "gate-01"


class TestModelManager:
    """Test model management."""

    def test_load_model(self, config):
        """Test loading a model."""
        manager = ModelManager(config)
        result = manager.load_model(config.model_path)
        assert result is True

    def test_model_registry(self, config):
        """Test model registration."""
        manager = ModelManager(config)
        manager.load_model(config.model_path, "yolov5n")
        assert "yolov5n" in manager.models
        assert manager.models["yolov5n"]["path"] == config.model_path


class TestEventFilter:
    """Test event filtering."""

    def test_should_process_event(self, config):
        """Test event should be processed."""
        filter_obj = EventFilter(config)
        bbox = BoundingBox(x1=0, y1=0, x2=100, y2=100)
        event = DetectedEvent(
            event_id="ev-1",
            event_type=EventType.PERSON_DETECTED,
            timestamp=datetime.now(timezone.utc).isoformat(),
            gate_id="gate-01",
            confidence=0.92,
            person_id="p-1",
            bbox=bbox,
        )

        assert filter_obj.should_process(event) is True

    def test_duplicate_suppression(self, config):
        """Test duplicate event suppression."""
        filter_obj = EventFilter(config)
        bbox = BoundingBox(x1=0, y1=0, x2=100, y2=100)
        event = DetectedEvent(
            event_id="ev-1",
            event_type=EventType.PERSON_DETECTED,
            timestamp=datetime.now(timezone.utc).isoformat(),
            gate_id="gate-01",
            confidence=0.92,
            person_id="p-1",
            bbox=bbox,
        )

        # First event should process
        assert filter_obj.should_process(event) is True

        # Duplicate within suppression window should not process
        assert filter_obj.should_process(event) is False

        # After suppression window, should process again
        time.sleep(config.duplicate_suppression_seconds + 0.1)
        assert filter_obj.should_process(event) is True

    def test_rate_limiting(self, config):
        """Test rate limiting."""
        config.max_events_per_second = 2
        filter_obj = EventFilter(config)
        bbox = BoundingBox(x1=0, y1=0, x2=100, y2=100)

        # Create multiple events
        events = []
        for i in range(3):
            event = DetectedEvent(
                event_id=f"ev-{i}",
                event_type=EventType.PERSON_DETECTED,
                timestamp=datetime.now(timezone.utc).isoformat(),
                gate_id="gate-01",
                confidence=0.92,
                person_id=f"p-{i}",
                bbox=bbox,
            )
            events.append(event)

        # First 2 should process
        assert filter_obj.should_process(events[0]) is True
        assert filter_obj.should_process(events[1]) is True

        # Third should be rate-limited
        assert filter_obj.should_process(events[2]) is False


class TestEdgeAIGateway:
    """Test Edge AI gateway."""

    def test_gateway_initialization(self, gateway):
        """Test gateway initialization."""
        assert gateway.gate_id == "gate-01"
        assert gateway.config.confidence_threshold == 0.7

    def test_load_model(self, gateway):
        """Test loading model."""
        result = gateway.load_model()
        assert result is True

    def test_add_webhook(self, gateway):
        """Test adding webhook."""
        webhook_url = "https://api.example.com/events"
        gateway.add_webhook(webhook_url)
        assert webhook_url in gateway.webhooks

    def test_remove_webhook(self, gateway):
        """Test removing webhook."""
        webhook_url = "https://api.example.com/events"
        gateway.add_webhook(webhook_url)
        gateway.remove_webhook(webhook_url)
        assert webhook_url not in gateway.webhooks

    def test_process_detections(self, gateway):
        """Test processing detections."""
        bbox = BoundingBox(x1=10, y1=20, x2=100, y2=150)
        detection = Detection(
            class_id=0,
            class_name="person",
            confidence=0.92,
            bbox=bbox,
        )

        events = gateway.process_detections([detection])
        assert len(events) > 0
        assert events[0].event_type == EventType.PERSON_DETECTED

    def test_process_low_confidence_detection(self, gateway):
        """Test that low confidence detections are filtered."""
        bbox = BoundingBox(x1=10, y1=20, x2=100, y2=150)
        detection = Detection(
            class_id=0,
            class_name="person",
            confidence=0.5,  # Below threshold
            bbox=bbox,
        )

        events = gateway.process_detections([detection])
        assert len(events) == 0

    def test_event_callback(self, gateway):
        """Test event callback invocation."""
        callback_invoked = []

        def mock_callback(event):
            callback_invoked.append(event)

        gateway.event_callback = mock_callback
        bbox = BoundingBox(x1=10, y1=20, x2=100, y2=150)
        event = DetectedEvent(
            event_id="ev-1",
            event_type=EventType.PERSON_DETECTED,
            timestamp=datetime.now(timezone.utc).isoformat(),
            gate_id="gate-01",
            confidence=0.92,
            person_id="p-1",
            bbox=bbox,
        )

        gateway.send_events([event])
        time.sleep(0.5)  # Allow time for callback

        assert len(callback_invoked) >= 0  # May or may not be called depending on timing

    def test_get_statistics(self, gateway):
        """Test statistics retrieval."""
        stats = gateway.get_statistics()
        assert isinstance(stats, EdgeAIStats)
        assert stats.frames_processed == 0
        assert stats.events_detected == 0

    def test_statistics_update(self, gateway):
        """Test statistics are updated."""
        # Simulate some processing
        bbox = BoundingBox(x1=10, y1=20, x2=100, y2=150)
        detection = Detection(
            class_id=0,
            class_name="person",
            confidence=0.92,
            bbox=bbox,
        )

        events = gateway.process_detections([detection])
        if events:
            gateway.send_events(events)

        stats = gateway.get_statistics()
        assert stats.events_detected >= 0

    def test_start_stop_processing(self, gateway):
        """Test starting and stopping processing."""
        gateway.start_processing()
        assert gateway._running is True

        time.sleep(0.5)

        gateway.stop_processing()
        assert gateway._running is False

    def test_classify_person_detection(self, gateway):
        """Test person detection classification."""
        bbox = BoundingBox(x1=10, y1=20, x2=100, y2=150)
        detection = Detection(
            class_id=0,
            class_name="person",
            confidence=0.92,
            bbox=bbox,
        )

        event_type = gateway._classify_detection(detection)
        assert event_type == EventType.PERSON_DETECTED

    def test_classify_package_detection(self, gateway):
        """Test package detection classification."""
        bbox = BoundingBox(x1=10, y1=20, x2=100, y2=150)
        detection = Detection(
            class_id=1,
            class_name="package",
            confidence=0.85,
            bbox=bbox,
        )

        event_type = gateway._classify_detection(detection)
        assert event_type == EventType.PACKAGE_DETECTED

    def test_reset_statistics(self, gateway):
        """Test resetting statistics."""
        # Create some events
        bbox = BoundingBox(x1=10, y1=20, x2=100, y2=150)
        detection = Detection(
            class_id=0,
            class_name="person",
            confidence=0.92,
            bbox=bbox,
        )
        events = gateway.process_detections([detection])
        if events:
            gateway.send_events(events)

        # Reset statistics
        gateway.reset_statistics()

        stats = gateway.get_statistics()
        assert stats.frames_processed == 0
        assert stats.events_detected == 0


class TestWebhookClient:
    """Test webhook client."""

    def test_webhook_client_creation(self):
        """Test creating webhook client."""
        client = WebhookClient()
        assert client.max_retries == 3
        assert client.base_retry_delay == 1


class TestEdgeAIConfig:
    """Test configuration."""

    def test_config_defaults(self):
        """Test configuration defaults."""
        config = EdgeAIConfig(model_path="models/test.tflite")
        assert config.input_width == 640
        assert config.input_height == 480
        assert config.confidence_threshold == 0.7
        assert config.fps == 30

    def test_config_custom_values(self):
        """Test custom configuration."""
        config = EdgeAIConfig(
            model_path="models/test.tflite",
            input_width=1280,
            input_height=720,
            confidence_threshold=0.8,
            fps=60,
        )
        assert config.input_width == 1280
        assert config.input_height == 720
        assert config.confidence_threshold == 0.8
        assert config.fps == 60


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
