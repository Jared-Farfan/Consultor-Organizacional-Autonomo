FROM python:3.12-slim

WORKDIR /service
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
RUN python -m app.synthetic --output data/legacy/v1/synthetic_events_v1.json --seed 42

EXPOSE 8000
CMD ["uvicorn", "app.api:app", "--host", "0.0.0.0", "--port", "8000"]
