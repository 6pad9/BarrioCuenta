FROM node:22-bookworm-slim AS frontend
WORKDIR /build
COPY package.json package-lock.json ./
RUN npm ci
COPY index.html vite.config.js ./
COPY src ./src
RUN npm run build

FROM python:3.12-slim-bookworm AS runtime
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt && useradd --create-home --uid 10001 barrio
COPY --chown=barrio:barrio backend ./backend
COPY --from=frontend --chown=barrio:barrio /build/dist ./dist
USER barrio
EXPOSE 10000
CMD ["sh", "-c", "exec gunicorn 'backend.cloud:create_cloud_app()' --bind 0.0.0.0:${PORT:-10000} --workers 1 --threads 4 --timeout 120 --access-logfile - --error-logfile -"]
