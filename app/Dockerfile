FROM python:3.12-slim
WORKDIR /app

# Install the application dependencies
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
RUN opentelemetry-bootstrap -a install

# Copy in the source code
COPY main.py .

# Setup an app user so the container doesn't run as the root user
RUN useradd app
USER app

EXPOSE 8080
CMD opentelemetry-instrument uvicorn main:app --host 0.0.0.0 --port 8080