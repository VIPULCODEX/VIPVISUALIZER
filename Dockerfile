FROM python:3.9-slim

# Install git and git-lfs for cloning the dataset from GitHub
RUN apt-get update && apt-get install -y --no-install-recommends git git-lfs && \
    git lfs install && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy requirements first for Docker layer caching
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the application code
COPY app.py .
COPY kidney_exchange.py .
COPY templates/ templates/
COPY static/ static/

# Clone the full repo (shallow) and pull LFS files, then keep only dataset/
RUN git clone --depth 1 https://github.com/VIPULCODEX/VIPVISUALIZER.git /tmp/repo && \
    cd /tmp/repo && git lfs pull && \
    cp -r /tmp/repo/dataset /app/dataset && \
    rm -rf /tmp/repo

# Verify dataset was cloned correctly
RUN echo "Dataset files:" && ls /app/dataset/ | head -20 && \
    echo "Total .dat files:" && ls /app/dataset/*.dat 2>/dev/null | wc -l && \
    echo "Total .wmd files:" && ls /app/dataset/*.wmd 2>/dev/null | wc -l

# Hugging Face Spaces uses port 7860
EXPOSE 7860
CMD ["gunicorn", "-b", "0.0.0.0:7860", "-w", "2", "--timeout", "120", "app:app"]
