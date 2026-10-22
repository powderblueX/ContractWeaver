FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1
WORKDIR /app
COPY requirements.txt ./
RUN pip install -r requirements.txt \
    && groupadd --gid 10001 app \
    && useradd --uid 10001 --gid app --no-create-home app \
    && mkdir -p /app/data && chown app:app /app/data
COPY app ./app
COPY resources/contracts/templates ./resources/contracts/templates
EXPOSE 8000
ENTRYPOINT ["python", "-m", "app.container_entrypoint"]
CMD ["python", "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
