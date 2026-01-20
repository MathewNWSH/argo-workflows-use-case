FROM python:3.13-slim
COPY --from=ghcr.io/astral-sh/uv:latest /uv /bin/uv
WORKDIR /app
COPY config.py convert.py /app/
RUN uv venv /app/.venv && . /app/.venv/bin/activate && uv pip install orjson rich
ENV PATH="/app/.venv/bin:$PATH"
ENTRYPOINT ["python", "convert.py"]
