FROM python:3.13-slim
RUN apt-get update && apt-get install -y --no-install-recommends libgl1 libglib2.0-0 libsm6 libxext6 libxrender1 && rm -rf /var/lib/apt/lists/*
COPY --from=ghcr.io/astral-sh/uv:latest /uv /bin/uv
WORKDIR /app
COPY config.py detect.py /app/
COPY yolo26m-obb.pt /model/yolo26m-obb.pt
RUN uv venv /app/.venv && . /app/.venv/bin/activate && uv pip install ultralytics pillow numpy orjson rich
ENV PATH="/app/.venv/bin:$PATH"
ENV MODEL_PATH="/model/yolo26m-obb.pt"
ENTRYPOINT ["python", "detect.py"]