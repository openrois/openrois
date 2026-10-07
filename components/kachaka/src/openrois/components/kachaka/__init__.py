"""OpenRoIS components for the Preferred Robotics Kachaka.

Navigation and SystemInformation, each over the Kachaka gRPC API or over ROS 2. Both
classes of a type declare the same profile constant, so a client sees the same component
whichever backend the adapter imports.
"""

from openrois.components.kachaka.navigation_grpc import GrpcNavigation
from openrois.components.kachaka.navigation_ros2 import Ros2Navigation
from openrois.components.kachaka.system_information_grpc import GrpcSystemInformation
from openrois.components.kachaka.system_information_ros2 import Ros2SystemInformation

__all__ = [
    "GrpcNavigation",
    "GrpcSystemInformation",
    "Ros2Navigation",
    "Ros2SystemInformation",
]
