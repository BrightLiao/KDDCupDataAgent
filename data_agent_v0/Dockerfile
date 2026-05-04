# syntax=docker/dockerfile:1.7
#
# v0 提交镜像。Build context = 仓库根目录（不是 data_agent_v0/）。
# 因为 v0 通过 path-deps 依赖 ../kddcup2026-starter-kit，
# 两个包都要 COPY 进同样的相对位置才能让 uv sync 解析路径依赖。
#
# Build:
#   cd <repo-root>
#   docker buildx build --platform linux/amd64 --load \
#     -f data_agent_v0/Dockerfile \
#     -t kddcup-v0:latest .

# ---- Stage 1: builder ----
FROM python:3.11-slim-bookworm AS builder

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_INDEX_URL=https://mirrors.cloud.tencent.com/pypi/simple/ \
    PIP_TRUSTED_HOST=mirrors.cloud.tencent.com \
    UV_INDEX_URL=https://mirrors.cloud.tencent.com/pypi/simple/ \
    UV_HTTP_TIMEOUT=120 \
    UV_LINK_MODE=copy

RUN sed -i 's|http://deb.debian.org/debian|http://mirrors.aliyun.com/debian|g' /etc/apt/sources.list.d/debian.sources 2>/dev/null; \
    sed -i 's|http://deb.debian.org/debian|http://mirrors.aliyun.com/debian|g' /etc/apt/sources.list 2>/dev/null; \
    apt-get update && apt-get install -y --no-install-recommends \
        build-essential \
    && rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir uv==0.5.0

WORKDIR /build

# 两个包：保留相对目录结构以匹配 pyproject.toml 的 ../ 路径依赖。
COPY data_agent_v0/pyproject.toml data_agent_v0/uv.lock data_agent_v0/README.md ./data_agent_v0/
COPY data_agent_v0/src ./data_agent_v0/src
COPY kddcup2026-starter-kit/pyproject.toml kddcup2026-starter-kit/README.md ./kddcup2026-starter-kit/
COPY kddcup2026-starter-kit/src ./kddcup2026-starter-kit/src

# repo 根 src/eval — data_agent_v0/output/normalize.py 通过 sys.path 引入
COPY src ./src

RUN --mount=type=cache,target=/root/.cache/uv \
    cd data_agent_v0 && uv sync --frozen --no-dev

# ---- Stage 2: runtime ----
FROM python:3.11-slim-bookworm AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/build/data_agent_v0/.venv/bin:$PATH"

RUN sed -i 's|http://deb.debian.org/debian|http://mirrors.aliyun.com/debian|g' /etc/apt/sources.list.d/debian.sources 2>/dev/null; \
    sed -i 's|http://deb.debian.org/debian|http://mirrors.aliyun.com/debian|g' /etc/apt/sources.list 2>/dev/null; \
    apt-get update && apt-get install -y --no-install-recommends \
        sqlite3 libsqlite3-0 tini \
    && rm -rf /var/lib/apt/lists/*

# Copy build output (venv + source)
COPY --from=builder /build /build
COPY data_agent_v0/entrypoint.py /entrypoint.py

WORKDIR /build/data_agent_v0

# 镜像内代码只读
RUN chmod -R a-w /build /entrypoint.py

# tini 包 PID 1，避免 multiprocessing.spawn 子进程退出后僵尸不回收
ENTRYPOINT ["/usr/bin/tini", "--", "python", "/entrypoint.py"]
