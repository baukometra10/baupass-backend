"""Tests for Fused Location Provider: Motion-aware GPS sampling with battery optimization."""

import time
import math
from datetime import datetime, timezone
import pytest

from backend.app.platform.physical_operations.fused_location_provider import (
    FusedLocationProvider,
    MotionDetector,
    MotionState,
    LocationSample,
    AccelerometerReading,
    BatteryStats,
    SamplingConfig,
)


@pytest.fixture
def config():
    """Create sampling configuration."""
    return SamplingConfig(
        stationary_interval_seconds=5.0,
        light_motion_interval_seconds=2.0,
        moderate_motion_interval_seconds=1.0,
    )


@pytest.fixture
def provider(config):
    """Create fused location provider."""
    return FusedLocationProvider(config=config)


class TestMotionDetector:
    """Test motion detection from accelerometer."""

    def test_detect_stationary(self, config):
        """Test detecting stationary state."""
        detector = MotionDetector(config)

        # Add low-acceleration readings
        for i in range(5):
            reading = AccelerometerReading(x=0.1, y=0.1, z=9.8)
            detector.add_reading(reading)
            time.sleep(0.01)

        state = detector.detect_motion_state()
        assert state == MotionState.STATIONARY

    def test_detect_light_motion(self, config):
        """Test detecting light motion (walking)."""
        detector = MotionDetector(config)

        # Add moderate acceleration readings
        for i in range(5):
            reading = AccelerometerReading(x=2.0, y=0.5, z=9.8)
            detector.add_reading(reading)
            time.sleep(0.01)

        state = detector.detect_motion_state()
        assert state in (MotionState.LIGHT_MOTION, MotionState.MODERATE_MOTION)

    def test_detect_fast_motion(self, config):
        """Test detecting fast motion."""
        detector = MotionDetector(config)

        # Add high acceleration readings
        for i in range(5):
            reading = AccelerometerReading(x=5.0, y=3.0, z=9.8)
            detector.add_reading(reading)
            time.sleep(0.01)

        state = detector.detect_motion_state()
        assert state in (MotionState.FAST_MOTION, MotionState.HIGH_SPEED)

    def test_acceleration_magnitude(self):
        """Test acceleration magnitude calculation."""
        reading = AccelerometerReading(x=3.0, y=4.0, z=0.0)
        # 3² + 4² = 9 + 16 = 25, sqrt(25) = 5
        assert reading.magnitude == 5.0


class TestLocationSample:
    """Test location sample operations."""

    def test_location_distance_calculation(self):
        """Test distance calculation between locations."""
        # San Francisco
        loc1 = LocationSample(latitude=37.7749, longitude=-122.4194, accuracy_m=5)
        # San Jose (approx 50km away)
        loc2 = LocationSample(latitude=37.3382, longitude=-121.8863, accuracy_m=5)

        distance = loc1.distance_to(loc2)
        # Should be roughly 50-55km
        assert 48000 < distance < 56000

    def test_location_same_point(self):
        """Test distance to same point is zero."""
        loc1 = LocationSample(latitude=37.7749, longitude=-122.4194, accuracy_m=5)
        loc2 = LocationSample(latitude=37.7749, longitude=-122.4194, accuracy_m=5)

        distance = loc1.distance_to(loc2)
        assert distance < 10  # Should be very small


