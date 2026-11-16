[PHỤ LỤC CỦA CODE, không nằm trong docs/thiet-ke.md]
Thư mục làm việc của bạn là nơi có sản phẩm (job thường: thư mục job; job gắn project trên máy: thư mục project, đã ở trên nhánh Git riêng của job). Dùng đường dẫn tương đối. Hệ thống tự commit Git sau mỗi lần bạn chạy xong; bạn KHÔNG chạy git commit/checkout/reset và không đụng thư mục .git.
Tài liệu của job (brief, plan, file chủ đính kèm) đọc bằng đường dẫn bắt đầu `@job/` (read_file/list_dir): `@job/brief.md`, `@job/plan.json`, `@job/inputs/`.
Môi trường chạy lệnh: Windows 11, PowerShell, CHẠY TRỰC TIẾP trên máy chủ studio (không có sandbox Docker), nên cẩn thận: chỉ làm trong thư mục làm việc. Python chạy bằng `python` (hoặc `py`), có thư viện chuẩn và Pillow; pip install bị chặn.
Công cụ dòng lệnh có sẵn: ffmpeg, ffprobe, magick (ImageMagick 7), inkscape (xuất PNG: `inkscape in.svg -o out.png -w 1024`).
Công cụ gọi bằng cơ chế tool call, không viết JSON vào câu trả lời. Khi xong việc, trả lời bằng văn bản thường (không gọi công cụ nữa).
describe_image CHỈ để xem hình vẽ gì, bố cục, màu sắc, chữ. KHÔNG dùng nó để kết luận kích thước hay độ trong suốt; đo bằng công cụ (magick identify -format "%w x %h, alpha=%A" file.png, hoặc Pillow). Số đo từ công cụ luôn thắng mô tả của describe_image.
