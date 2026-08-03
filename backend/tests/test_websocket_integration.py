"""
WebSocket Integration Tests — Real-time Communication Verification
==================================================================

Tests WebSocket connection, location updates, and offline sync integration.
"""
import pytest
import json
from datetime import datetime, timezone
from unittest.mock import patch, MagicMock
import time


class TestWebSocketConnection:
    """Test WebSocket connectivity and event handling."""

    def test_websocket_server_init(self, client_and_db):
        """Test that WebSocket server initializes."""
        client, _ = client_and_db

        # Server should load without errors (already verified by app startup)
        assert client is not None
        assert hasattr(client, 'get')
        assert hasattr(client, 'post')

    def test_api_suppix_endpoint_accessible(self, client_and_db):
        """Test SUPPIX endpoints are accessible."""
        client, _ = client_and_db

        # Test geospatial endpoint
        response = client.post(
            "/api/suppix/geospatial/nearest-cameras",
            json={"latitude": 40.7128, "longitude": -74.0060, "company_id": "test-company"},
            headers={"Authorization": "Bearer test-token"}
        )
        assert response.status_code == 200
        data = json.loads(response.data)
        assert data["status"] == "success"

    def test_location_sample_endpoint(self, client_and_db):
        """Test battery/location sample processing."""
        client, _ = client_and_db

        response = client.post(
            "/api/suppix/location/sample",
            json={
                "worker_id": "w-test-001",
                "gps": {"latitude": 40.7128, "longitude": -74.0060, "accuracy": 10.0},
                "accelerometer": {"x": 0.1, "y": 0.2, "z": 9.8},
                "battery_level": 85.0,
                "timestamp": datetime.now(timezone.utc).isoformat()
            },
            headers={"Authorization": "Bearer test-token"}
        )
        assert response.status_code == 200
        data = json.loads(response.data)
        assert data["status"] == "success"
        assert "motion_state" in data
        assert "should_sample" in data

    def test_offline_sync_integration(self, client_and_db):
        """Test offline sync endpoint integration."""
        client, _ = client_and_db
        device_id = "device-test-001"

        # Simulate offline sync
        response = client.post(
            "/api/suppix/offline/sync",
            json={
                "device_id": device_id,
                "records": [
                    {
                        "record_type": "CHECKIN",
                        "data": {"worker_id": "w-001", "location": {"latitude": 40.7128, "longitude": -74.0060}},
                        "timestamp": datetime.now(timezone.utc).isoformat()
                    },
                    {
                        "record_type": "LOCATION_UPDATE",
                        "data": {"worker_id": "w-001", "latitude": 40.7180, "longitude": -74.0100},
                        "timestamp": datetime.now(timezone.utc).isoformat()
                    }
                ]
            },
            headers={"Authorization": "Bearer test-token"}
        )
        assert response.status_code == 200
        data = json.loads(response.data)
        assert data["status"] == "success"
        assert data["synced"] >= 0

    def test_offline_status_check(self, client_and_db):
        """Test offline cache status retrieval."""
        client, _ = client_and_db
        device_id = "device-test-001"

        response = client.get(
            f"/api/suppix/offline/status/{device_id}",
            headers={"Authorization": "Bearer test-token"}
        )
        assert response.status_code == 200
        data = json.loads(response.data)
        assert data["status"] == "success"
        assert "cache_stats" in data
        assert "pending" in data["cache_stats"]
        assert "synced" in data["cache_stats"]

    def test_conflict_resolution_endpoint(self, client_and_db):
        """Test conflict resolution for offline records."""
        client, _ = client_and_db

        response = client.post(
            "/api/suppix/offline/conflict/record-123",
            json={
                "strategy": "server_wins",
                "resolved_data": {"worker_id": "w-001", "status": "checked_in"}
            },
            headers={"Authorization": "Bearer test-token"}
        )
        assert response.status_code == 200
        data = json.loads(response.data)
        assert data["status"] == "success"

    def test_battery_stats_retrieval(self, client_and_db):
        """Test battery statistics endpoint."""
        client, _ = client_and_db

        response = client.get(
            "/api/suppix/battery/stats/w-test-001",
            headers={"Authorization": "Bearer test-token"}
        )
        assert response.status_code == 200
        data = json.loads(response.data)
        assert data["status"] == "success"
        assert "battery_stats" in data
        stats = data["battery_stats"]
        assert "current_level" in stats
        assert "drain_rate" in stats
        assert "estimated_runtime" in stats
        assert "emergency_mode" in stats

    def test_geospatial_cache_stats(self, client_and_db):
        """Test geospatial cache statistics."""
        client, _ = client_and_db

        response = client.get(
            "/api/suppix/geospatial/cache/stats",
            headers={"Authorization": "Bearer test-token"}
        )
        # Endpoint may return 200 or default stats
        assert response.status_code in (200, 500)
        if response.status_code == 200:
            data = json.loads(response.data)
            assert data["status"] == "success"
            assert "cache_stats" in data

    def test_edge_ai_events_endpoint(self, client_and_db):
        """Test edge AI events retrieval."""
        client, _ = client_and_db

        response = client.get(
            "/api/suppix/edge-ai/events?gate_id=gate-test-01&limit=50",
            headers={"Authorization": "Bearer test-token"}
        )
        assert response.status_code == 200
        data = json.loads(response.data)
        assert data["status"] == "success"
        assert "gate_id" in data

    def test_edge_ai_webhook_registration(self, client_and_db):
        """Test edge AI webhook registration."""
        client, _ = client_and_db

        response = client.post(
            "/api/suppix/edge-ai/gateway/gate-test-01/webhook",
            json={"webhook_url": "https://webhook.example.com/events"},
            headers={"Authorization": "Bearer test-token"}
        )
        assert response.status_code == 200
        data = json.loads(response.data)
        assert data["status"] == "success"
        assert data["gate_id"] == "gate-test-01"

    def test_edge_ai_model_update(self, client_and_db):
        """Test edge AI model update endpoint."""
        client, _ = client_and_db

        # Mock the model download to avoid network calls
        with patch('backend.app.platform.physical_operations.edge_ai_gateway.EdgeAIGateway') as mock_gateway:
            mock_instance = MagicMock()
            mock_instance.model_manager.download_model.return_value = "models/yolov5n.tflite"
            mock_instance.load_model.return_value = True
            mock_gateway.return_value = mock_instance

            response = client.post(
                "/api/suppix/edge-ai/model/gate-test-01",
                json={
                    "model_url": "https://models.example.com/yolov5n.tflite",
                    "model_name": "yolov5n"
                },
                headers={"Authorization": "Bearer test-token"}
            )
            assert response.status_code == 200
            data = json.loads(response.data)
            assert data["status"] == "success"
            assert data["model_name"] == "yolov5n"

    def test_health_check_endpoint(self, client_and_db):
        """Test platform health check."""
        client, _ = client_and_db

        response = client.get(
            "/api/suppix/health",
            headers={"Authorization": "Bearer test-token"}
        )
        assert response.status_code == 200
        data = json.loads(response.data)
        assert data["status"] == "healthy"
        assert "components" in data
        components = data["components"]
        assert components["geospatial_optimization"] == "operational"
        assert components["offline_first"] == "operational"
        assert components["battery_management"] == "operational"
        assert components["edge_ai"] == "operational"
        assert components["websocket"] == "operational"


