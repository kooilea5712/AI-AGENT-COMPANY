# Image sandbox cho tool run_command: cùng bộ công cụ agent cần, nhưng chạy trong container
# (giới hạn RAM/CPU, chỉ thấy thư mục job). Dựng: docker build -t studio-sandbox docker/sandbox
# Container chạy với --rm nên `pip install` lúc chạy KHÔNG còn ở lượt sau: thư viện agent hay cần phải nằm sẵn ở đây.
# Mạng: SANDBOX_NETWORK trong .env (none = không ra mạng; bridge = ra được internet, cần cho edge-tts, cào web).
# Debian trixie đã có ImageMagick 7 (lệnh `magick`), nên không cần vỏ bọc tương thích.
FROM python:3.12-slim
RUN apt-get update && apt-get install -y --no-install-recommends \
      ffmpeg imagemagick inkscape git \
      fonts-dejavu-core fonts-noto-core fonts-noto-color-emoji \
    && rm -rf /var/lib/apt/lists/*
# Thư viện Python thường dùng: ảnh/video, giọng đọc (edge-tts gọi dịch vụ online: cần mạng), web/API, cấu hình, test.
RUN pip install --no-cache-dir \
      pillow numpy moviepy \
      edge-tts \
      httpx requests beautifulsoup4 \
      fastapi "uvicorn[standard]" jinja2 python-multipart \
      pyyaml python-dotenv pydantic \
      pytest pytest-asyncio \
      playwright
# Chromium cho Playwright (vẽ thẻ HTML -> PNG, đọc trang công khai). Đặt đường dẫn chung để mọi user trong container dùng được.
ENV PLAYWRIGHT_BROWSERS_PATH=/opt/ms-playwright
RUN playwright install --with-deps chromium && rm -rf /var/lib/apt/lists/*
WORKDIR /job
