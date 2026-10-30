#!/usr/bin/env python3

import contextlib
import io
import json
import sys
import time

import qwen_chat_helper
from rclpy.node import Node

import rclpy
from custom_drone_mission.srv import GenerateMission


MAX_REQUEST_BYTES = 8192
SYSTEM_PROMPT = (
    "Propose a high-level drone mission. Return only a JSON object with exactly "
    "these fields: status (ready or needs_clarification), summary (string), "
    "steps (array of objects with action and details), and "
    "clarification_questions (array of strings). Allowed actions are takeoff, "
    "navigate, search_area, capture_photo, return, and land. Never invent "
    "coordinates, altitudes, speeds, geofences, or numeric flight limits. "
    "If required information is missing or unsafe, use "
    "status=needs_clarification, include specific questions, and return no steps. "
)
ALLOWED_ACTIONS = {
    "takeoff",
    "navigate",
    "search_area",
    "capture_photo",
    "return",
    "land",
}


def validate_proposal(proposal: object) -> None:
    if not isinstance(proposal, dict) or set(proposal) != {
        "status",
        "summary",
        "steps",
        "clarification_questions",
    }:
        raise ValueError("Proposal does not match the required mission JSON structure.")
    if not isinstance(proposal["status"], str) or proposal["status"] not in {
        "ready",
        "needs_clarification",
    }:
        raise ValueError("Proposal has an invalid status.")
    if not isinstance(proposal["summary"], str) or not proposal["summary"].strip():
        raise ValueError("Proposal has an empty summary.")
    if not isinstance(proposal["steps"], list):
        raise ValueError("Proposal steps must be a list.")
    if not isinstance(proposal["clarification_questions"], list):
        raise ValueError("Clarification questions must be a list.")

    for step in proposal["steps"]:
        if (
            not isinstance(step, dict)
            or set(step) != {"action", "details"}
            or not isinstance(step["action"], str)
            or step["action"] not in ALLOWED_ACTIONS
            or not isinstance(step["details"], str)
            or not step["details"].strip()
        ):
            raise ValueError("Proposal contains a malformed or unsupported mission step.")
    for question in proposal["clarification_questions"]:
        if not isinstance(question, str) or not question.strip():
            raise ValueError("Proposal contains an invalid clarification question.")

    has_steps = bool(proposal["steps"])
    has_questions = bool(proposal["clarification_questions"])
    if proposal["status"] == "ready" and (not has_steps or has_questions):
        raise ValueError("Ready proposals require steps and no clarification questions.")
    if proposal["status"] == "needs_clarification" and (has_steps or not has_questions):
        raise ValueError(
            "Clarification proposals must contain questions and no mission steps."
        )


class MissionGenerator(Node):
    def __init__(self) -> None:
        super().__init__("mission_generator")
        model_name = self.declare_parameter("model_name", "qwen-1.5b").value
        cpu_cores = self.declare_parameter("cpu_cores", "6-7").value
        max_new_tokens = self.declare_parameter("max_new_tokens", 256).value

        self._helper = qwen_chat_helper
        if model_name not in self._helper.MODELS:
            raise ValueError(
                f"Unsupported model_name '{model_name}'. "
                f"Choose from: {', '.join(self._helper.MODELS)}."
            )
        if not isinstance(max_new_tokens, int) or not 1 <= max_new_tokens <= 512:
            raise ValueError("max_new_tokens must be between 1 and 512.")
        self._model_name = model_name
        self._cpu_cores = cpu_cores
        self._max_new_tokens = max_new_tokens

        self._service = self.create_service(
            GenerateMission, "generate_mission", self._on_generate
        )
        self.get_logger().info(
            f"Mission proposal service ready; using {self._helper.MODELS[model_name]['label']} "
            f"on CPU cores {cpu_cores}."
        )

    def _generate(self, request_text: str) -> str:
        question = f"{SYSTEM_PROMPT}\n\nOperator request:\n{request_text}"
        with contextlib.redirect_stdout(io.StringIO()):
            answer = self._helper.chat_one_shot(
                question=question,
                model_name=self._model_name,
                max_tokens=self._max_new_tokens,
                temp=0.0,
                cores=self._cpu_cores,
            )
        proposal = json.loads(answer)
        validate_proposal(proposal)
        return json.dumps(proposal, separators=(",", ":"), ensure_ascii=True)

    def _on_generate(self, request, response):
        response.success = False
        if not request.request.strip():
            response.error = "The mission request must not be empty."
            return response
        if len(request.request.encode("utf-8")) > MAX_REQUEST_BYTES:
            response.error = f"The mission request exceeds the {MAX_REQUEST_BYTES}-byte limit."
            return response

        started = time.monotonic()
        try:
            response.proposal = self._generate(request.request)
            response.success = True
            response.error = ""
            self.get_logger().info(
                f"Generated mission proposal in {time.monotonic() - started:.2f}s."
            )
        except (OSError, ValueError, RuntimeError, json.JSONDecodeError) as error:
            response.proposal = ""
            response.error = str(error)
            self.get_logger().error(f"Mission generation failed: {error}")
        return response


def main(args=None) -> int:
    rclpy.init(args=args)
    node = None
    try:
        node = MissionGenerator()
        rclpy.spin(node)
    except Exception as error:
        print(f"mission_generator: {error}", file=sys.stderr)
        return 1
    finally:
        if node is not None:
            node.destroy_node()
        rclpy.shutdown()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
