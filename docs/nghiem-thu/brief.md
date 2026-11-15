Mục tiêu: Viết script Python để đổi tên hàng loạt file ảnh trong một thư mục dựa trên thời gian chỉnh sửa file (do hạn chế thư viện chuẩn, không dùng EXIF).

Đầu ra:
- File: rename_photos.py
- Định dạng: .py

Ràng buộc:
- Chỉ sử dụng thư viện chuẩn của Python (không pip install).
- Nhận đường dẫn thư mục qua tham số dòng lệnh.
- Quy tắc đặt tên: YYYYMMDD_HHMMSS_TênGốc.ext.
- Xử lý trùng lặp: Thêm số thứ tự nếu cùng thời gian.
- Chế độ --dry-run: Chỉ in ra kết quả dự kiến, không đổi tên thật.

Nằm ngoài phạm vi:
- Xử lý file không phải ảnh.
- Chỉnh sửa nội dung ảnh.

Tiêu chí nghiệm thu:
1. Chạy `py rename_photos.py --dry-run <path>`: In ra danh sách tên mới dự kiến.
2. Chạy `py rename_photos.py <path>`: Các file trong thư mục được đổi tên đúng quy tắc.
3. Kiểm tra file rename_photos.py tồn tại và chạy được trên Windows 11.