class TestFusedLocationProvider:
    """Test fused location provider."""

    def test_should_sample_stationary(self, provider):
        """Test sampling interval when stationary."""
        provider.current_motion_state = MotionState.STATIONARY
        provider.last_sample_time = time.time() - 10  # 10 seconds ago

        loc = LocationSample(latitude=37.7749, longitude=-122.4194, accuracy_m=5)

        # Should sample (10 sec > 5 sec stationary interval)
        assert provider.should_sample_now(loc) is True

    def test_should_not_sample_too_soon(self, provider):
        """Test not sampling if too soon."""
        provider.current_motion_state = MotionState.LIGHT_MOTION
        provider.last_sample_time = time.time()  # Just now

        loc = LocationSample(latitude=37.7749, longitude=-122.4194, accuracy_m=5)

        # Should not sample (0 seconds < 2 sec interval)
        assert provider.should_sample_now(loc) is False

    def test_should_not_sample_poor_accuracy(self, provider):
        """Test not sampling with poor accuracy."""
        provider.current_motion_state = MotionState.STATIONARY
        provider.last_sample_time = time.time() - 10

        loc = LocationSample(latitude=37.7749, longitude=-122.4194, accuracy_m=150)

        # Should not sample (poor accuracy)
        assert provider.should_sample_now(loc) is False

    def test_sampling_interval_by_motion_state(self, provider, config):
        """Test sampling intervals match motion states."""
        intervals = {
            MotionState.STATIONARY: config.stationary_interval_seconds,
            MotionState.LIGHT_MOTION: config.light_motion_interval_seconds,
            MotionState.MODERATE_MOTION: config.moderate_motion_interval_seconds,
        }

        for state, expected_interval in intervals.items():
            provider.current_motion_state = state
            assert provider._get_sampling_interval() == expected_interval

    def test_battery_emergency_mode(self, provider, config):
        """Test emergency ultra-low mode when battery critical."""
        config.enable_battery_mode = True
        config.battery_threshold_percent = 20

        provider.battery_stats.current_level = 15  # Below threshold
        provider.current_motion_state = MotionState.LIGHT_MOTION

        interval = provider._get_sampling_interval()
        assert interval == config.ultra_low_interval_seconds

    def test_process_location_callback(self, provider):
        """Test location callback is invoked."""
        callback_invoked = []

        def mock_callback(location):
            callback_invoked.append(location)

        provider.location_callback = mock_callback
        provider.current_motion_state = MotionState.STATIONARY
        provider.last_sample_time = time.time() - 10

        loc = LocationSample(latitude=37.7749, longitude=-122.4194, accuracy_m=5)
        result = provider.process_location(loc)

        assert result is True
        assert len(callback_invoked) == 1
        assert callback_invoked[0] == loc

    def test_sampling_efficiency(self, provider, config):
        """Test sampling efficiency calculation."""
        # Stationary: 5 second interval vs 2 second baseline
        # 2 / 5 = 0.4 (40% of samples)
        provider.current_motion_state = MotionState.STATIONARY
        efficiency = provider.get_sampling_efficiency()
        assert 0.35 < efficiency < 0.45

    def test_battery_savings_calculation(self, provider):
        """Test battery savings calculation."""
        provider.current_motion_state = MotionState.STATIONARY
        stats = provider.get_stats()

        savings = stats["battery_savings_percent"]
        # Stationary should have high savings (>60%)
        assert savings > 50

    def test_battery_impact_estimate(self, provider):
        """Test battery impact estimation."""
        provider.battery_stats.current_level = 100
        provider.battery_stats.gps_drain_percent_per_hour = 1.0
        provider.current_motion_state = MotionState.LIGHT_MOTION

        impact = provider.estimate_battery_impact(hours=1)

        assert impact["hours"] == 1
        assert impact["total_drain_percent"] > 0
        assert impact["battery_level_after"] < 100

    def test_minimum_distance_filter(self, provider):
        """Test minimum distance filter."""
        provider.current_motion_state = MotionState.LIGHT_MOTION
        provider.last_sample_time = time.time() - 100  # Long time ago
        provider.config.min_distance_meters = 100

        # Create two locations very close together
        loc1 = LocationSample(latitude=37.7749, longitude=-122.4194, accuracy_m=5)
        provider.process_location(loc1)

        # Very nearby location (< 10m away, config requires 100m)
        loc2 = LocationSample(latitude=37.77495, longitude=-122.41945, accuracy_m=5)
        provider.last_sample_time = time.time() - 100

        should_sample = provider.should_sample_now(loc2)
        # Should require more distance moved
        assert should_sample is False

    def test_motion_state_assignment(self, provider):
        """Test motion state is assigned to locations."""
        callback_data = []

        def capture(loc):
            callback_data.append(loc)

        provider.location_callback = capture
        provider.current_motion_state = MotionState.MODERATE_MOTION
        provider.last_sample_time = time.time() - 10

        loc = LocationSample(latitude=37.7749, longitude=-122.4194, accuracy_m=5)
        provider.process_location(loc)

        assert len(callback_data) == 1
        assert callback_data[0].motion_state == MotionState.MODERATE_MOTION

    def test_get_stats(self, provider):
        """Test statistics collection."""
        provider.current_motion_state = MotionState.LIGHT_MOTION
        provider.battery_stats.current_level = 75
        provider.battery_stats.estimated_remaining_hours = 12

        stats = provider.get_stats()

        assert stats["motion_state"] == "light_motion"
        assert stats["battery_level"] == 75
        assert stats["estimated_remaining_hours"] == 12
        assert "sampling_efficiency" in stats
        assert "battery_savings_percent" in stats


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
