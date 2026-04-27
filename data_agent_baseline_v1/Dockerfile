# syntax=docker/dockerfile:1.7
#
# baseline-v1 提交镜像。Build context = 仓库根目录（不是 data_agent_baseline_v1/）。
# 因为 baseline_v1 通过 path-deps 依赖 ../kddcup2026-starter-kit 与 ../data_agent_v0，
# 三个包都要 COPY 进同样的相对位置才能让 uv sync 解析路径依赖。
#
# Build:
#   cd <repo-root>
#   docker buildx build --platform linux/amd64 --load \
#     -f data_agent_baseline_v1/Dockerfile \
#     -t kddcup-baseline-v1:dev .

# ---- Stage 1: builder ----
FROM python:3.11-slim-bookworm AS builder

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_INDEX_URL=https://mirrors.aliyun.com/pypi/simple/ \
    PIP_TRUSTED_HOST=mirrors.aliyun.com \
    UV_INDEX_URL=https://mirrors.aliyun.com/pypi/simple/ \
    UV_LINK_MODE=copy

RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential \
    && rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir uv==0.5.0

WORKDIR /build

# 三个包：保留相对目录结构以匹配 pyproject.toml 的 ../ 路径依赖。
# README.md 是 hatchling 构建 editable wheel 必读项，所以 .dockerignore 把 README.md 加白名单.
COPY data_agent_baseline_v1/pyproject.toml data_agent_baseline_v1/uv.lock data_agent_baseline_v1/README.md ./data_agent_baseline_v1/
COPY data_agent_baseline_v1/src ./data_agent_baseline_v1/src
COPY data_agent_v0/pyproject.toml data_agent_v0/README.md ./data_agent_v0/
COPY data_agent_v0/src ./data_agent_v0/src
COPY kddcup2026-starter-kit/pyproject.toml kddcup2026-starter-kit/README.md ./kddcup2026-starter-kit/
COPY kddcup2026-starter-kit/src ./kddcup2026-starter-kit/src

# uv sync 在 baseline_v1 dir 内运行，自动把 baseline / v0 装入 baseline_v1/.venv
# BuildKit cache mount → wheels 跨 build 复用；mirrors.aliyun.com 走国内 PyPI.
RUN --mount=type=cache,target=/root/.cache/uv \
    cd data_agent_baseline_v1 && uv sync --frozen --no-dev

# ---- Stage 2: runtime ----
FROM python:3.11-slim-bookworm AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/build/data_agent_baseline_v1/.venv/bin:$PATH"

RUN apt-get update && apt-get install -y --no-install-recommends \
        sqlite3 libsqlite3-0 tini \
    && rm -rf /var/lib/apt/lists/*

# Copy build output (venv + source). 不把 build deps 带进来。
COPY --from=builder /build /build
COPY data_agent_baseline_v1/entrypoint.py /entrypoint.py

WORKDIR /build/data_agent_baseline_v1

# 镜像内代码只读，防误改与 .pyc 写
RUN chmod -R a-w /build /entrypoint.py

# tini 包 PID 1，避免 multiprocessing.spawn 子进程退出后僵尸不回收。
# 不内置任何 key；MODEL_API_URL/KEY/NAME 由评测注入
ENTRYPOINT ["/usr/bin/tini", "--", "python", "/entrypoint.py"]
