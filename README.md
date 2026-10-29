# Video Studio

App desktop (Python + PySide6 + FFmpeg) dựng video ngắn giới thiệu sản phẩm từ **footage của bạn** hoặc footage có giấy phép.

## Tính năng (v0.1)

- Nhập nhiều video hoặc cả thư mục.
- Cắt ghép tự động: chọn đoạn dài ngẫu nhiên trong khoảng min/max, xáo trộn thứ tự, ghép thành video 9:16, 16:9 hoặc 1:1 (cắt lấp đầy khung hoặc thêm viền).
- Tiêu đề sản phẩm và phụ đề tiếng Việt (vẽ bằng libass, chỉnh font, cỡ chữ, màu, vị trí).
- Giọng đọc AI bằng Edge TTS (Hoài My, Nam Minh). Phụ đề lấy mốc thời gian từng từ của giọng đọc, độ dài video bám theo lời đọc.
- Trộn âm thanh gốc, voice và nhạc nền với âm lượng riêng.
- Preset lưu thành JSON trong `~/.video_studio/presets`.
- Xuất hàng loạt N phiên bản (mỗi bản một cách cắt khác), có nút dừng và preview nhanh độ phân giải thấp.

## Cài đặt

1. Cài Python 3.10+ và FFmpeg (có `ffmpeg`, `ffprobe` trong PATH). Trên Windows: `winget install Gyan.FFmpeg`.
2. Windows: chạy `run_windows.bat` (tự tạo môi trường ảo và cài thư viện lần đầu).
3. Hoặc chạy tay:

```bash
python -m venv .venv
.venv/bin/pip install -r requirements.txt   # Windows: .venv\Scripts\pip
.venv/bin/python -m video_studio
```

## Kiểm thử

```bash
pip install -r requirements-dev.txt
pytest
VSTUDIO_TEST_TTS=1 pytest -k voice   # thêm test gọi Edge TTS thật, cần mạng
```

## Cấu trúc

| File | Vai trò |
|---|---|
| `video_studio/settings.py` | Cài đặt dạng dataclass, lưu/đọc preset |
| `video_studio/planner.py` | Chọn đoạn cắt từ các clip |
| `video_studio/captions.py` | Tạo file ASS cho tiêu đề và phụ đề |
| `video_studio/voice.py` | Edge TTS + mốc thời gian từng từ |
| `video_studio/pipeline.py` | Gọi FFmpeg: cắt, nối, chèn chữ, trộn âm, xuất hàng loạt |
| `video_studio/gui/main_window.py` | Giao diện PySide6 |

## Lưu ý sử dụng

Chỉ dùng video, nhạc và hình ảnh bạn sở hữu hoặc có quyền sử dụng. Edge TTS là dịch vụ không chính thức của Microsoft, có thể thay đổi hoặc ngừng bất cứ lúc nào.
