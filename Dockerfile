FROM python:3.12-slim
WORKDIR /app
COPY pyproject.toml .
RUN pip install -e .
COPY switchboard/ ./switchboard/
CMD ["uvicorn", "switchboard.main:app", "--host", "0.0.0.0", "--port", "8018"]