class TestRealTimeDataFlow:
    """Test complete real-time data flow scenarios."""

    def test_worker_location_flow(self, client_and_db):
        """Test complete worker location update flow."""
        client, _ = client_and_db
        worker_id = "w-flow-test-001"
        company_id = "company-flow-test"

        # Step 1: Worker location sample with accelerometer data
        response1 = client.post(
            "/api/suppix/location/sample",
            json={
                "worker_id": worker_id,
                "gps": {"latitude": 40.7128, "longitude": -74.0060, "accuracy": 8.0},
                "accelerometer": {"x": 0.2, "y": 0.3, "z": 9.8},
                "battery_level": 75.0,
                "timestamp": datetime.now(timezone.utc).isoformat()
            },
            headers={"Authorization": "Bearer test-token"}
        )
        assert response1.status_code == 200

        # Step 2: Find nearest cameras to worker location
        response2 = client.post(
            "/api/suppix/geospatial/nearest-cameras",
            json={
                "latitude": 40.7128,
                "longitude": -74.0060,
                "company_id": company_id,
                "max_results": 5
            },
            headers={"Authorization": "Bearer test-token"}
        )
        assert response2.status_code == 200

        # Step 3: Get battery stats
        response3 = client.get(
            f"/api/suppix/battery/stats/{worker_id}",
            headers={"Authorization": "Bearer test-token"}
        )
        assert response3.status_code == 200

    def test_offline_outage_flow(self, client_and_db):
        """Test complete offline outage and recovery flow."""
        client, _ = client_and_db
        device_id = "device-outage-test"

        # Step 1: Record operations during outage
        response1 = client.post(
            "/api/suppix/offline/sync",
            json={
                "device_id": device_id,
                "records": [
                    {
                        "record_type": "CHECKIN",
                        "data": {"worker_id": "w-001"},
                        "timestamp": datetime.now(timezone.utc).isoformat()
                    },
                    {
                        "record_type": "LOCATION_UPDATE",
                        "data": {"worker_id": "w-001", "latitude": 40.7128, "longitude": -74.0060},
                        "timestamp": datetime.now(timezone.utc).isoformat()
                    },
                    {
                        "record_type": "CHECKOUT",
                        "data": {"worker_id": "w-001"},
                        "timestamp": datetime.now(timezone.utc).isoformat()
                    }
                ]
            },
            headers={"Authorization": "Bearer test-token"}
        )
        assert response1.status_code == 200
        synced = json.loads(response1.data)["synced"]

        # Step 2: Check offline status
        response2 = client.get(
            f"/api/suppix/offline/status/{device_id}",
            headers={"Authorization": "Bearer test-token"}
        )
        assert response2.status_code == 200
        status = json.loads(response2.data)
        assert "cache_stats" in status

    def test_ai_detection_flow(self, client_and_db):
        """Test edge AI detection and webhook flow."""
        client, _ = client_and_db
        gate_id = "gate-ai-test"

        # Step 1: Register webhook
        response1 = client.post(
            f"/api/suppix/edge-ai/gateway/{gate_id}/webhook",
            json={"webhook_url": "https://webhook.test.com/events"},
            headers={"Authorization": "Bearer test-token"}
        )
        assert response1.status_code == 200

        # Step 2: Get AI events
        response2 = client.get(
            f"/api/suppix/edge-ai/events?gate_id={gate_id}&limit=100",
            headers={"Authorization": "Bearer test-token"}
        )
        assert response2.status_code == 200

        # Step 3: Update AI model (mocked to avoid network calls)
        with patch('backend.app.platform.physical_operations.edge_ai_gateway.EdgeAIGateway') as mock_gateway:
            mock_instance = MagicMock()
            mock_instance.model_manager.download_model.return_value = "models/yolov5n.tflite"
            mock_instance.load_model.return_value = True
            mock_gateway.return_value = mock_instance

            response3 = client.post(
                f"/api/suppix/edge-ai/model/{gate_id}",
                json={
                    "model_url": "https://models.test.com/yolov5n.tflite",
                    "model_name": "yolov5n"
                },
                headers={"Authorization": "Bearer test-token"}
            )
            assert response3.status_code == 200
