# Video Studio

App desktop (Python + PySide6 + FFmpeg) dựng video ngắn giới thiệu sản phẩm từ **footage của bạn** hoặc footage có giấy phép.

## Tính năng (v0.2)

- Nhập nhiều video hoặc cả thư mục.
- Cắt ghép tự động: chọn đoạn dài ngẫu nhiên trong khoảng min/max, xáo trộn thứ tự, ghép thành video 9:16, 16:9 hoặc 1:1 (cắt lấp đầy khung hoặc thêm viền).
- Tiêu đề sản phẩm và phụ đề tiếng Việt (vẽ bằng libass, chỉnh font, cỡ chữ, màu, vị trí).
- Giọng đọc AI bằng Edge TTS (Hoài My, Nam Minh). Phụ đề lấy mốc thời gian từng từ của giọng đọc, độ dài video bám theo lời đọc. Lỗi mạng được thử lại và báo rõ ràng.
- Hoặc dùng file giọng tự thu (mp3, m4a, wav): độ dài video theo file, phụ đề chia đều lời thoại theo thời gian.
- Trộn âm thanh gốc, voice và nhạc nền với âm lượng riêng.
- **Hoạt hình theo cảnh** (tab Hoạt hình): viết kịch bản, mỗi đoạn là một cảnh gắn một ảnh (nhân vật/bối cảnh bạn tự vẽ hoặc có quyền dùng). App đọc lời từng cảnh, cho ảnh chuyển động (zoom, lia), mờ chuyển cảnh, thêm phụ đề, tiêu đề, nhạc nền.
- Preset lưu thành JSON trong `~/.video_studio/presets`.
- Xuất hàng loạt N phiên bản (mỗi bản một cách cắt khác), có nút dừng và preview nhanh độ phân giải thấp.

## Cài đặt

1. Cài Python 3.10+ và FFmpeg. Trên Windows: `winget install Gyan.FFmpeg`, rồi mở lại cửa sổ lệnh.
   App tìm FFmpeg theo thứ tự: biến môi trường `VSTUDIO_FFMPEG_DIR`, thư mục `ffmpeg\bin` cạnh app, lối tắt của winget (`%LOCALAPPDATA%\Microsoft\WinGet\Links`), rồi PATH.
2. Windows: chạy `run_windows.bat` (tự tạo môi trường ảo, cài thư viện lần đầu và khi `requirements.txt` thay đổi).
3. Hoặc chạy tay:

```bash
python -m venv .venv
.venv/bin/pip install -r requirements.txt   # Windows: .venv\Scripts\pip
.venv/bin/python -m video_studio
```

## Kịch bản hoạt hình

Các cảnh cách nhau bởi một dòng trống. Dòng đầu của cảnh có thể là `[tên_ảnh.png]` (tính theo thư mục ảnh). Cảnh không ghi ảnh dùng ảnh tiếp theo trong thư mục (sắp theo tên), hết ảnh thì dùng lại ảnh của cảnh trước.

```text
[01_meo_ngu.png]
Ngày xửa ngày xưa, có một chú mèo lười.

Một hôm, chú quyết định đi câu cá.
```

Khi bật giọng AI, mỗi cảnh dài bằng lời đọc cộng thời gian nghỉ; khi tắt voice, mỗi cảnh dài theo "Giây/cảnh". Dùng 16:9 cho video YouTube thường, 9:16 cho Shorts.

## Kiểm thử

```bash
pip install -r requirements-dev.txt
pytest
VSTUDIO_TEST_TTS=1 pytest -k "tts or voice"   # thêm test gọi Edge TTS thật, cần mạng
```

GitHub Actions (`.github/workflows/tests.yml`) chạy toàn bộ test trên Windows và Ubuntu, gồm cả test Edge TTS thật và test kiểm tra tiêu đề tiếng Việt thực sự được vẽ lên khung hình.

## Cấu trúc

| File | Vai trò |
|---|---|
| `video_studio/settings.py` | Cài đặt dạng dataclass, lưu/đọc preset |
| `video_studio/planner.py` | Chọn đoạn cắt từ các clip |
| `video_studio/captions.py` | Tạo file ASS cho tiêu đề và phụ đề |
| `video_studio/voice.py` | Edge TTS + mốc thời gian từng từ |
| `video_studio/pipeline.py` | Gọi FFmpeg: cắt, nối, chèn chữ, trộn âm, xuất hàng loạt |
| `video_studio/scenes.py` | Hoạt hình theo cảnh: đọc kịch bản, ảnh chuyển động, ghép cảnh |
| `video_studio/gui/main_window.py` | Giao diện PySide6 |

## Lưu ý sử dụng

Chỉ dùng video, nhạc và hình ảnh bạn sở hữu hoặc có quyền sử dụng. Edge TTS là dịch vụ không chính thức của Microsoft, có thể thay đổi hoặc ngừng bất cứ lúc nào.
