"""Ultrasonic obstacle detection and simple avoidance behavior."""

from __future__ import annotations

import time
from statistics import median
from typing import Optional

from gpiozero import DistanceSensor

from rc import Movement


class UltrasonicAvoider:
    """Detects near obstacles and runs a basic avoid maneuver."""

    def __init__(
        self,
        movement: Movement,
        trigger_pin: int = 23,
        echo_pin: int = 24,
        obstacle_distance_m: float = 0.30,
        sample_count: int = 3,
        turn_seconds: float = 0.45,
        clear_forward_seconds: float = 0.30,
    ) -> None:
        self.movement = movement
        self.obstacle_distance_m = obstacle_distance_m
        self.sample_count = max(1, sample_count)
        self.turn_seconds = turn_seconds
        self.clear_forward_seconds = clear_forward_seconds
        self.turn_left_next = True

        try:
            self.sensor = DistanceSensor(
                echo=echo_pin,
                trigger=trigger_pin,
                max_distance=4.0,
            )
        except Exception as exc:
            raise RuntimeError(
                "Failed to initialize ultrasonic sensor. "
                f"Check trigger/echo wiring ({trigger_pin}/{echo_pin})."
            ) from exc

    def cleanup(self) -> None:
        try:
            self.sensor.close()
        except Exception:
            pass

    def read_distance_m(self) -> Optional[float]:
        samples = []
        for _ in range(self.sample_count):
            try:
                samples.append(float(self.sensor.distance))
            except Exception:
                continue
            time.sleep(0.02)

        if not samples:
            return None
        return median(samples)

    def obstacle_detected(self) -> tuple[bool, Optional[float]]:
        distance_m = self.read_distance_m()
        if distance_m is None:
            return False, None
        return distance_m <= self.obstacle_distance_m, distance_m

    def avoid_if_needed(self) -> tuple[bool, Optional[float], Optional[str]]:
        """Returns (avoided, distance_m, direction)."""
        blocked, distance_m = self.obstacle_detected()
        if not blocked:
            return False, distance_m, None

        self.movement.stop()
        self.movement.straight()
        time.sleep(0.1)

        if self.turn_left_next:
            self.movement.left()
            direction = "left"
        else:
            self.movement.right()
            direction = "right"
        self.turn_left_next = not self.turn_left_next

        self.movement.forward()
        time.sleep(self.turn_seconds)
        self.movement.stop()
        self.movement.straight()

        self.movement.forward()
        time.sleep(self.clear_forward_seconds)
        self.movement.stop()

        return True, distance_m, direction
