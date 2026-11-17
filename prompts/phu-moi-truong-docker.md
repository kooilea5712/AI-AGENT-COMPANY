[PHỤ LỤC CỦA CODE, không nằm trong docs/thiet-ke.md]
Thư mục làm việc của bạn là nơi có sản phẩm (job thường: thư mục job; job gắn project trên máy: thư mục project, đã ở trên nhánh Git riêng của job). Dùng đường dẫn tương đối. Hệ thống tự commit Git sau mỗi lần bạn chạy xong; bạn KHÔNG chạy git commit/checkout/reset và không đụng thư mục .git.
Tài liệu của job (brief, plan, file chủ đính kèm) đọc bằng đường dẫn bắt đầu `@job/` (read_file/list_dir): `@job/brief.md`, `@job/plan.json`, `@job/inputs/`. Trong lệnh shell chúng nằm ở `/studio-job` (chỉ đọc) khi job gắn project.
Lệnh run_command chạy trong một container Linux dùng một lần (bash); chỉ file trong thư mục làm việc được giữ lại, mọi thứ khác mất sau mỗi lệnh. Dùng cú pháp bash (mkdir -p, cat > file <<'EOF', ls), không dùng PowerShell. Python: `python`.
{moi_truong_sandbox}
Inkscape xuất PNG: `inkscape in.svg -o out.png -w 1024`. git chỉ để đọc.
Công cụ gọi bằng cơ chế tool call, không viết JSON vào câu trả lời. Khi xong việc, trả lời bằng văn bản thường (không gọi công cụ nữa).
describe_image CHỈ để xem hình vẽ gì, bố cục, màu sắc, chữ. KHÔNG dùng nó để kết luận kích thước hay độ trong suốt: model vision thấy ảnh đã bị ghép lên nền trắng/đen và hay đoán sai. Hãy đo bằng công cụ:
- kích thước + kênh alpha: magick identify -format "%w x %h, alpha=%A" file.png
- độ trong suốt: python -c "from PIL import Image; im=Image.open('file.png').convert('RGBA'); print(im.size, im.getpixel((0,0)))" (pixel góc có alpha 0 nghĩa là nền trong suốt)
Số đo từ công cụ luôn thắng mô tả của describe_image.
Mẹo dữ liệu thử đã chạy được: tạo ảnh JPEG có EXIF ngày chụp bằng Pillow: python -c "from PIL import Image; im=Image.new('RGB',(8,8)); ex=im.getexif(); ex.get_ifd(0x8769)[0x9003]='2019:03:14 09:26:53'; im.save('x.jpg', exif=ex)" (ngày EXIF có dạng YYYY:MM:DD HH:MM:SS). Đặt ngày sửa file: touch -d '2020-05-01 10:00:00' file. Không có hàm Image._create_exif.
