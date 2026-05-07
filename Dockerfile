FROM runpod/pytorch:1.0.3-cu1290-torch290-ubuntu2204

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

RUN git clone https://github.com/Kosinkadink/ComfyUI-VideoHelperSuite.git custom_nodes/ComfyUI-VideoHelperSuite
RUN git clone https://github.com/kijai/ComfyUI-KJNodes.git custom_nodes/ComfyUI-KJNodes
RUN git clone https://github.com/yolain/ComfyUI-Easy-Use.git custom_nodes/ComfyUI-Easy-Use

RUN python -m pip install --upgrade pip setuptools wheel && \
    pip install -r requirements.txt && \
    if [ -f custom_nodes/ComfyUI-LTXVideo/requirements.txt ]; then pip install -r custom_nodes/ComfyUI-LTXVideo/requirements.txt; fi && \
    if [ -f custom_nodes/ComfyUI-VideoHelperSuite/requirements.txt ]; then pip install -r custom_nodes/ComfyUI-VideoHelperSuite/requirements.txt; fi && \
    if [ -f custom_nodes/ComfyUI-KJNodes/requirements.txt ]; then pip install -r custom_nodes/ComfyUI-KJNodes/requirements.txt; fi && \
    if [ -f custom_nodes/ComfyUI-Easy-Use/requirements.txt ]; then pip install -r custom_nodes/ComfyUI-Easy-Use/requirements.txt; fi && \
    pip install sageattention && \
    pip install runpod requests

EXPOSE 8188

CMD ["python", "runpod_handler.py"]
