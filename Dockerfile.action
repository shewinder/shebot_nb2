FROM python:3.11-slim

# 安装uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

# 设置工作目录
WORKDIR /app

# 复制依赖文件
COPY pyproject.toml uv.lock ./

# 使用uv同步依赖（创建虚拟环境）
RUN uv sync --frozen --no-dev

# 复制应用代码
COPY ./res /app/res
COPY run.py /app
COPY ./hoshino /app/hoshino

# 设置环境变量
ENV ENVIRONMENT=prod
ENV DRIVER=~fastapi
ENV LOCALSTORE_CACHE_DIR=/app/data/.cache

# 使用uv运行应用（自动激活虚拟环境）
CMD ["uv", "run", "python", "run.py"]
