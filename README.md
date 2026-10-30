# Developing a Custom PX4 Drone

This workspace contains a deliberately simple example named **x700**: a larger X-frame multicopter model for Gazebo, its PX4 SITL airframe configuration, and a read-only ROS 2 companion-computer monitor.
It is a development walkthrough, not a flight-ready aircraft definition. See commit history for details

## Project Plan: Prompt-Driven Drone with Onboard AI

### Goal

Develop a low-cost PX4 drone whose companion computer interprets an operator's natural-language request, plans a bounded mission, detects objects with its camera, and reports or acts on detections. Example prompt: "search an approved area for a red car, capture a photo, then return"

The language model must not control motors or bypass PX4. It proposes a structured mission; a deterministic mission executive validates it, and PX4 remains responsible for flight control, stabilization, and failsafes. Keep a human operator able to approve missions and take over through QGroundControl.

### Target Architecture

```text
Operator / QGroundControl
  ├─ Prompt, mission approval, telemetry, and manual takeover (MAVLink)
  └─ Ground station link
          │
          ▼
Companion computer: Radxa Cubie A7A (Linux, ROS 2)
  ├─ Prompt interpreter: local LLM → structured mission proposal
  ├─ Mission executive: validate limits, request approval, execute mission
  ├─ Vision node: camera → YOLOv8n detection → optional red-car check
  ├─ Photo/event storage
  └─ PX4 ROS 2 interface via uXRCE-DDS
          │ serial or Ethernet
          ▼
PX4 flight controller → ESCs and motors
  ├─ Estimation, navigation, and stabilization
  └─ Geofence, battery, link-loss, and other configured failsafes
```

### Planned Hardware and Software

- **Flight platform:** PX4-compatible multicopter and supported flight controller.
- **Companion computer:** Radxa Cubie A7A.
- **Middleware:** ROS 2 Jazzy in the companion workspace, `px4_msgs` matched to the PX4 firmware, and the PX4 uXRCE-DDS client with Micro XRCE-DDS Agent on the companion.
- **Object detection:** YOLOv8n and its COCO pretrained classes for common objects such as cars.
- **Language model:** Anything between 7 and 14 billion parapeters should be smart enought for the job. The A7A should be able to run it. Validate the claim.
- **Ground station:** QGroundControl

## What is connected

| Concern | Example file | Purpose |
|---|---|---|
| Vehicle geometry and simulated sensors/motors | `PX4-Autopilot/Tools/simulation/gz/models/x700/model.sdf` | Defines 0.45 m rotor spacing per body axis (0.636 m diagonal), a 3 kg body, rotor links and Gazebo motor/sensor systems. |
| PX4 vehicle configuration | `PX4-Autopilot/ROMFS/px4fmu_common/init.d-posix/airframes/22000_gz_x700` | Maps the four control-allocation rotors and Gazebo motor outputs; sets starting parameter defaults. |
| Firmware registration | `PX4-Autopilot/ROMFS/px4fmu_common/init.d-posix/airframes/CMakeLists.txt` | Includes the airframe in the PX4 ROMFS build. |
| Companion application | `companion_ws/src/custom_drone_monitor/` | ROS 2 Python node subscribes to vehicle status and local odometry. It does not send flight commands. |
| NPU vision inference | `companion_ws/src/custom_drone_vision/` | ROS 2 camera node runs A733-targeted NBG models through the Cubie A7A AWNN/VIPLite runtime; ONNX models must be converted to NBG before deployment. |

The model uses primitive shapes rather than copied X500 assets so its larger dimensions are obvious and editable. Rotor positions are ±0.225 m on each body axis, compared with ±0.174 m in X500 (about 1.29× the arm footprint). Its mass, inertia, propeller/motor constants, and hover-throttle value are illustrative starting estimates, not measured specifications. The IMU, magnetometer, and barometer have small Gaussian noise on purpose: PX4 treats a sensor that repeats identical values as stale and removes it from estimator use.

## Run the SITL example

This PX4 checkout needs its official release tags available for CMake to embed the real version in the firmware. If QGroundControl identifies the firmware as `0.0.0`, fetch the upstream tags (do not create a made-up version tag):

```sh
cd /home/ws/PX4-Autopilot
git fetch --tags https://github.com/PX4/PX4-Autopilot.git
git describe --tags --match 'v[0-9]*'
```

Reconfigure/rebuild after fetching tags so the version header and firmware are regenerated:

```sh
make px4_sitl_default
```

From the PX4 checkout, build and launch the vehicle:

```sh
cd /home/ws/PX4-Autopilot
ROS_DOMAIN_ID=42 make px4_sitl gz_x700
```

