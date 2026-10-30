# Cubie A7A NPU camera inference

This ROS 2 node subscribes to a camera image topic, prepares each frame, executes a compiled model on the Cubie A7A's Vivante VIP9000 NPU through Allwinner AWNN/VIPLite, and publishes each raw output tensor on `output_0`, `output_1`, etc. Inference time is published in milliseconds on `inference_latency_ms`. Output tensors are flat `std_msgs/Float32MultiArray` messages; this node does not apply model-specific post-processing.

## Model format and runtime

The A733 board does not run an arbitrary `.onnx` file directly through a generic ONNX Runtime provider. Convert the ONNX model to an NBG model offline using Radxa/Allwinner's ACUITY Toolkit, then load the generated `network_binary.nb` on the board using AWNN/VIPLite. This node currently expects one image input with UINT8 data; the NBG must target the A733 NPU and its input preprocessing, layout, and quantization must match the node parameters.

Follow Radxa's [ACUITY Toolkit setup](https://docs.radxa.com/en/cubie/a7a/app-dev/npu-dev/cubie-acuity-env), [model conversion guide](https://docs.radxa.com/en/cubie/a7a/app-dev/npu-dev/cubie-acuity-usage), and [A733 ResNet50 ONNX example](https://docs.radxa.com/en/cubie/a7a/app-dev/npu-dev/cubie-resnet50) to convert and validate ONNX models. The ACUITY toolkit runs on the model-preparation host; the generated A733 NBG and the AWNN/VIPLite runtime are used on the Cubie.

Radxa's A733 examples use the `ai-sdk` checkout and VIPLite v2.0. Install the matching board runtime and checkout the SDK on the Cubie A7A. The SDK's `examples/libawnn_viplite` source and `viplite-tina/lib/aarch64-none-linux-gnu/v2.0` libraries are used when building this package.

## Build on the Cubie A7A

Install ROS 2 Jazzy with `rclcpp`, `sensor_msgs`, `std_msgs`, and the A733 NPU driver/runtime. Clone the Allwinner SDK without adding it to this repository, then set its location:

```bash
git clone https://github.com/ZIFENG278/ai-sdk.git "$HOME/ai-sdk"
export AI_SDK_ROOT="$HOME/ai-sdk"
source /opt/ros/jazzy/setup.bash
cd /home/ws/companion_ws
colcon build --packages-select custom_drone_vision
source install/setup.bash
```

`AI_SDK_ROOT` must contain `examples/libawnn_viplite/awnn_lib.c` and
`viplite-tina/lib/aarch64-none-linux-gnu/v2.0/libVIPhal.so` and
`libNBGlinker.so`. Build and run this package on the A7A with its matching
ARM64 driver libraries; an x86 development host cannot execute the NPU node.

## Run

Provide the compiled NBG path, camera topic, model input shape/layout, and one
flat output element count for each NBG output. Set the number of counts and
each value from the compiled model's output metadata. For example, a
640 × 640 RGB model with NCHW input and three output tensors can be launched as:

```bash
ros2 run custom_drone_vision npu_camera_inference --ros-args \
  -p model_path:=/home/rock/models/network_binary.nb \
  -p camera_topic:=/camera/image_raw \
  -p input_width:=640 \
  -p input_height:=640 \
  -p input_channels:=3 \
  -p input_layout:=NCHW \
  -p color_order:=RGB \
  -p output_element_counts:="[8400,8400,8400]"
```

The output counts above are illustrative only; they must match the actual
compiled model. Subscribe to `output_0`, `output_1`, etc. and
`inference_latency_ms`. The node accepts `rgb8`, `bgr8`, and `mono8` images and resizes frames directly
to the configured input dimensions; it does not letterbox, normalize, or decode detection
outputs. Match these operations to the preprocessing encoded in the NBG
model and add model-specific post-processing in a separate consumer.

The inference callback is synchronous and the image subscription uses a
sensor-data QoS profile with a one-frame history, so old frames are dropped
instead of queued when inference cannot keep up. No CPU inference fallback is
provided: failure to load AWNN or the NBG model stops node startup.
