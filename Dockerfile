FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

COPY backend/requirements.txt backend/requirements.txt
RUN apt-get update && apt-get install -y --no-install-recommends \
    tesseract-ocr \
    curl \
    && rm -rf /var/lib/apt/lists/*
RUN pip install --upgrade pip && pip install -r backend/requirements.txt

COPY . .

RUN mkdir -p vendor/signotec \
    && curl -fsSL --retry 3 --retry-delay 2 \
      -o vendor/signotec/signotec_signoPAD-API_Web_3.5.0.exe \
      "${BAUPASS_SIGNOTEC_INSTALLER_URL:-https://backend.signotec.com/wp-content/uploads/2025/11/signotec_signoPAD-API_Web_3.5.0.exe}" \
    && test "$(wc -c < vendor/signotec/signotec_signoPAD-API_Web_3.5.0.exe)" -gt 5000000

EXPOSE 8000
CMD ["python", "backend/run_prod.py"]
