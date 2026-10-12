# Evidence Store v0 (Phase 2.3)
# 의존성은 빌드 시점에 설치한다 — 클러스터 안에서 런타임 다운로드 없음.
FROM python:3.14-slim

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY app.py .

RUN useradd --uid 10001 --no-create-home store && mkdir -p /data && chown store /data
USER 10001

ENV EVIDENCE_DATA_DIR=/data PYTHONUNBUFFERED=1
EXPOSE 8080
# 인덱스가 프로세스 메모리에 있으므로 워커는 반드시 1개
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8080", "--workers", "1"]