In another terminal, start the Micro XRCE-DDS agent:

```sh
ROS_DOMAIN_ID=42 MicroXRCEAgent udp4 -p 8888
```

The agent must be installed on the companion computer. This PX4 `main` firmware uses the DDS v2 client; with ROS 2 Jazzy, use Micro XRCE-DDS Agent v2.4.3. See PX4's [agent installation instructions](PX4-Autopilot/docs/en/middleware/uxrce_dds.md#micro-xrce-dds-agent-installation) to install that version before starting it.
PX4 SITL starts its DDS client for the default UDP setup. Keep the ROS 2 domain consistent with the workspace setting (`ROS_DOMAIN_ID=42` in this devcontainer).

## Build and run the companion app

The companion workspace needs `px4_msgs` definitions compatible with the PX4 firmware. For this PX4 `main` checkout, use the matching `px4_msgs` branch; use the corresponding release branch when building a PX4 release.

```sh
cd /home/ws/companion_ws/src
git clone --branch main https://github.com/PX4/px4_msgs.git
cd /home/ws/companion_ws
source /opt/ros/jazzy/setup.bash
colcon build --packages-up-to custom_drone_monitor
source install/setup.bash
ROS_DOMAIN_ID=42 ros2 run custom_drone_monitor vehicle_monitor
```

Build and source `px4_msgs` in the same ROS 2 environment used to run the app and `ros2 topic echo`; otherwise ROS 2 can discover a topic's type name but report that its message type is invalid. The app prints armed state, mode, and local position once per second. It intentionally only subscribes to `/fmu/out/vehicle_status` and `/fmu/out/vehicle_odometry`; no commands are published.
For a real companion computer, install the matching ROS 2 distribution and agent there, connect it to PX4 over a dedicated serial or Ethernet link, and keep the unauthenticated DDS network isolated.

### Run camera inference on the Cubie A7A NPU

The Cubie A7A uses an Allwinner A733 with a Vivante VIP9000 NPU. Build this
package on the board against its AWNN/VIPLite v2.0 runtime; see
[`custom_drone_vision/README.md`](companion_ws/src/custom_drone_vision/README.md)
for the ONNX-to-NBG conversion requirement, build setup, camera parameters,
and launch example. The node only executes NBG artifacts on the NPU and does
not silently fall back to CPU inference.

## Customize the vehicle

1. **Geometry:** Edit the `x700` SDF. Keep each `rotor_N` link, joint, and motor plugin number aligned with the corresponding PX4 control-allocation rotor and Gazebo ESC function. Update model mass, center of gravity, inertia tensor, collision shapes, propeller dimensions, and sensor pose/rates from the actual CAD and component specifications. Match motor plugin constants to measured thrust/torque curves where possible.
2. **Airframe firmware configuration:** Update rotor locations and signs in `22000_gz_x700`, output functions, limits, and parameter defaults. Reserve a unique airframe ID in the project's custom range; register its filename in the airframe `CMakeLists.txt`. `param set-default` supplies defaults, it does not overwrite a user's saved parameter value.
3. **Run and validate:** Rebuild with `make px4_sitl gz_x700`. Confirm all four outputs correspond to the intended rotor order and direction before arming. Check hover thrust, estimator health, motor saturation, and logs; retune `MPC_THR_HOVER` and the `MC_*` gains from controlled simulation tests. Do not copy SITL values to hardware without validation.
4. **Custom flight-controller code:** Keep vehicle-specific startup/default configuration in the airframe file. For new PX4-side logic, create an out-of-tree PX4 module (PX4 docs: [External Modules](PX4-Autopilot/docs/en/advanced/out_of_tree_modules.md)) and build SITL with `EXTERNAL_MODULES_LOCATION=<path>`; move stable reusable changes into a pinned PX4 fork or upstream contribution. The airframe shell file is configuration, not a substitute for flight-control code.
5. **Companion features:** Add ROS 2 nodes alongside `custom_drone_monitor`, using the matching `px4_msgs`. PX4's [uXRCE-DDS bridge documentation](PX4-Autopilot/docs/en/middleware/uxrce_dds.md) describes topic selection, agent setup, message matching, and security considerations. Add only the topics the app needs; treat offboard control as a separate safety-critical feature and test failsafe behavior in simulation first.

## From SITL to hardware

The example's geometry, motor dynamics, controller gains, sensor suite, output mapping, and companion transport do not define a real airframe. Before hardware use, create a board-specific build target and airframe configuration, select supported sensors/actuators, validate power and control directions without propellers, and complete PX4's configuration, tuning, and flight-safety checks. Removing `--no-nuttx` from the environment setup is only one build prerequisite; it does not make this SITL example compatible with a flight controller.
