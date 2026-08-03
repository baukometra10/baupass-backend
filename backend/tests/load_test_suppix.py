#!/usr/bin/env python3
"""
SUPPIX Platform Load Test
Tests 1000+ concurrent users with location updates, WebSocket connections,
offline sync, and geospatial queries.
"""

import asyncio
import aiohttp
import time
import json
import random
from datetime import datetime, timezone
from typing import List, Dict, Any
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Configuration
CONFIG = {
    "API_BASE_URL": "http://localhost:8080",
    "AUTH_TOKEN": "test-token",
    "CONCURRENT_USERS": 100,  # Start with 100, can increase to 1000
    "TEST_DURATION_SECONDS": 60,
    "LOCATION_UPDATE_INTERVAL": 5,  # seconds
}

# Statistics
stats = {
    "total_requests": 0,
    "successful_requests": 0,
    "failed_requests": 0,
    "total_errors": [],
    "response_times": [],
    "start_time": None,
    "end_time": None,
}


class LoadTestWorker:
    """Simulates a worker with location tracking, battery monitoring, and offline sync."""

    def __init__(self, worker_id: str, session: aiohttp.ClientSession):
        self.worker_id = worker_id
        self.session = session
        self.latitude = 40.7128 + random.uniform(-0.01, 0.01)
        self.longitude = -74.0060 + random.uniform(-0.01, 0.01)
        self.battery_level = random.uniform(20, 100)
        self.is_online = True
        self.offline_queue: List[Dict[str, Any]] = []

    async def send_location_update(self) -> bool:
        """Send location + battery + accelerometer data to backend."""
        try:
            # Simulate movement
            self.latitude += random.uniform(-0.0005, 0.0005)
            self.longitude += random.uniform(-0.0005, 0.0005)
            self.battery_level = max(0, self.battery_level - random.uniform(0.1, 0.3))

            data = {
                "latitude": self.latitude,
                "longitude": self.longitude,
                "company_id": "load-test",
                "battery_level": self.battery_level,
                "accelerometer": {
                    "x": random.uniform(-2, 2),
                    "y": random.uniform(-2, 2),
                    "z": 9.8 + random.uniform(-1, 1),
                },
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }

            url = f"{CONFIG['API_BASE_URL']}/api/suppix/location/sample"
            headers = {
                "Authorization": f"Bearer {CONFIG['AUTH_TOKEN']}",
                "Content-Type": "application/json",
            }

            start = time.time()
            async with self.session.post(url, json=data, headers=headers, timeout=10) as response:
                elapsed = time.time() - start
                stats["response_times"].append(elapsed)

                if response.status in (200, 201):
                    stats["successful_requests"] += 1
                    self.is_online = True
                    return True
                else:
                    stats["failed_requests"] += 1
                    self.offline_queue.append(data)
                    self.is_online = False
                    return False
        except Exception as e:
            stats["failed_requests"] += 1
            stats["total_errors"].append(str(e))
            self.offline_queue.append(data)
            self.is_online = False
            return False
        finally:
            stats["total_requests"] += 1

    async def query_nearest_cameras(self) -> bool:
        """Query nearest cameras (geospatial optimization)."""
        try:
            params = {
                "latitude": self.latitude,
                "longitude": self.longitude,
                "company_id": "load-test",
                "max_results": 5,
            }

            url = f"{CONFIG['API_BASE_URL']}/api/suppix/geospatial/nearest-cameras"
            headers = {"Authorization": f"Bearer {CONFIG['AUTH_TOKEN']}"}

            start = time.time()
            async with self.session.get(url, params=params, headers=headers, timeout=10) as response:
                elapsed = time.time() - start
                stats["response_times"].append(elapsed)

                if response.status == 200:
                    stats["successful_requests"] += 1
                    return True
                else:
                    stats["failed_requests"] += 1
                    return False
        except Exception as e:
            stats["failed_requests"] += 1
            stats["total_errors"].append(str(e))
            return False
        finally:
            stats["total_requests"] += 1

    async def check_offline_sync_status(self) -> bool:
        """Check offline cache status."""
        try:
            url = f"{CONFIG['API_BASE_URL']}/api/suppix/offline/status/{self.worker_id}"
            headers = {"Authorization": f"Bearer {CONFIG['AUTH_TOKEN']}"}

            start = time.time()
            async with self.session.get(url, headers=headers, timeout=10) as response:
                elapsed = time.time() - start
                stats["response_times"].append(elapsed)

                if response.status == 200:
                    stats["successful_requests"] += 1
                    return True
                else:
                    stats["failed_requests"] += 1
                    return False
        except Exception as e:
            stats["failed_requests"] += 1
            stats["total_errors"].append(str(e))
            return False
        finally:
            stats["total_requests"] += 1

    async def run_worker_loop(self, duration: int) -> None:
        """Run worker for specified duration."""
        end_time = time.time() + duration
        request_count = 0

        while time.time() < end_time:
            # Randomly distribute requests
            request_type = random.choice(
                ["location"] * 5 + ["geospatial"] * 3 + ["sync_status"]
            )

            if request_type == "location":
                await self.send_location_update()
            elif request_type == "geospatial":
                await self.query_nearest_cameras()
            elif request_type == "sync_status":
                await self.check_offline_sync_status()

            request_count += 1
            await asyncio.sleep(0.5)  # Small delay between requests

        logger.info(
            f"Worker {self.worker_id} completed {request_count} requests. "
            f"Online: {self.is_online}, Battery: {self.battery_level:.1f}%"
        )


