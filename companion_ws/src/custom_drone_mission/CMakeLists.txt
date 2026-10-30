cmake_minimum_required(VERSION 3.13)
project(custom_drone_mission)

find_package(ament_cmake REQUIRED)
find_package(rosidl_default_generators REQUIRED)

rosidl_generate_interfaces(${PROJECT_NAME} "srv/GenerateMission.srv")

install(PROGRAMS src/mission_generator.py
  DESTINATION lib/${PROJECT_NAME}
  RENAME mission_generator)

install(FILES src/qwen_chat_helper.py
  DESTINATION lib/${PROJECT_NAME})

install(DIRECTORY third_party/licenses/
  DESTINATION share/${PROJECT_NAME}/licenses)

ament_export_dependencies(rosidl_default_runtime)
ament_package()
