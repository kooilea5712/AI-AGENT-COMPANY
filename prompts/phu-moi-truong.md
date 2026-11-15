[PHỤ LỤC CỦA CODE, không nằm trong docs/thiet-ke.md]
Môi trường chạy: Windows 11, PowerShell. Thư mục hiện tại của mọi lệnh là thư mục job. Dùng đường dẫn tương đối (work/..., deliverables/...).
Python chạy bằng `python` (hoặc `py`). Thư viện có sẵn: thư viện chuẩn và Pillow (PIL, đọc được EXIF). pip install bị chặn: không dùng thư viện nào khác trừ khi brief nói khác.
Công cụ dòng lệnh có sẵn: ffmpeg, ffprobe, magick (ImageMagick 7), inkscape (xuất PNG: `inkscape in.svg -o out.png -w 1024`).
Công cụ của bạn: read_file, write_file, list_dir, run_command, describe_image (nhìn ảnh png/jpg/webp). Gọi bằng cơ chế tool call, không viết JSON vào câu trả lời.
Khi xong việc, trả lời bằng văn bản thường (không gọi công cụ nữa).
