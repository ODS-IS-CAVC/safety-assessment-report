# =============================================================================
# dashcam-preprocessor Dockerfile
# ドラレコ動画前処理: 画像分解・歪み補正・YOLOセグメンテーション
# License: AGPL-3.0
# =============================================================================

FROM nvidia/cuda:11.8.0-runtime-ubuntu22.04

ENV DEBIAN_FRONTEND=noninteractive
ENV TZ=Asia/Tokyo
RUN ln -snf /usr/share/zoneinfo/$TZ /etc/localtime && echo $TZ > /etc/timezone

# Python 3.11 + 必要パッケージのインストール
RUN apt-get update && apt-get install -y --no-install-recommends \
    python3.11 \
    python3.11-dev \
    python3.11-venv \
    python3-pip \
    libgl1-mesa-glx \
    libglib2.0-0 \
    libproj-dev \
    proj-data \
    proj-bin \
    jq \
    && update-alternatives --install /usr/bin/python python /usr/bin/python3.11 1 \
    && update-alternatives --install /usr/bin/python3 python3 /usr/bin/python3.11 1 \
    && rm -rf /var/lib/apt/lists/*

# pip を python3.11 に紐付け
RUN python -m pip install --upgrade pip

WORKDIR /app

# Python パッケージのインストール
COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt

# アプリケーションコードのコピー
COPY app/ /app/

RUN chmod +x /app/entrypoint.sh

ENV BASE_DIR=/mnt/data

ENTRYPOINT ["/app/entrypoint.sh"]
