# =============================================================================
# sim-generation-app Dockerfile
# プリビルド済みsct.soを使用（ソースコード不要）
# License: Apache-2.0
# =============================================================================

FROM nvidia/cuda:11.8.0-runtime-ubuntu22.04

ENV DEBIAN_FRONTEND=noninteractive
ENV TZ=Asia/Tokyo
RUN ln -snf /usr/share/zoneinfo/$TZ /etc/localtime && echo $TZ > /etc/timezone

# deadsnakes PPA から安定版 Python 3.11 をインストール
RUN apt-get update && apt-get install -y --no-install-recommends \
    software-properties-common \
    && add-apt-repository ppa:deadsnakes/ppa \
    && apt-get update && apt-get install -y --no-install-recommends \
    python3.11 \
    python3.11-dev \
    python3.11-venv \
    python3.11-distutils \
    git \
    curl \
    libgl1-mesa-glx \
    libglib2.0-0 \
    libsm6 \
    libxext6 \
    libxrender-dev \
    && update-alternatives --install /usr/bin/python python /usr/bin/python3.11 1 \
    && update-alternatives --install /usr/bin/python3 python3 /usr/bin/python3.11 1 \
    && rm -rf /var/lib/apt/lists/*

RUN curl -sS https://bootstrap.pypa.io/get-pip.py | python3.11 \
    && python -m pip install --upgrade pip

WORKDIR /app

# Python依存パッケージのインストール
COPY requirements.txt /app/
RUN pip install --no-cache-dir -r requirements.txt

# アプリケーションコードのコピー（先にコピー）
COPY app/ /app/

# プリビルド済みsct.soを配置
COPY app/trajectory/prebuilt/*.so /app/trajectory/

# HybridNets リポジトリのクローンと重みファイルのダウンロード（COPYの後）
RUN git clone --depth 1 https://github.com/datvuthanh/HybridNets.git /app/hybridnets_repo && \
    mkdir -p /app/hybridnets_repo/weights && \
    curl -L -o /app/hybridnets_repo/weights/hybridnets.pth \
    https://github.com/datvuthanh/HybridNets/releases/download/v1.0/hybridnets.pth


# EfficientNet-B3 の pretrained weights をビルド時にキャッシュ（実行時ダウンロード防止）
RUN python3 -c "\
from torch.utils import model_zoo; \
model_zoo.load_url('https://github.com/lukemelas/EfficientNet-PyTorch/releases/download/1.0/efficientnet-b3-5fb5a3c3.pth')"

RUN chmod +x /app/entrypoint.sh

ENV BASE_DIR=/mnt/data

ENTRYPOINT ["/app/entrypoint.sh"]
