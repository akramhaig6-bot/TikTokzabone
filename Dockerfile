FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt && useradd --uid 10001 --create-home botuser
COPY --chown=botuser:botuser . .
RUN mkdir -p /app/data && chown botuser:botuser /app/data
USER botuser
ENV PORT=8000 DATA_DIR=/app/data
EXPOSE 8000
CMD ["python", "app.py"]
