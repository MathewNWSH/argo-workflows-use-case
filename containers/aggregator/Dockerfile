FROM python:3.13-slim
COPY --from=ghcr.io/astral-sh/uv:latest /uv /bin/uv
WORKDIR /app
COPY config.py aggregate.py /app/
RUN uv venv /app/.venv && . /app/.venv/bin/activate && uv pip install orjson rich pydantic-settings
ENV PATH="/app/.venv/bin:$PATH"
ENTRYPOINT ["python", "aggregate.py"]
