FROM python:3.9-slim

# Install git and git-lfs for cloning the dataset from GitHub
RUN apt-get update && apt-get install -y --no-install-recommends git git-lfs && \
    git lfs install && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy requirements first for Docker layer caching
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the application code (dataset/ is excluded via .dockerignore-like approach)
COPY app.py .
COPY kidney_exchange.py .
COPY templates/ templates/
COPY static/ static/

# Clone ONLY the dataset folder from GitHub using git LFS
RUN git clone --depth 1 --filter=blob:none --sparse \
    https://github.com/VIPULCODEX/VIPVISUALIZER.git /tmp/repo && \
    cd /tmp/repo && git sparse-checkout set dataset && git lfs pull && \
    mv /tmp/repo/dataset /app/dataset && \
    rm -rf /tmp/repo

# Hugging Face Spaces uses port 7860
EXPOSE 7860
CMD ["gunicorn", "-b", "0.0.0.0:7860", "-w", "2", "--timeout", "120", "app:app"]
