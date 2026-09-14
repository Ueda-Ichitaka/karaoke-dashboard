# syntax=docker/dockerfile:1
FROM python:3.12-slim AS base

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# Dependencies first for better layer caching.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app

# Run as an unprivileged user.
RUN useradd --create-home --uid 10001 appuser
USER appuser

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/healthz').status==200 else 1)"

# --forwarded-allow-ips trusts X-Forwarded-For only from connections whose
# actual TCP source is in this list (uvicorn checks the real socket peer,
# not the header itself, so this can't be spoofed) - it must name your
# reverse proxy's real address, never "*" (trusting every source lets
# anyone who can reach this port directly - bypassing the proxy entirely -
# spoof their IP and defeat IP-based defenses like the login rate limiter).
# Default here covers a proxy on the same Docker host (127.0.0.1) or on the
# same Docker network (Docker's private bridge range); override via
# FORWARDED_ALLOW_IPS in docker-compose.yml if your proxy connects from
# somewhere else. `exec` keeps uvicorn as PID 1 so it receives SIGTERM
# directly for a clean shutdown, same as the previous exec-form CMD.
CMD exec uvicorn app.main:app --host 0.0.0.0 --port 8000 \
    --proxy-headers --forwarded-allow-ips "${FORWARDED_ALLOW_IPS:-127.0.0.1,172.16.0.0/12}"
