# 前端构建产物由 ../frontend 单独生成并提交到 static/calendar/
FROM --platform=$BUILDPLATFORM python:3.13-slim AS runtime

ENV PIP_INDEX_URL=https://pypi.tuna.tsinghua.edu.cn/simple
ENV INSTALL=True
ENV BROWSER_TYPE=webkit
ENV PLANT_PATH=/app/env
ENV CONFIG_PATH=/app/config.yaml
ENV START_MODE=api

WORKDIR /app
RUN echo "1.0.$(date +%Y%m%d.%H%M)">>docker_version.txt
COPY requirements.txt install.sh ./
RUN apt-get update && apt-get install -y --no-install-recommends bash && rm -rf /var/lib/apt/lists/* \
    && chmod +x /app/install.sh && /app/install.sh

COPY . .
COPY config.example.yaml /app/config.yaml
RUN chmod +x /app/start.sh

EXPOSE 8001
CMD ["/app/start.sh"]
