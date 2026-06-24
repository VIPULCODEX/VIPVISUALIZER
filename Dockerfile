FROM python:3.9-slim

WORKDIR /app

# Copy requirements first for Docker layer caching
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the application code
COPY app.py .
COPY kidney_exchange.py .
COPY templates/ templates/
COPY static/ static/
COPY dataset/ dataset/

# Verify dataset was cloned correctly
RUN echo "Dataset files:" && ls /app/dataset/ | head -20 && \
    echo "Total .dat files:" && ls /app/dataset/*.dat 2>/dev/null | wc -l && \
    echo "Total .wmd files:" && ls /app/dataset/*.wmd 2>/dev/null | wc -l

# Hugging Face Spaces uses port 7860
EXPOSE 7860
CMD ["gunicorn", "-b", "0.0.0.0:7860", "-w", "1", "--threads", "4", "--timeout", "180", "app:app"]
