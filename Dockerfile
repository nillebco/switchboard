FROM python:3.12-slim
WORKDIR /app
COPY pyproject.toml .
COPY switchboard/ ./switchboard/
RUN pip install .
CMD ["uvicorn", "switchboard.main:app", "--host", "0.0.0.0", "--port", "8018"]
