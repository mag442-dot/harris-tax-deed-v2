FROM python:3.12-slim
WORKDIR /app
COPY pipeline.py .
RUN useradd --uid 10001 --create-home worker && mkdir /state && chown worker /state
USER worker
ENTRYPOINT ["python", "pipeline.py"]
