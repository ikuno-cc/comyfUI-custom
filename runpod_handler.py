import os
import base64
import subprocess
import time
import uuid
import mimetypes
from pathlib import Path

import requests
import runpod


COMFYUI_DIR = Path(os.environ.get("COMFYUI_DIR", "/workspace/ComfyUI"))
COMFYUI_PORT = int(os.environ.get("COMFYUI_PORT", "8188"))
COMFYUI_BASE = f"http://127.0.0.1:{COMFYUI_PORT}"
COMFYUI_INPUT_DIR = COMFYUI_DIR / "input"
COMFYUI_OUTPUT_DIR = COMFYUI_DIR / "output"


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


def upload_bytes_to_comfyui(file_bytes: bytes, filename: str, subfolder: str = "") -> dict:
    files = {"image": (filename, file_bytes, "application/octet-stream")}
    data = {"overwrite": "true", "type": "input", "subfolder": subfolder}
    response = requests.post(f"{COMFYUI_BASE}/upload/image", files=files, data=data, timeout=120)
    response.raise_for_status()
    return response.json()


def download_url_bytes(url: str) -> tuple[bytes, str]:
    response = requests.get(url, timeout=120)
    response.raise_for_status()
    content_type = response.headers.get("content-type", "").split(";")[0].strip()
    ext = mimetypes.guess_extension(content_type) or ""
    return response.content, ext


def decode_base64_file(data: str) -> tuple[bytes, str]:
    # Supports plain base64 and data URLs: data:<mime>;base64,<data>
    if data.startswith("data:") and "," in data:
        header, payload = data.split(",", 1)
        mime = header.split(";")[0].replace("data:", "").strip()
        ext = mimetypes.guess_extension(mime) or ""
        return base64.b64decode(payload), ext
    return base64.b64decode(data), ""


def replace_placeholder_in_workflow(workflow: dict, placeholder: str, value: str) -> None:
    for node in workflow.values():
        if not isinstance(node, dict):
            continue
        inputs = node.get("inputs")
        if not isinstance(inputs, dict):
            continue
        for key, input_value in inputs.items():
            if input_value == placeholder:
                inputs[key] = value


def save_video_to_input(file_bytes: bytes, ext: str = ".mp4") -> str:
    filename = f"runpod_video_{uuid.uuid4().hex}{ext if ext else '.mp4'}"
    COMFYUI_INPUT_DIR.mkdir(parents=True, exist_ok=True)
    (COMFYUI_INPUT_DIR / filename).write_bytes(file_bytes)
    return filename


def save_audio_to_input(file_bytes: bytes, ext: str = ".wav") -> str:
    filename = f"runpod_audio_{uuid.uuid4().hex}{ext if ext else '.wav'}"
    COMFYUI_INPUT_DIR.mkdir(parents=True, exist_ok=True)
    (COMFYUI_INPUT_DIR / filename).write_bytes(file_bytes)
    return filename


