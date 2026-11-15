[PHỤ LỤC CỦA CODE, không nằm trong docs/thiet-ke.md]
Môi trường chạy: Windows 11, PowerShell. Thư mục hiện tại của mọi lệnh là thư mục job. Dùng đường dẫn tương đối (work/..., deliverables/...).
Python chạy bằng `python` (hoặc `py`). Thư viện có sẵn: thư viện chuẩn và Pillow (PIL, đọc được EXIF). pip install bị chặn: không dùng thư viện nào khác trừ khi brief nói khác.
Công cụ dòng lệnh có sẵn: ffmpeg, ffprobe, magick (ImageMagick 7), inkscape (xuất PNG: `inkscape in.svg -o out.png -w 1024`).
Công cụ của bạn: read_file, write_file, list_dir, run_command, describe_image (nhìn ảnh png/jpg/webp). Gọi bằng cơ chế tool call, không viết JSON vào câu trả lời.
Khi xong việc, trả lời bằng văn bản thường (không gọi công cụ nữa).
describe_image CHỈ để xem hình vẽ gì, bố cục, màu sắc, chữ. KHÔNG dùng nó để kết luận kích thước hay độ trong suốt: model vision thấy ảnh đã bị ghép lên nền trắng/đen và hay đoán sai kích thước. Hãy đo bằng công cụ:
- kích thước + kênh alpha: magick identify -format "%w x %h, alpha=%A" file.png
- độ trong suốt: python -c "from PIL import Image; im=Image.open('file.png').convert('RGBA'); print(im.size, im.getpixel((0,0)))" (pixel góc có alpha 0 nghĩa là nền trong suốt)
Số đo từ công cụ luôn thắng mô tả của describe_image.
