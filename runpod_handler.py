import os
import subprocess
import time
import uuid
from pathlib import Path

import requests
import runpod


COMFYUI_DIR = Path(os.environ.get("COMFYUI_DIR", "/workspace/ComfyUI"))
COMFYUI_PORT = int(os.environ.get("COMFYUI_PORT", "8188"))
COMFYUI_BASE = f"http://127.0.0.1:{COMFYUI_PORT}"


def wait_for_comfyui(timeout_seconds: int = 180) -> None:
    deadline = time.time() + timeout_seconds
    while time.time() < deadline:
        try:
            response = requests.get(f"{COMFYUI_BASE}/system_stats", timeout=3)
            if response.ok:
                return
        except requests.RequestException:
            pass
        time.sleep(1)
    raise RuntimeError("ComfyUI did not become ready in time.")


def start_comfyui() -> subprocess.Popen:
    process = subprocess.Popen(
        [
            "python",
            "main.py",
            "--listen",
            "0.0.0.0",
            "--port",
            str(COMFYUI_PORT),
            "--disable-auto-launch",
        ],
        cwd=str(COMFYUI_DIR),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.STDOUT,
    )
    wait_for_comfyui()
    return process


COMFYUI_PROCESS = start_comfyui()


def queue_prompt(workflow: dict) -> str:
    client_id = str(uuid.uuid4())
    payload = {"prompt": workflow, "client_id": client_id}
    response = requests.post(f"{COMFYUI_BASE}/prompt", json=payload, timeout=30)
    response.raise_for_status()
    return response.json()["prompt_id"]


def wait_for_completion(prompt_id: str, timeout_seconds: int = 600) -> dict:
    deadline = time.time() + timeout_seconds
    while time.time() < deadline:
        response = requests.get(f"{COMFYUI_BASE}/history/{prompt_id}", timeout=30)
        response.raise_for_status()
        history = response.json()
        if prompt_id in history:
            return history[prompt_id]
        time.sleep(1)
    raise RuntimeError("Workflow execution timed out.")


def handler(job):
    job_input = job.get("input", {})
    workflow = job_input.get("workflow")
    timeout = int(job_input.get("timeout", 600))

    if not isinstance(workflow, dict):
        return {"error": "input.workflow must be a ComfyUI workflow JSON object."}

    try:
        prompt_id = queue_prompt(workflow)
        result = wait_for_completion(prompt_id, timeout_seconds=timeout)
        return {"prompt_id": prompt_id, "result": result}
    except Exception as exc:
        return {"error": str(exc)}


runpod.serverless.start({"handler": handler})