def prepare_media(job_input: dict, workflow: dict) -> dict:
    media_info = {}

    image_filename = None
    if isinstance(job_input.get("image_url"), str):
        image_bytes, guessed_ext = download_url_bytes(job_input["image_url"])
        filename = f"runpod_image_{uuid.uuid4().hex}{guessed_ext or '.png'}"
        uploaded = upload_bytes_to_comfyui(image_bytes, filename)
        image_filename = uploaded.get("name", filename)
    elif isinstance(job_input.get("image_base64"), str):
        image_bytes, guessed_ext = decode_base64_file(job_input["image_base64"])
        filename = f"runpod_image_{uuid.uuid4().hex}{guessed_ext or '.png'}"
        uploaded = upload_bytes_to_comfyui(image_bytes, filename)
        image_filename = uploaded.get("name", filename)

    if image_filename:
        replace_placeholder_in_workflow(workflow, "__IMAGE__", image_filename)
        media_info["image_filename"] = image_filename

    video_filename = None
    if isinstance(job_input.get("video_url"), str):
        video_bytes, guessed_ext = download_url_bytes(job_input["video_url"])
        video_filename = save_video_to_input(video_bytes, guessed_ext or ".mp4")
    elif isinstance(job_input.get("video_base64"), str):
        video_bytes, guessed_ext = decode_base64_file(job_input["video_base64"])
        video_filename = save_video_to_input(video_bytes, guessed_ext or ".mp4")

    if video_filename:
        replace_placeholder_in_workflow(workflow, "__VIDEO__", video_filename)
        media_info["video_filename"] = video_filename

    audio_filename = None
    if isinstance(job_input.get("audio_url"), str):
        audio_bytes, guessed_ext = download_url_bytes(job_input["audio_url"])
        audio_ext = guessed_ext.lower() if guessed_ext else ".wav"
        if audio_ext not in (".wav", ".mp3"):
            audio_ext = ".wav"
        audio_filename = save_audio_to_input(audio_bytes, audio_ext)
    elif isinstance(job_input.get("audio_base64"), str):
        audio_bytes, guessed_ext = decode_base64_file(job_input["audio_base64"])
        audio_ext = guessed_ext.lower() if guessed_ext else ".wav"
        if audio_ext not in (".wav", ".mp3"):
            audio_ext = ".wav"
        audio_filename = save_audio_to_input(audio_bytes, audio_ext)

    if audio_filename:
        replace_placeholder_in_workflow(workflow, "__AUDIO__", audio_filename)
        media_info["audio_filename"] = audio_filename

    return media_info


def queue_prompt(workflow: dict) -> str:
    client_id = str(uuid.uuid4())
    payload = {"prompt": workflow, "client_id": client_id}
    response = requests.post(f"{COMFYUI_BASE}/prompt", json=payload, timeout=30)
    if not response.ok:
        details = response.text
        try:
            details = response.json()
        except Exception:
            pass
        raise RuntimeError(f"ComfyUI /prompt rejected request ({response.status_code}): {details}")

    data = response.json()
    if "prompt_id" not in data:
        raise RuntimeError(f"ComfyUI /prompt response missing prompt_id: {data}")
    return data["prompt_id"]


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


def file_to_base64(file_path: Path) -> str:
    return base64.b64encode(file_path.read_bytes()).decode("utf-8")


def collect_outputs(history_entry: dict) -> list[dict]:
    output_items = []
    outputs = history_entry.get("outputs", {})
    for node_id, node_output in outputs.items():
        if not isinstance(node_output, dict):
            continue
        for key in ("images", "gifs", "videos"):
            files = node_output.get(key, [])
            if not isinstance(files, list):
                continue
            for f in files:
                if not isinstance(f, dict):
                    continue
                filename = f.get("filename")
                subfolder = f.get("subfolder", "")
                if not filename:
                    continue
                candidate = (COMFYUI_OUTPUT_DIR / subfolder / filename).resolve()
                if not candidate.exists():
                    continue
                output_items.append(
                    {
                        "node_id": node_id,
                        "type": key,
                        "filename": filename,
                        "subfolder": subfolder,
                        "base64": file_to_base64(candidate),
                    }
                )
    return output_items


def handler(job):
    job_input = job.get("input", {})
    workflow = job_input.get("workflow")
    timeout = int(job_input.get("timeout", 600))

    if not isinstance(workflow, dict):
        return {"error": "input.workflow must be a ComfyUI workflow JSON object."}

    try:
        media_info = prepare_media(job_input, workflow)
        prompt_id = queue_prompt(workflow)
        result = wait_for_completion(prompt_id, timeout_seconds=timeout)
        output_files = collect_outputs(result)
        return {
            "prompt_id": prompt_id,
            "media": media_info,
            "result": result,
            "outputs_base64": output_files,
        }
    except Exception as exc:
        return {"error": str(exc)}


runpod.serverless.start({"handler": handler})
