# CPU Qwen mission proposals

`mission_generator` is a Python ROS 2 node that returns a structured proposal
through `/generate_mission`. The package vendors the model configuration and
one-shot llama.cpp helper logic from
[A733 NPU Driver](https://github.com/petayyyy/a733_npu_driver) and calls it
directly as a local Python module using **Qwen2.5-1.5B-Instruct Q4_K_M on CPU**.
The helper launches the existing `llama-cli` binary; it does not dynamically
load code from an external checkout. The ROS node adds mission-specific
instructions and validates the returned JSON. The service does not publish
PX4 messages or execute a proposal. A separate deterministic mission executive
must validate and obtain operator approval before any mission can be sent to
PX4. The vendored source and its MIT license are identified in
`third_party/licenses/A733-NPU-Driver-MIT.txt`.

The proposal JSON contains:

```json
{
  "status": "ready",
  "summary": "Search the operator-specified area and return.",
  "steps": [
    {"action": "takeoff", "details": "Take off as required by the approved plan."},
    {"action": "search_area", "details": "Search the area specified by the operator."},
    {"action": "return", "details": "Return to the launch point."}
  ],
  "clarification_questions": []
}
```

Allowed actions are `takeoff`, `navigate`, `search_area`, `capture_photo`,
`return`, and `land`. A proposal with `status: "needs_clarification"` has no
steps and includes one or more questions instead. The node rejects malformed
or inconsistent JSON. The schema deliberately omits executable coordinates
and numeric flight limits. Never treat its output as flight-ready.

## Prepare llama.cpp and the CPU model

The [A733 NPU Driver project](https://github.com/petayyyy/a733_npu_driver)
documents and benchmarks CPU inference on the A733.

```bash
git clone https://github.com/petayyyy/a733_npu_driver.git "$HOME/a733_npu_driver"
```

Follow the project's [CPU baseline setup](https://github.com/petayyyy/a733_npu_driver/blob/aae9287f6d0de4af2f3e253343c58a78e2f3d04f/docs/06-cpu-baseline.md)
and [CLI setup](https://github.com/petayyyy/a733_npu_driver/blob/aae9287f6d0de4af2f3e253343c58a78e2f3d04f/docs/09-cli-tools.md)
to build llama.cpp and download the Qwen2.5-1.5B-Instruct Q4_K_M GGUF at:

```text
~/a733_npu_driver/models/qwen2.5-1.5b-instruct-q4_k_m.gguf
```

The helper expects llama.cpp at `~/llama.cpp/build/bin/llama-cli`.

## Build

```bash
source /opt/ros/jazzy/setup.bash
cd /home/ws/companion_ws
colcon build --packages-select custom_drone_mission
source install/setup.bash
```

## Run

```bash
ros2 run custom_drone_mission mission_generator --ros-args \
  -p model_name:=qwen-1.5b \
  -p cpu_cores:=6-7 \
  -p max_new_tokens:=256
```

In another terminal:

```bash
ros2 service call /generate_mission custom_drone_mission/srv/GenerateMission \
  "{request: 'Search the operator-approved area for a red car, capture a photo, then return.'}"
```

The helper defaults to the two A76 cores (`6-7` on the tested Orange Pi Zero
3W); verify the A76 CPU IDs on the target and override `cpu_cores` if needed.
The published Qwen2.5-1.5B benchmark is about 8.5 tokens/s and 2 GB RSS on the
tested Orange Pi Zero 3W. Confirm the Cubie A7A has adequate available memory
and benchmark under the intended ROS 2 workload. Inference is CPU-only; it
does not use the NPU.
