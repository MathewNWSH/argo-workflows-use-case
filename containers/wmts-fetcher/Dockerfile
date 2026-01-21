FROM python:3.13-slim
COPY --from=ghcr.io/astral-sh/uv:latest /uv /bin/uv
WORKDIR /app
COPY config.py fetch_tiles.py /app/
RUN uv venv /app/.venv && . /app/.venv/bin/activate && uv pip install httpx pillow orjson rich pydantic-settings
ENV PATH="/app/.venv/bin:$PATH"
ENTRYPOINT ["python", "fetch_tiles.py"]
