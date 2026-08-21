FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

COPY backend/requirements.txt backend/requirements-optional.txt backend/
RUN apt-get update && apt-get install -y --no-install-recommends \
    tesseract-ocr \
    curl \
    libcairo2 \
    libpango-1.0-0 \
    libpangocairo-1.0-0 \
    libgdk-pixbuf-2.0-0 \
    libffi8 \
    libharfbuzz0b \
    shared-mime-info \
    fonts-dejavu-core \
    fonts-liberation \
    fonts-noto-core \
    chromium \
    libxml2 \
    libxslt1.1 \
    && rm -rf /var/lib/apt/lists/*
ENV CHROME_BIN=/usr/bin/chromium \
    CHROMIUM_PATH=/usr/bin/chromium \
    PAYSLIP_PDF_ENGINE=chromium
RUN pip install --upgrade pip && pip install -r backend/requirements.txt \
    && pip install -r backend/requirements-optional.txt

COPY . .

RUN mkdir -p vendor/signotec \
    && curl -fsSL --retry 3 --retry-delay 2 \
      -o vendor/signotec/signotec_signoPAD-API_Web_3.5.0.exe \
      "${BAUPASS_SIGNOTEC_INSTALLER_URL:-https://backend.signotec.com/wp-content/uploads/2025/11/signotec_signoPAD-API_Web_3.5.0.exe}" \
    && test "$(wc -c < vendor/signotec/signotec_signoPAD-API_Web_3.5.0.exe)" -gt 5000000

EXPOSE 8000
CMD ["python", "backend/run_prod.py"]
