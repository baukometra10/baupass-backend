"""
SUPPIX Platform Monitoring Setup
=================================

Prometheus metrics und Grafana dashboard für alle 5 Komponenten.
"""

from prometheus_client import Counter, Histogram, Gauge, CollectorRegistry
import logging

logger = logging.getLogger(__name__)

# Create a registry for SUPPIX metrics
supplix_registry = CollectorRegistry()


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Point #1: Geospatial Optimization Metrics
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

geospatial_queries = Counter(
    "geospatial_queries_total",
    "Total geospatial queries",
    ["query_type", "company_id"],
    registry=supplix_registry
)

geospatial_cache_hits = Counter(
    "geospatial_cache_hits_total",
    "Geospatial cache hits",
    ["query_type"],
    registry=supplix_registry
)

geospatial_haversine_calculations = Counter(
    "geospatial_haversine_total",
    "Total Haversine distance calculations",
    ["query_type"],
    registry=supplix_registry
)

geospatial_query_duration = Histogram(
    "geospatial_query_duration_seconds",
    "Geospatial query duration",
    ["query_type"],
    buckets=(0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0),
    registry=supplix_registry
)

geospatial_cache_size = Gauge(
    "geospatial_cache_size_bytes",
    "Geospatial cache size in bytes",
    registry=supplix_registry
)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Point #2: WebSocket Real-time Metrics
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

websocket_connections = Gauge(
    "websocket_connections_active",
    "Active WebSocket connections",
    ["event_type"],
    registry=supplix_registry
)

websocket_events_sent = Counter(
    "websocket_events_sent_total",
    "WebSocket events sent",
    ["event_type", "recipient_type"],  # broadcast/user/role
    registry=supplix_registry
)

websocket_message_latency = Histogram(
    "websocket_message_latency_ms",
    "WebSocket message latency in milliseconds",
    ["event_type"],
    buckets=(5, 10, 20, 50, 100, 200, 500, 1000),
    registry=supplix_registry
)

websocket_connection_errors = Counter(
    "websocket_connection_errors_total",
    "WebSocket connection errors",
    ["error_type"],
    registry=supplix_registry
)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Point #3: Offline-First Smart Boxes Metrics
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

offline_cache_records = Gauge(
    "offline_cache_records_total",
    "Total offline cache records",
    ["device_id", "sync_status"],
    registry=supplix_registry
)

offline_sync_operations = Counter(
    "offline_sync_operations_total",
    "Offline sync operations",
    ["device_id", "status"],  # success/partial/error
    registry=supplix_registry
)

offline_sync_duration = Histogram(
    "offline_sync_duration_seconds",
    "Offline sync operation duration",
    ["device_id"],
    buckets=(0.1, 0.5, 1.0, 2.5, 5.0, 10.0),
    registry=supplix_registry
)

offline_conflict_resolutions = Counter(
    "offline_conflicts_resolved_total",
    "Offline conflicts resolved",
    ["device_id", "strategy"],  # local_wins/server_wins/merge/manual
    registry=supplix_registry
)

offline_data_loss = Counter(
    "offline_data_loss_total",
    "Offline data loss (should be zero)",
    ["device_id", "record_type"],
    registry=supplix_registry
)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Point #4: Battery Management Metrics
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

battery_level = Gauge(
    "battery_level_percent",
    "Current battery level",
    ["worker_id"],
    registry=supplix_registry
)

battery_drain_rate = Gauge(
    "battery_drain_rate_percent_per_hour",
    "Battery drain rate",
    ["worker_id", "motion_state"],
    registry=supplix_registry
)

motion_state_changes = Counter(
    "motion_state_changes_total",
    "Motion state transitions",
    ["motion_state"],  # STATIONARY/SLOW/NORMAL/FAST/VERY_FAST/HIGH_SPEED
    registry=supplix_registry
)

battery_emergency_mode = Gauge(
    "battery_emergency_mode_active",
    "Is battery in emergency mode (<20%)",
    ["worker_id"],
    registry=supplix_registry
)

gps_sampling_interval = Gauge(
    "gps_sampling_interval_seconds",
    "GPS sampling interval based on motion",
    ["worker_id", "motion_state"],
    registry=supplix_registry
)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Point #5: Edge AI Processing Metrics
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

edge_ai_frames_processed = Counter(
    "edge_ai_frames_processed_total",
    "Frames processed by edge AI",
    ["gate_id", "model_name"],
    registry=supplix_registry
)

edge_ai_inference_time = Histogram(
    "edge_ai_inference_time_ms",
    "Edge AI inference time",
    ["gate_id", "model_name"],
    buckets=(20, 50, 100, 200, 500, 1000),
    registry=supplix_registry
)

edge_ai_fps = Gauge(
    "edge_ai_fps",
    "Frames per second processed",
    ["gate_id"],
    registry=supplix_registry
)

edge_ai_detections = Counter(
    "edge_ai_detections_total",
    "AI detections",
    ["gate_id", "event_type", "confidence_range"],  # 0.7-0.8, 0.8-0.9, 0.9+
    registry=supplix_registry
)

edge_ai_webhook_deliveries = Counter(
    "edge_ai_webhook_deliveries_total",
    "Webhook deliveries",
    ["gate_id", "webhook_url", "status"],  # success/failed/retrying
    registry=supplix_registry
)

edge_ai_webhook_latency = Histogram(
    "edge_ai_webhook_latency_ms",
    "Webhook delivery latency",
    ["gate_id"],
    buckets=(10, 50, 100, 500, 1000, 5000),
    registry=supplix_registry
)

edge_ai_bandwidth_saved = Gauge(
    "edge_ai_bandwidth_saved_percent",
    "Bandwidth saved by local processing",
    ["gate_id"],
    registry=supplix_registry
)

edge_ai_gpu_utilization = Gauge(
    "edge_ai_gpu_utilization_percent",
    "GPU utilization on edge device",
    ["gate_id"],
    registry=supplix_registry
)

edge_ai_memory_usage = Gauge(
    "edge_ai_memory_usage_mb",
    "Memory usage on edge device",
    ["gate_id"],
    registry=supplix_registry
)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Overall Platform Metrics
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

platform_api_requests = Counter(
    "platform_api_requests_total",
    "Platform API requests",
    ["endpoint", "method", "status"],
    registry=supplix_registry
)

platform_api_latency = Histogram(
    "platform_api_latency_ms",
    "Platform API latency",
    ["endpoint"],
    buckets=(10, 25, 50, 100, 250, 500, 1000),
    registry=supplix_registry
)

platform_data_availability = Gauge(
    "platform_data_availability_percent",
    "Data availability (0% loss)",
    registry=supplix_registry
)

platform_worker_online_count = Gauge(
    "platform_workers_online",
    "Number of online workers",
    ["company_id"],
    registry=supplix_registry
)


def init_metrics(app):
    """Initialize Prometheus metrics endpoint."""
    from flask import Response
    from prometheus_client import generate_latest, CONTENT_TYPE_LATEST

    @app.route("/metrics", methods=["GET"])
    def metrics():
        """Expose Prometheus metrics."""
        return Response(
            generate_latest(supplix_registry),
            mimetype=CONTENT_TYPE_LATEST
        )

    logger.info("Prometheus metrics endpoint initialized at /metrics")
