# BÀN GIAO (HANDOFF)

## Nội dung đã thực hiện
- Xây dựng script Python `rename_script.py` để đổi tên hàng loạt file JPG dựa trên dữ liệu thời gian.
- Tích hợp đọc dữ liệu EXIF (DateTimeOriginal) và cơ chế fallback sang ngày sửa file (mtime).
- Cung cấp chế độ `--dry-run` để xem trước thay đổi.

## Cách mở hoặc chạy
1. Đảm bảo đã cài đặt Python 3.12 và thư viện Pillow.
2. Chạy thử nghiệm (không đổi tên thật):
   `python3 deliverables/rename_script.py <đường_dẫn_thư_mục_ảnh> --dry-run`
3. Chạy thực tế:
   `python3 deliverables/rename_script.py <đường_dẫn_thư_mục_ảnh>`

## Giới hạn đã biết
- Chỉ xử lý file định dạng `.jpg` và `.jpeg`.
- Không xử lý đệ quy các thư mục con bên trong thư mục đầu vào.
- Script giả định quyền ghi (write permission) trên thư mục chứa ảnh.

## Giả định đã dùng
- Sử dụng thư viện Pillow để đọc dữ liệu EXIF.
- Định dạng tên file mặc định là `YYYYMMDD_HHMMSS_tên_gốc.jpg`.
- Nếu file không có EXIF, lấy thời gian sửa file gần nhất của hệ thống.
