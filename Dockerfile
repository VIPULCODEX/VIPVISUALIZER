FROM python:3.9-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Hugging Face Spaces passes the port via the $PORT environment variable.
# It defaults to 7860.
EXPOSE 7860
CMD ["gunicorn", "-b", "0.0.0.0:7860", "app:app"]
