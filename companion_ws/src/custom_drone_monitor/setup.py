from setuptools import find_packages, setup

package_name = "custom_drone_monitor"

setup(
    name=package_name,
    version="0.1.0",
    packages=find_packages(exclude=["test"]),
    data_files=[
        ("share/ament_index/resource_index/packages", ["resource/" + package_name]),
        ("share/" + package_name, ["package.xml"]),
    ],
    install_requires=["setuptools"],
    zip_safe=True,
    maintainer="PX4 x700 example maintainer",
    maintainer_email="dev@example.com",
    description="Read-only ROS 2 telemetry monitor for a PX4 vehicle.",
    license="BSD-3-Clause",
    entry_points={
        "console_scripts": [
            "vehicle_monitor = custom_drone_monitor.vehicle_monitor:main",
        ],
    },
)
