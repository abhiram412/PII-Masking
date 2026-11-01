FROM python:3.12-slim

WORKDIR /app
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY masking/ /app/masking/
COPY qrng/ /app/qrng/
COPY data/schema/ /app/data/schema/
COPY cli.py seed.py streamlit_app.py main.py /app/

# Note: data/csv/ and keys/ are NOT copied (guidelines: no pack data, no secrets).
# Mount them at runtime or seed with --fallback-sample for demo.
# Example: docker run -v $(pwd)/data/csv:/app/data/csv -e IBM_QUANTUM_TOKEN=... ...

EXPOSE 8501
HEALTHCHECK --interval=30s --timeout=5s CMD python -c "import urllib.request;urllib.request.urlopen('http://localhost:8501/_stcore/health').read()"

CMD ["streamlit", "run", "streamlit_app.py", "--server.port=8501", "--server.address=0.0.0.0"]
