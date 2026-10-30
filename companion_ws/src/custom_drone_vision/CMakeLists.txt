cmake_minimum_required(VERSION 3.8)
project(custom_drone_vision)

if(NOT CMAKE_CXX_STANDARD)
  set(CMAKE_CXX_STANDARD 17)
endif()

find_package(ament_cmake REQUIRED)
find_package(rclcpp REQUIRED)
find_package(sensor_msgs REQUIRED)
find_package(std_msgs REQUIRED)
find_package(Threads REQUIRED)

set(AI_SDK_ROOT "$ENV{AI_SDK_ROOT}" CACHE PATH "Path to the Allwinner ai-sdk checkout")
set(NPU_SW_VERSION "v2.0" CACHE STRING "A733 VIPLite driver version")

if(NOT AI_SDK_ROOT)
  message(FATAL_ERROR
    "Set AI_SDK_ROOT to the Allwinner ai-sdk checkout. "
    "See companion_ws/src/custom_drone_vision/README.md.")
endif()
if(NOT NPU_SW_VERSION STREQUAL "v2.0")
  message(FATAL_ERROR "The Cubie A7A uses the A733 VIPLite v2.0 runtime.")
endif()

set(AWNN_DIR "${AI_SDK_ROOT}/examples/libawnn_viplite")
set(VIP_DIR "${AI_SDK_ROOT}/viplite-tina/lib/aarch64-none-linux-gnu/${NPU_SW_VERSION}")
foreach(required_file
    "${AWNN_DIR}/awnn_lib.c"
    "${AWNN_DIR}/awnn_quantize.c"
    "${AWNN_DIR}/awnn_lib.h"
    "${AI_SDK_ROOT}/log/log.h"
    "${VIP_DIR}/inc/vip_lite.h"
    "${VIP_DIR}/libNBGlinker.so"
    "${VIP_DIR}/libVIPhal.so")
  if(NOT EXISTS "${required_file}")
    message(FATAL_ERROR "Required A733 NPU SDK file not found: ${required_file}")
  endif()
endforeach()

add_executable(npu_camera_inference
  src/npu_camera_inference.cpp
  "${AWNN_DIR}/awnn_lib.c"
  "${AWNN_DIR}/awnn_quantize.c")
target_include_directories(npu_camera_inference PRIVATE
  "${AI_SDK_ROOT}"
  "${AWNN_DIR}"
  "${VIP_DIR}/inc")
target_link_libraries(npu_camera_inference
  Threads::Threads
  "${VIP_DIR}/libNBGlinker.so"
  "${VIP_DIR}/libVIPhal.so")
target_link_options(npu_camera_inference PRIVATE "-Wl,-rpath,${VIP_DIR}")
ament_target_dependencies(npu_camera_inference
  rclcpp
  sensor_msgs
  std_msgs)

install(TARGETS npu_camera_inference
  DESTINATION lib/${PROJECT_NAME})

ament_package()
