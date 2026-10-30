#!/usr/bin/env python3
import os
import re
import subprocess
import sys
import time
from pathlib import Path

HOME = Path.home()
REPO = HOME / "a733_npu_driver"
LLAMA_BIN = HOME / "llama.cpp/build/bin"
LLAMA_CLI = LLAMA_BIN / "llama-cli"

MODELS = {
    "qwen-0.5b": {
        "gguf": REPO / "models/qwen2.5-0.5b-instruct-q8_0.gguf",
        "speed": "~18 tok/s",
        "rss": "~1.1 GB",
        "label": "Qwen2.5-0.5B Q8_0",
        "ctx": 8192,
    },
    "qwen-1.5b": {
        "gguf": REPO / "models/qwen2.5-1.5b-instruct-q4_k_m.gguf",
        "speed": "~8.5 tok/s",
        "rss": "~2.0 GB",
        "label": "Qwen2.5-1.5B Q4_K_M",
        "ctx": 8192,
    },
    "qwen-3b": {
        "gguf": REPO / "models/qwen2.5-3b-instruct-q4_k_m.gguf",
        "speed": "~4 tok/s",
        "rss": "~3.7 GB",
        "label": "Qwen2.5-3B Q4_K_M (EXPERIMENTAL)",
        "ctx": 4096,
    },
}


def _parse_timing(stderr_text):
    prompt_tps = gen_tps = None
    match = re.search(r"Prompt:\s*([\d.]+)\s*t/s", stderr_text)
    if match:
        prompt_tps = float(match.group(1))
    match = re.search(r"Generation:\s*([\d.]+)\s*t/s", stderr_text)
    if match:
        gen_tps = float(match.group(1))
    return prompt_tps, gen_tps


def chat_one_shot(question, model_name, max_tokens, temp, cores):
    cfg = MODELS[model_name]
    if not cfg["gguf"].exists():
        raise FileNotFoundError(f"GGUF not found: {cfg['gguf']}")

    print(f"LLM Chat -- {cfg['label']} | {cfg['speed']} | {cfg['rss']}")
    print(f"Q: {question}")
    print()

    cmd = [
        str(LLAMA_CLI),
        "-m", str(cfg["gguf"]),
        "-p", question,
        "-n", str(max_tokens),
        "-t", "2",
        "--cpu-range", cores,
        "--temp", str(temp),
        "-c", str(cfg["ctx"]),
        "--simple-io",
        "--log-disable",
        "--single-turn",
        "--chat-template", "chatml",
    ]

    env = {"LD_LIBRARY_PATH": str(LLAMA_BIN)}
    started = time.time()
    process = subprocess.Popen(
        cmd,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        env={**os.environ, **env},
    )
    process.stdin.write("/exit\n")
    process.stdin.close()

    answer_lines = []
    timing_lines = []
    in_answer = False
    for line in process.stdout:
        line = line.rstrip("\n\r")
        if "Exiting" in line or "available commands" in line:
            continue
        if line.startswith("> "):
            in_answer = True
            continue
        if in_answer and line.strip():
            if line.startswith("[ Prompt:") or line.startswith("[ Generation:"):
                timing_lines.append(line)
                continue
            answer_lines.append(line)
            sys.stdout.write(line + "\n")
            sys.stdout.flush()

    process.wait()
    for line in process.stderr:
        timing_lines.append(line.rstrip("\n\r"))
    if process.returncode != 0:
        detail = "\n".join(timing_lines).strip()
        raise RuntimeError(
            f"llama-cli exited with status {process.returncode}"
            + (f": {detail}" if detail else "")
        )

    elapsed = time.time() - started
    prompt_tps, gen_tps = _parse_timing("\n".join(timing_lines))
    print()
    parts = [f"-- {cfg['label']} | wall {elapsed:.1f}s"]
    if prompt_tps:
        parts.append(f"prompt {prompt_tps:.0f} t/s")
    if gen_tps:
        parts.append(f"gen {gen_tps:.0f} t/s")
    parts.append(f"cores {cores}")
    print(" | ".join(parts))
    return "\n".join(answer_lines)
