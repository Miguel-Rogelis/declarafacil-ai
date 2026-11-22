# 1) Construye el front (React + Vite). `npm run build` revisa los tipos con tsc antes de empaquetar.
FROM node:22-slim AS front
WORKDIR /front
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

# 2) Base del backend: Python + Tesseract en español (OCR de escaneos y fotos, HU-38)
FROM python:3.12-slim AS base
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
RUN apt-get update \
    && apt-get install -y --no-install-recommends tesseract-ocr tesseract-ocr-spa \
    && rm -rf /var/lib/apt/lists/*
WORKDIR /app/backend
COPY backend/requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# 3) Compuerta de calidad (HU-43): si una prueba falla, la imagen no se construye y Render no despliega
FROM base AS pruebas
COPY backend/requirements-dev.txt ./
RUN pip install --no-cache-dir -r requirements-dev.txt
COPY backend/ ./
RUN LLM_MODE=simulado ALMACEN=memoria python -m pytest -q -p no:cacheprovider \
    && touch /tmp/pruebas-ok

# 4) Imagen final: solo arranca si la etapa de pruebas terminó bien (por eso copia su marca)
FROM base
ENV FRONTEND_DIR=/app/frontend/dist
COPY --from=pruebas /tmp/pruebas-ok /tmp/pruebas-ok
COPY backend/app ./app
COPY backend/data ./data
COPY --from=front /front/dist /app/frontend/dist
# La extensión de Chrome, comprimida para descargarla desde la app (sin sus pruebas ni la ficha de la tienda)
COPY extension /tmp/extension
RUN python /tmp/extension/tienda/empaquetar.py /app/frontend/dist/declarafacil-extension.zip \
    && rm -rf /tmp/extension
EXPOSE 8000
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
