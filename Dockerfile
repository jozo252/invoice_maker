FROM python:3.11-bullseye
RUN apt-get update && apt-get install -y --no-install-recommends \
    wkhtmltopdf fontconfig libjpeg62-turbo libxrender1 libxext6 \
    && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
ENV PYTHONUNBUFFERED=1
CMD ["gunicorn", "app:create_app()", "--bind", "0.0.0.0:8000", "--workers", "3", "--timeout", "90"]
