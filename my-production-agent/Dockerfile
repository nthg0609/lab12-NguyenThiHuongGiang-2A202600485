# Stage 1: Builder
FROM python:3.9-slim as builder
WORKDIR /app
COPY requirements.txt .
RUN mkdir /install && pip install --no-cache-dir --prefix=/install -r requirements.txt

# Stage 2: Runtime
FROM python:3.9-slim
WORKDIR /app
ENV PATH="/usr/local/bin:$PATH"
RUN pip install --no-cache-dir uvicorn fastapi
COPY --from=builder /install /usr/local
COPY . .
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]