FROM python:3.11-slim
WORKDIR /app
COPY system/backend/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt
COPY system/backend/ .
COPY system/kits/ ./kits/
COPY system/db-bootstrap-plan.json ./db-bootstrap-plan.json
COPY license.lic /app/license.lic
CMD ["python", "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]