ARG BASE_IMAGE=python:3.12-slim
FROM ${BASE_IMAGE}

WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1

# 国内部署时用 compose 的 build.args 换成镜像源，仓库默认走官方
ARG PIP_INDEX_URL=https://pypi.org/simple

COPY proxy/requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -i ${PIP_INDEX_URL} -r /app/requirements.txt

COPY proxy/ /app/proxy/
COPY static/ /app/static/

RUN useradd -u 10002 -m demo && chown -R demo:demo /app
USER 10002

EXPOSE 8080
# 单进程：内存限流才是准的。
CMD ["python", "-m", "uvicorn", "proxy.server:app", "--host", "0.0.0.0", "--port", "8080", "--workers", "1"]
