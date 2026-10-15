FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 POLICEM_DATA=/var/lib/policem
WORKDIR /app
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
COPY app.py reminder_job.py ./
COPY static/ ./static/
RUN useradd --create-home --uid 10001 policem && mkdir -p /var/lib/policem && chown -R policem:policem /var/lib/policem
USER policem
EXPOSE 8000
CMD ["sh","-c","uvicorn app:app --host 0.0.0.0 --port ${PORT:-8000} --proxy-headers"]
