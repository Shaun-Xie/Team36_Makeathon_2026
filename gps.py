"""GPS waypoint navigation for Raspberry Pi RC car."""

from __future__ import annotations

import json
import math
import socket
import time
from dataclasses import dataclass
from typing import Optional, Sequence

from rc import Movement


@dataclass
class GPSFix:
    latitude: float
    longitude: float
    timestamp: Optional[str] = None


@dataclass
class NavigationState:
    done: bool
    message: str
    waypoint_index: int
    total_waypoints: int
    distance_m: Optional[float] = None


class GPSReader:
    """Reads fixes from local gpsd JSON stream (port 2947)."""

    def __init__(
        self,
        host: str = "127.0.0.1",
        port: int = 2947,
        connect_timeout: float = 3.0,
    ) -> None:
        self.host = host
        self.port = port
        self.connect_timeout = connect_timeout
        self.sock: Optional[socket.socket] = None
        self._buffer = ""

    def connect(self) -> None:
        if self.sock is not None:
            return

        try:
            self.sock = socket.create_connection(
                (self.host, self.port), timeout=self.connect_timeout
            )
        except OSError as exc:
            raise RuntimeError(
                f"Unable to connect to gpsd at {self.host}:{self.port}. "
                "Start gpsd first."
            ) from exc

        self.sock.settimeout(0.5)
        watch_cmd = '?WATCH={"enable":true,"json":true}\n'.encode("utf-8")
        self.sock.sendall(watch_cmd)

    def read_fix(self, timeout_seconds: float = 3.0) -> Optional[GPSFix]:
        """Return one valid TPV fix with lat/lon or None on timeout."""
        if self.sock is None:
            self.connect()

        assert self.sock is not None
        deadline = time.monotonic() + timeout_seconds

        while time.monotonic() < deadline:
            try:
                data = self.sock.recv(4096)
            except socket.timeout:
                continue
            except OSError as exc:
                raise RuntimeError(f"Failed while reading gpsd stream: {exc}") from exc

            if not data:
                raise RuntimeError("gpsd connection closed.")

            self._buffer += data.decode("utf-8", errors="ignore")
            while "\n" in self._buffer:
                line, self._buffer = self._buffer.split("\n", 1)
                line = line.strip()
                if not line:
                    continue

                try:
                    payload = json.loads(line)
                except json.JSONDecodeError:
                    continue

                if payload.get("class") != "TPV":
                    continue

                mode = int(payload.get("mode", 0))
                latitude = payload.get("lat")
                longitude = payload.get("lon")
                if (
                    mode >= 2
                    and isinstance(latitude, (int, float))
                    and isinstance(longitude, (int, float))
                ):
                    return GPSFix(
                        latitude=float(latitude),
                        longitude=float(longitude),
                        timestamp=payload.get("time"),
                    )

        return None

    def close(self) -> None:
        if self.sock is None:
            return

        try:
            self.sock.sendall(b'?WATCH={"enable":false}\n')
        except OSError:
            pass
        try:
            self.sock.close()
        finally:
            self.sock = None
            self._buffer = ""


