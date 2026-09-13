FROM python:3.12.11-slim-bookworm
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PORT=8080 OMP_NUM_THREADS=1 LOKY_MAX_CPU_COUNT=1
WORKDIR /app
COPY requirements.lock pyproject.toml ./
COPY src ./src
RUN pip install --no-cache-dir -r requirements.lock && pip install --no-cache-dir --no-deps --no-build-isolation .
COPY app.py ./
COPY .streamlit ./.streamlit
COPY artifacts/full ./artifacts/full
RUN useradd --create-home --uid 10001 analyst && chown -R analyst:analyst /app
USER analyst
EXPOSE 8080
HEALTHCHECK --interval=30s --timeout=5s CMD python -c "import urllib.request,os; urllib.request.urlopen('http://127.0.0.1:'+os.environ.get('PORT','8080')+'/_stcore/health')"
CMD ["sh", "-c", "python -m streamlit run app.py --server.address=0.0.0.0 --server.port=${PORT:-8080} --server.headless=true"]
