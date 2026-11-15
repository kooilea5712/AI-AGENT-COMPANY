"""Danh bạ nhân viên của studio: ai làm gì, dùng combo nào. Giao diện (trang Đội ngũ, sơ đồ tiến trình) đọc từ đây.
Nội dung mô tả rút từ docs/thiet-ke.md (mục Sơ đồ tổ chức)."""
from . import config

OWNER = "Chủ studio"
SYSTEM = "Hệ thống"

STAFF = [
    {"id": "owner", "name": OWNER, "title": "Chủ tịch (bạn)", "human": True, "active": True, "combo": None,
     "duties": ["Giao việc cho Giám đốc", "Duyệt brief trước khi làm (điểm dừng 1)", "Duyệt bàn giao trước khi gửi khách (điểm dừng 2)",
                "Trả lời khi Giám đốc hỏi lại", "Quyết định khi job bị dừng"], "tools": []},
    {"id": "director", "name": "Giám đốc điều phối", "title": "Giám đốc", "human": False, "active": True, "combo": "brain",
     "duties": ["Tiếp nhận yêu cầu, hỏi lại tối đa 3 câu nếu thiếu thông tin", "Viết brief.md với tiêu chí nghiệm thu kiểm được",
                "Lập kế hoạch plan.md và chọn người thực hiện", "Viết HANDOFF.md khi Kiểm định PASS", "Rút kinh nghiệm vào lessons.md"],
     "tools": ["đọc/ghi file trong thư mục job"]},
    {"id": "software", "name": "Kỹ sư phần mềm", "title": "Chuyên viên", "human": False, "active": True, "combo": "coder",
     "duties": ["Viết, chạy, test code và script", "Tự kiểm bằng cách chạy chương trình thật", "Kèm README và file khai báo thư viện",
                "Sửa lỗi theo báo cáo của Kiểm định (tối đa 2 vòng)"],
     "tools": ["shell trong Docker", "Python + Pillow", "đọc/ghi file"]},
    {"id": "media", "name": "Chuyên viên media", "title": "Chuyên viên", "human": False, "active": True, "combo": "coder + vision",
     "duties": ["Logo SVG, vector, xử lý ảnh bằng lệnh", "Xuất PNG xem trước và tự nhìn lại bằng model vision",
                "Đo kích thước, độ trong suốt bằng công cụ (không tin mắt model)"],
     "tools": ["Inkscape", "ImageMagick", "Pillow", "FFmpeg", "describe_image"]},
    {"id": "qa", "name": "Kiểm định", "title": "QA", "human": False, "active": True, "combo": "brain + vision",
     "duties": ["Đối chiếu từng tiêu chí nghiệm thu trong brief", "Tự chạy và đo sản phẩm, không tin báo cáo của người làm",
                "Trả PASS hoặc FAIL kèm bằng chứng và lỗi cụ thể"],
     "tools": ["shell trong Docker", "describe_image", "đọc file"]},
    # Vai theo thiết kế nhưng chưa dựng (hiện mờ trên giao diện)
    {"id": "game", "name": "Lập trình game", "title": "Chưa có", "human": False, "active": False, "combo": "coder",
     "duties": ["Prototype và game nhỏ (Godot hoặc HTML5)"], "tools": []},
    {"id": "video", "name": "Biên tập video", "title": "Chưa có", "human": False, "active": False, "combo": "coder + vision",
     "duties": ["Cắt ghép, phụ đề, xuất file bằng FFmpeg"], "tools": []},
    {"id": "audio", "name": "Âm thanh", "title": "Chưa có", "human": False, "active": False, "combo": "fast",
     "duties": ["Lồng tiếng, làm sạch, ghép nhạc"], "tools": []},
]
NAME_TO_ID = {s["name"]: s["id"] for s in STAFF}
NAME_TO_ID[SYSTEM] = "system"


def combo_models() -> dict:
    """Combo -> model Ollama thật ở chế độ direct (chế độ omniroute thì tên model thật do /health?deep báo)."""
    return dict(config.DIRECT_MODELS)