def haversine_meters(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Distance in meters between two WGS84 points."""
    radius_m = 6371000.0
    lat1_rad = math.radians(lat1)
    lat2_rad = math.radians(lat2)
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)

    a = (
        math.sin(dlat / 2) ** 2
        + math.cos(lat1_rad) * math.cos(lat2_rad) * math.sin(dlon / 2) ** 2
    )
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return radius_m * c


def bearing_degrees(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Initial bearing in degrees [0..360)."""
    lat1_rad = math.radians(lat1)
    lat2_rad = math.radians(lat2)
    dlon_rad = math.radians(lon2 - lon1)

    x = math.sin(dlon_rad) * math.cos(lat2_rad)
    y = (
        math.cos(lat1_rad) * math.sin(lat2_rad)
        - math.sin(lat1_rad) * math.cos(lat2_rad) * math.cos(dlon_rad)
    )
    angle_deg = math.degrees(math.atan2(x, y))
    return (angle_deg + 360.0) % 360.0


def normalize_angle_deg(angle_deg: float) -> float:
    """Normalize angle to [-180, 180]."""
    normalized = (angle_deg + 180.0) % 360.0 - 180.0
    return normalized


class GPSNavigator:
    """Navigates through waypoints using GPS-only course correction."""

    def __init__(
        self,
        movement: Movement,
        waypoints: Sequence[tuple[float, float]],
        gps_reader: Optional[GPSReader] = None,
        arrival_radius_m: float = 2.5,
        heading_update_min_m: float = 0.5,
        steer_threshold_deg: float = 20.0,
        turn_pulse_seconds: float = 0.35,
        forward_pulse_seconds: float = 0.45,
    ) -> None:
        if not waypoints:
            raise RuntimeError("At least one waypoint is required.")

        self.movement = movement
        self.waypoints = list(waypoints)
        self.reader = gps_reader or GPSReader()
        self.arrival_radius_m = arrival_radius_m
        self.heading_update_min_m = heading_update_min_m
        self.steer_threshold_deg = steer_threshold_deg
        self.turn_pulse_seconds = turn_pulse_seconds
        self.forward_pulse_seconds = forward_pulse_seconds

        self.current_waypoint_index = 0
        self.last_fix: Optional[GPSFix] = None
        self.heading_deg: Optional[float] = None

    @property
    def total_waypoints(self) -> int:
        return len(self.waypoints)

    def start(self) -> None:
        self.reader.connect()

    def cleanup(self) -> None:
        self.reader.close()
        self.movement.stop()
        self.movement.straight()

    def _pulse_forward(self) -> None:
        self.movement.straight()
        self.movement.forward()
        time.sleep(self.forward_pulse_seconds)
        self.movement.stop()

    def _pulse_turn(self, turn_left: bool) -> None:
        if turn_left:
            self.movement.left()
        else:
            self.movement.right()
        self.movement.forward()
        time.sleep(self.turn_pulse_seconds)
        self.movement.stop()
        self.movement.straight()

    def _update_heading(self, current_fix: GPSFix) -> None:
        if self.last_fix is None:
            self.last_fix = current_fix
            return

        moved_m = haversine_meters(
            self.last_fix.latitude,
            self.last_fix.longitude,
            current_fix.latitude,
            current_fix.longitude,
        )
        if moved_m >= self.heading_update_min_m:
            self.heading_deg = bearing_degrees(
                self.last_fix.latitude,
                self.last_fix.longitude,
                current_fix.latitude,
                current_fix.longitude,
            )
            self.last_fix = current_fix

    def step(self, fix_timeout_seconds: float = 3.0) -> NavigationState:
        """Run one navigation step toward current waypoint."""
        if self.current_waypoint_index >= self.total_waypoints:
            self.movement.stop()
            return NavigationState(
                done=True,
                message="All waypoints reached.",
                waypoint_index=self.current_waypoint_index,
                total_waypoints=self.total_waypoints,
            )

        current_fix = self.reader.read_fix(timeout_seconds=fix_timeout_seconds)
        if current_fix is None:
            self.movement.stop()
            return NavigationState(
                done=False,
                message="Waiting for valid GPS fix...",
                waypoint_index=self.current_waypoint_index,
                total_waypoints=self.total_waypoints,
            )

        self._update_heading(current_fix)

        target_lat, target_lon = self.waypoints[self.current_waypoint_index]
        distance_m = haversine_meters(
            current_fix.latitude,
            current_fix.longitude,
            target_lat,
            target_lon,
        )

        if distance_m <= self.arrival_radius_m:
            self.movement.stop()
            self.movement.straight()
            self.current_waypoint_index += 1

            if self.current_waypoint_index >= self.total_waypoints:
                return NavigationState(
                    done=True,
                    message="Reached final waypoint.",
                    waypoint_index=self.current_waypoint_index,
                    total_waypoints=self.total_waypoints,
                    distance_m=distance_m,
                )

            return NavigationState(
                done=False,
                message=f"Reached waypoint {self.current_waypoint_index}. Moving to next.",
                waypoint_index=self.current_waypoint_index,
                total_waypoints=self.total_waypoints,
                distance_m=distance_m,
            )

        target_bearing_deg = bearing_degrees(
            current_fix.latitude,
            current_fix.longitude,
            target_lat,
            target_lon,
        )

        if self.heading_deg is None:
            self._pulse_forward()
            return NavigationState(
                done=False,
                message=(
                    f"Heading unknown. Forward pulse toward waypoint "
                    f"{self.current_waypoint_index + 1}/{self.total_waypoints}."
                ),
                waypoint_index=self.current_waypoint_index,
                total_waypoints=self.total_waypoints,
                distance_m=distance_m,
            )

        error_deg = normalize_angle_deg(target_bearing_deg - self.heading_deg)
        if error_deg > self.steer_threshold_deg:
            self._pulse_turn(turn_left=True)
            action = "left-turn pulse"
        elif error_deg < -self.steer_threshold_deg:
            self._pulse_turn(turn_left=False)
            action = "right-turn pulse"
        else:
            self._pulse_forward()
            action = "forward pulse"

        return NavigationState(
            done=False,
            message=(
                f"{action}; target bearing={target_bearing_deg:.1f} deg, "
                f"heading={self.heading_deg:.1f} deg, error={error_deg:.1f} deg."
            ),
            waypoint_index=self.current_waypoint_index,
            total_waypoints=self.total_waypoints,
            distance_m=distance_m,
        )
