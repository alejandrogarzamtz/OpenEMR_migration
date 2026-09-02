FROM python:3.13-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY app app
COPY alembic.ini .
COPY alembic alembic
COPY start.sh .
COPY tests tests
RUN chmod +x start.sh
CMD ["./start.sh"]
