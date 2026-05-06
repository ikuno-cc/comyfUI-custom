FROM runpod/pytorch:2.4.0-py3.10-cuda12.1.1-devel-ubuntu22.04

ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONUNBUFFERED=1 \
    COMFYUI_DIR=/workspace/ComfyUI \
    COMFYUI_PORT=8188

WORKDIR /workspace

RUN apt-get update && apt-get install -y --no-install-recommends \
    git \
    libgl1 \
    libglib2.0-0 \
    libsm6 \
    libxrender1 \
    libxext6 \
    && rm -rf /var/lib/apt/lists/*

COPY . ${COMFYUI_DIR}

WORKDIR ${COMFYUI_DIR}

RUN python -m pip install --upgrade pip setuptools wheel && \
    pip install -r requirements.txt && \
    pip install -r custom_nodes/ComfyUI-LTXVideo/requirements.txt && \
    pip install runpod requests

EXPOSE 8188

CMD ["python", "runpod_handler.py"]