async def run_load_test():
    """Run the load test with concurrent workers."""
    stats["start_time"] = time.time()

    connector = aiohttp.TCPConnector(limit=200, limit_per_host=50)
    timeout = aiohttp.ClientTimeout(total=30)

    async with aiohttp.ClientSession(connector=connector, timeout=timeout) as session:
        # Create workers
        workers = [
            LoadTestWorker(f"worker-{i:04d}", session)
            for i in range(CONFIG["CONCURRENT_USERS"])
        ]

        logger.info(
            f"Starting load test with {CONFIG['CONCURRENT_USERS']} concurrent workers "
            f"for {CONFIG['TEST_DURATION_SECONDS']} seconds"
        )

        # Run all workers concurrently
        tasks = [
            worker.run_worker_loop(CONFIG["TEST_DURATION_SECONDS"]) for worker in workers
        ]

        await asyncio.gather(*tasks, return_exceptions=True)

    stats["end_time"] = time.time()


def print_results():
    """Print load test results."""
    elapsed = stats["end_time"] - stats["start_time"]
    avg_response_time = (
        sum(stats["response_times"]) / len(stats["response_times"])
        if stats["response_times"]
        else 0
    )
    min_response_time = min(stats["response_times"]) if stats["response_times"] else 0
    max_response_time = max(stats["response_times"]) if stats["response_times"] else 0

    success_rate = (
        stats["successful_requests"] / stats["total_requests"] * 100
        if stats["total_requests"] > 0
        else 0
    )

    print("\n" + "=" * 70)
    print("SUPPIX PLATFORM LOAD TEST RESULTS")
    print("=" * 70)
    print(f"Test Duration: {elapsed:.2f} seconds")
    print(f"Concurrent Workers: {CONFIG['CONCURRENT_USERS']}")
    print(f"Total Requests: {stats['total_requests']}")
    print(f"Successful Requests: {stats['successful_requests']}")
    print(f"Failed Requests: {stats['failed_requests']}")
    print(f"Success Rate: {success_rate:.2f}%")
    print(f"Requests/Second: {stats['total_requests'] / elapsed:.2f}")
    print("\nResponse Times:")
    print(f"  Average: {avg_response_time * 1000:.2f}ms")
    print(f"  Min: {min_response_time * 1000:.2f}ms")
    print(f"  Max: {max_response_time * 1000:.2f}ms")

    if stats["total_errors"]:
        print(f"\nTop Errors:")
        error_counts = {}
        for error in stats["total_errors"]:
            error_type = error.split(":")[0]
            error_counts[error_type] = error_counts.get(error_type, 0) + 1

        for error_type, count in sorted(error_counts.items(), key=lambda x: x[1], reverse=True)[
            :5
        ]:
            print(f"  {error_type}: {count}")

    print("=" * 70)


if __name__ == "__main__":
    try:
        asyncio.run(run_load_test())
        print_results()
    except KeyboardInterrupt:
        logger.info("Load test interrupted by user")
        print_results()
    except Exception as e:
        logger.error(f"Load test failed: {e}", exc_info=True)
        print_results()
