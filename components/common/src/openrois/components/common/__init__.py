"""Platform-independent OpenRoIS components with simulated data.

They stand in for a robot while an adapter is brought up, serve as test fixtures, and
show how a platform-specific component is written.
"""

from openrois.components.common.system_information import MockSystemInformation

__all__ = ["MockSystemInformation"]
