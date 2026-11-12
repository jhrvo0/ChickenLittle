FROM python:3.13-slim@sha256:e48f59cdba69a3cbd9ed2cf0f348d90d45a8d350d98134cf1070bc106ee9ed90
WORKDIR /workspace
COPY requirements.txt requirements-mlops.lock pyproject.toml README.md ./
COPY ops/mlops/requirements-server.lock /tmp/motionlab-server.lock
RUN pip install --no-cache-dir -r /tmp/motionlab-server.lock
COPY ml ./ml
COPY terminal ./terminal
COPY simulator ./simulator
RUN pip install --no-cache-dir --no-deps .
ENV PYTHONUNBUFFERED=1
ENV OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1
CMD ["python", "-m", "ml.inference_api", "--host", "0.0.0.0"]
