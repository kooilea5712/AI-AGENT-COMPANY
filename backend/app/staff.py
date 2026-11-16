"""Danh bạ nhân viên của studio: ai làm gì, dùng vai LLM nào. Giao diện (trang Đội ngũ, sơ đồ tiến trình) đọc từ đây.
Nội dung mô tả rút từ docs/thiet-ke.md (mục Sơ đồ tổ chức) và từ luồng mới: chủ chỉ làm việc với Giám đốc."""
from . import settings

OWNER = "Chủ studio"
SYSTEM = "Hệ thống"
DIRECTOR = "Giám đốc điều phối"
QA_AUTHOR = "Kiểm định"
QA_RUNNER = "Kiểm thử viên"

STAFF = [
    {"id": "owner", "name": OWNER, "title": "Chủ tịch (bạn)", "human": True, "active": True, "role": None,
     "duties": ["Chỉ làm việc với Giám đốc: giao việc, trả lời khi Giám đốc hỏi, nhắn thêm yêu cầu hoặc file đính kèm bất cứ lúc nào",
                "Xem kết quả cuối: chấp nhận, hoặc chỉ ra lỗi để Giám đốc cho làm tiếp", "Quyết định khi job bị dừng"], "tools": []},
    {"id": "director", "name": DIRECTOR, "title": "Giám đốc", "human": False, "active": True, "role": "director",
     "duties": ["Tiếp nhận yêu cầu, hỏi lại tối đa 3 câu nếu thiếu thông tin quyết định", "Viết brief và TỰ CHỐT DUYỆT brief",
                "Chia việc thành các task giao cho model con (plan.json), chọn đúng vai cho từng task",
                "Viết HANDOFF.md khi Kiểm định PASS, rút kinh nghiệm vào lessons.md"], "tools": ["đọc/ghi file", "đọc project trên máy"]},
    {"id": "software", "name": "Kỹ sư phần mềm", "title": "Model con", "human": False, "active": True, "role": "engineer",
     "duties": ["Viết, chạy, test code và script theo task Giám đốc giao", "Tự kiểm bằng cách chạy chương trình thật",
                "Kèm README và file khai báo thư viện", "Sửa lỗi theo báo cáo của Kiểm thử (tối đa 2 vòng/đợt)"],
     "tools": ["shell trong Docker", "Python + Pillow", "đọc/ghi file"]},
    {"id": "media", "name": "Chuyên viên media", "title": "Model con", "human": False, "active": True, "role": "media",
     "duties": ["Logo, vector, PDF bằng ArtCraft (VectorCraft, PdfCraft) và Inkscape/ImageMagick", "Xuất PNG xem trước và tự nhìn lại bằng model vision",
                "Đo kích thước, độ trong suốt bằng công cụ (không tin mắt model)"],
     "tools": ["ArtCraft: vectorcraft-cli", "ArtCraft: pdfcraft-cli", "Inkscape", "ImageMagick", "describe_image"]},
    {"id": "qa", "name": QA_AUTHOR, "title": "Thiết kế testcase", "human": False, "active": True, "role": "qa_author",
     "duties": ["Đọc brief và sản phẩm, viết bộ testcase phủ mọi tiêu chí nghiệm thu", "Mỗi testcase có kết quả mong đợi đo được bằng máy",
                "Không sửa sản phẩm, không thêm yêu cầu ngoài brief"], "tools": ["đọc file", "chạy thử trên bản sao"]},
    {"id": "tester", "name": QA_RUNNER, "title": "Chạy testcase", "human": False, "active": True, "role": "qa_runner",
     "duties": ["Chạy HẾT testcase, ghi PASS/FAIL kèm bằng chứng thật", "Hệ thống chạy lại độc lập các case đo được bằng máy để chống ghi sai"],
     "tools": ["shell trong Docker (bản sao dùng một lần)", "describe_image"]},
    # Vai theo thiết kế nhưng chưa dựng (hiện mờ trên giao diện)
    {"id": "game", "name": "Lập trình game", "title": "Chưa có", "human": False, "active": False, "role": None,
     "duties": ["Prototype và game nhỏ (Godot hoặc HTML5)"], "tools": []},
    {"id": "video", "name": "Biên tập video", "title": "Chưa có", "human": False, "active": False, "role": None,
     "duties": ["Cắt ghép, phụ đề, xuất file bằng FFmpeg"], "tools": []},
    {"id": "audio", "name": "Âm thanh", "title": "Chưa có", "human": False, "active": False, "role": None,
     "duties": ["Lồng tiếng, làm sạch, ghép nhạc"], "tools": []},
]
NAME_TO_ID = {s["name"]: s["id"] for s in STAFF}
NAME_TO_ID[SYSTEM] = "system"


def model_chain(role: str | None) -> list[str]:
    """Chuỗi model của một vai theo cài đặt hiện tại, ví dụ ['anthropic/claude-opus-5-5', 'omniroute/brain']."""
    if not role:
        return []
    return [f"{c['connection']}/{c['model']}" + (f" (bỏ qua: {c['skip']})" if c["skip"] else "") for c in settings.candidates(role)]
