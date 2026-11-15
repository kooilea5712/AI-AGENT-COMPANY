# Image sandbox cho tool run_command: cùng bộ công cụ agent cần, nhưng chạy trong container
# (không mạng, giới hạn RAM/CPU, chỉ thấy thư mục job). Dựng: docker build -t studio-sandbox docker/sandbox
# Debian trixie đã có ImageMagick 7 (lệnh `magick`), nên không cần vỏ bọc tương thích.
FROM python:3.12-slim
RUN apt-get update && apt-get install -y --no-install-recommends \
      ffmpeg imagemagick inkscape fonts-dejavu-core git \
    && rm -rf /var/lib/apt/lists/*
RUN pip install --no-cache-dir pillow
WORKDIR /job
