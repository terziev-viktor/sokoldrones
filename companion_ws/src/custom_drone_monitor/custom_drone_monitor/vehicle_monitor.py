from math import isfinite
from time import monotonic

import rclpy
from px4_msgs.msg import VehicleOdometry, VehicleStatus
from rclpy.node import Node
from rclpy.qos import HistoryPolicy, QoSProfile, ReliabilityPolicy


class VehicleMonitor(Node):
    def __init__(self) -> None:
        super().__init__("custom_drone_monitor")
        qos = QoSProfile(
            reliability=ReliabilityPolicy.BEST_EFFORT,
            history=HistoryPolicy.KEEP_LAST,
            depth=1,
        )
        self._status: VehicleStatus | None = None
        self._odometry: VehicleOdometry | None = None
        self._last_status = 0.0
        self._last_odometry = 0.0

        self.create_subscription(VehicleStatus, "/fmu/out/vehicle_status", self._on_status, qos)
        self.create_subscription(
            VehicleOdometry, "/fmu/out/vehicle_odometry", self._on_odometry, qos
        )
        self.create_timer(1.0, self._report)

    def _on_status(self, message: VehicleStatus) -> None:
        self._status = message
        self._last_status = monotonic()

    def _on_odometry(self, message: VehicleOdometry) -> None:
        self._odometry = message
        self._last_odometry = monotonic()

    def _report(self) -> None:
        now = monotonic()
        status_text = "waiting"
        if self._status is not None:
            status = self._status
            age = now - self._last_status
            armed = status.arming_state == VehicleStatus.ARMING_STATE_ARMED
            mode = {
                VehicleStatus.NAVIGATION_STATE_MANUAL: "manual",
                VehicleStatus.NAVIGATION_STATE_POSCTL: "position",
                VehicleStatus.NAVIGATION_STATE_OFFBOARD: "offboard",
            }.get(status.nav_state, f"nav_state={status.nav_state}")
            status_text = f"{'armed' if armed else 'disarmed'} {mode}"
            if age > 3.0:
                status_text += " (stale)"

        position_text = "waiting"
        if self._odometry is not None:
            age = now - self._last_odometry
            position = self._odometry.position
            if all(isfinite(value) for value in position):
                position_text = "NED [%.2f, %.2f, %.2f] m" % tuple(position)
            else:
                position_text = "invalid"
            if age > 3.0:
                position_text += " (stale)"

        self.get_logger().info(f"vehicle: {status_text}; position: {position_text}")


def main(args: list[str] | None = None) -> None:
    rclpy.init(args=args)
    node = VehicleMonitor()
    try:
        rclpy.spin(node)
    finally:
        node.destroy_node()
        rclpy.shutdown()
