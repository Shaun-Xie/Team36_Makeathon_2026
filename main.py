"""Main robot loop: waypoint navigation + ultrasonic avoidance."""

import os
import time

from gps import GPSNavigator
from rc import Movement
from ultrasonic import UltrasonicAvoider


# Fallback if WAYPOINTS env var is not set.
# Replace with your real route coordinates.
DEFAULT_WAYPOINTS = [
    (39.1735, -86.5340),
    (39.1736, -86.5339),
]

WAYPOINTS_ENV = "WAYPOINTS"  # format: "lat,lon;lat,lon;lat,lon"
ARRIVAL_RADIUS_METERS = 2.5
GPS_FIX_TIMEOUT_SECONDS = 2.0
NAV_LOOP_SLEEP_SECONDS = 0.15
STATUS_PRINT_INTERVAL_SECONDS = 1.0

OBSTACLE_AVOIDANCE_ENABLED = True
ULTRASONIC_TRIGGER_PIN = 23
ULTRASONIC_ECHO_PIN = 24
OBSTACLE_DISTANCE_METERS = 0.30


def parse_waypoints() -> list[tuple[float, float]]:
    raw = os.getenv(WAYPOINTS_ENV, "").strip()
    if not raw:
        return DEFAULT_WAYPOINTS

    parsed: list[tuple[float, float]] = []
    for pair in raw.split(";"):
        pair = pair.strip()
        if not pair:
            continue
        parts = pair.split(",")
        if len(parts) != 2:
            raise RuntimeError(
                f"Invalid waypoint '{pair}'. Expected format lat,lon."
            )
        try:
            latitude = float(parts[0].strip())
            longitude = float(parts[1].strip())
        except ValueError as exc:
            raise RuntimeError(
                f"Invalid waypoint '{pair}'. Latitude/longitude must be numeric."
            ) from exc
        parsed.append((latitude, longitude))

    if not parsed:
        raise RuntimeError("No valid waypoints parsed from WAYPOINTS env var.")
    return parsed


def main() -> int:
    movement = Movement()
    navigator = None
    avoider = None

    try:
        waypoints = parse_waypoints()
        navigator = GPSNavigator(
            movement=movement,
            waypoints=waypoints,
            arrival_radius_m=ARRIVAL_RADIUS_METERS,
        )
        navigator.start()

        print("Autonomous navigation started.")
        print(f"Waypoints: {len(waypoints)}")
        print(
            f"Waypoint source: {WAYPOINTS_ENV}"
            if os.getenv(WAYPOINTS_ENV)
            else "Waypoint source: DEFAULT_WAYPOINTS"
        )

        if OBSTACLE_AVOIDANCE_ENABLED:
            try:
                avoider = UltrasonicAvoider(
                    movement=movement,
                    trigger_pin=ULTRASONIC_TRIGGER_PIN,
                    echo_pin=ULTRASONIC_ECHO_PIN,
                    obstacle_distance_m=OBSTACLE_DISTANCE_METERS,
                )
                print("Ultrasonic avoidance enabled.")
            except RuntimeError as exc:
                print(f"[WARN] Ultrasonic disabled: {exc}")

        print("Press Ctrl+C to stop.\n")

        last_status_print = 0.0
        while True:
            if avoider is not None:
                avoided, distance_m, direction = avoider.avoid_if_needed()
                if avoided:
                    distance_text = (
                        f"{distance_m:.2f}m" if distance_m is not None else "unknown"
                    )
                    print(
                        f"[AVOID] Obstacle at {distance_text}; "
                        f"executed {direction} avoid maneuver."
                    )
                    time.sleep(NAV_LOOP_SLEEP_SECONDS)
                    continue

            nav_state = navigator.step(fix_timeout_seconds=GPS_FIX_TIMEOUT_SECONDS)

            now = time.monotonic()
            if now - last_status_print >= STATUS_PRINT_INTERVAL_SECONDS:
                display_waypoint_index = min(
                    nav_state.total_waypoints,
                    nav_state.waypoint_index + (0 if nav_state.done else 1),
                )
                if nav_state.distance_m is not None:
                    distance_text = f"{nav_state.distance_m:.2f}m"
                else:
                    distance_text = "n/a"
                print(
                    f"[NAV] waypoint {display_waypoint_index}/"
                    f"{nav_state.total_waypoints} | distance={distance_text} | "
                    f"{nav_state.message}"
                )
                last_status_print = now

            if nav_state.done:
                print("[DONE] Route complete.")
                return 0

            time.sleep(NAV_LOOP_SLEEP_SECONDS)

    except KeyboardInterrupt:
        print("\nInterrupted by user.")
        return 0
    except RuntimeError as exc:
        print(f"[ERROR] {exc}")
        return 1
    finally:
        if avoider is not None:
            avoider.cleanup()
        if navigator is not None:
            navigator.cleanup()
        movement.cleanup()


if __name__ == "__main__":
    raise SystemExit(main())
