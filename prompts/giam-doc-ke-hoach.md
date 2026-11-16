NHIỆM VỤ HIỆN TẠI: lập kế hoạch và chia việc cho các model con (bước 3).
Đọc `@job/brief.md` (và mọi phản hồi của chủ nếu có), rồi ghi `@job/plan.json` bằng write_file, ĐÚNG định dạng JSON sau, không thêm chữ ngoài JSON:
{
  "summary": "một hai câu: cách làm tổng thể",
  "tasks": [
    {"id": "T1", "role": "software", "title": "tên ngắn",
     "goal": "kết quả cần có (mô tả kết quả, không mô tả từng bước)",
     "inputs": ["đường dẫn file có sẵn, nếu có"],
     "outputs": ["đường dẫn CỤ THỂ file sản phẩm, không dùng ký tự đại diện *"],
     "acceptance": ["tiêu chí kiểm được, lấy từ brief"],
     "depends_on": []}
  ]
}
Quy tắc:
- role chỉ là "software" (code, script, test) hoặc "media" (logo SVG, vector, xử lý ảnh, PDF bằng ArtCraft/Inkscape/ImageMagick).
- Ít task nhất có thể (job nhỏ: một task). Tối đa 8. Task nào cần kết quả của task khác thì ghi id đó vào depends_on. Không tạo vòng phụ thuộc.
- outputs là đường dẫn tương đối thư mục làm việc. Job thường: đặt sản phẩm cuối trong `deliverables/`. Job có thư mục project trên máy: đặt file đúng chỗ trong project.
- Mỗi task tự đủ thông tin: model con không thấy cuộc trò chuyện với chủ, chỉ biết nội dung task và brief.
- Nếu phần phía trên có phản hồi của chủ hoặc báo cáo lỗi, kế hoạch này CHỈ chứa các task mới hoặc task sửa cần làm thêm.
Sau khi ghi xong trả lời một dòng "ĐÃ LẬP KẾ HOẠCH".
