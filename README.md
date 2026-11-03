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
- **Hội thoại nhiều nhân vật**: kịch bản dạng `Mèo: lời thoại`, mỗi nhân vật có giọng (giọng, tốc độ, cao độ), vị trí và khẩu hình riêng; ai nói thì miệng người đó cử động.
- **Tạo nhân vật ngay trong app** (nút "Tạo nhân vật…" ở tab Hoạt hình): người nét vẽ tay (bộ Notionists, CC0: 64 kiểu tóc, 25 kiểu áo, tay, kính, râu) hoặc con vật hoạt hình; tự tô màu, vẽ đủ 9 khẩu hình và mắt nhắm.
- Nhân vật thở nhẹ và nhún đầu khi nói (tắt được).
- Ảnh bìa YouTube (thumbnail) tự tạo từ cảnh đầu: tiêu đề chữ to + nhân vật.
- Lưu đệm giọng đọc trong `~/.video_studio/tts_cache`: câu không đổi thì không gọi Edge TTS lại (preview nhanh hơn).
- Tự hạ nhạc nền khi có lời đọc; xuất kèm file phụ đề `.srt` để tải lên YouTube; xuất thêm bản Shorts 9:16 cùng lúc với bản 16:9.
- **Nhân vật nói khớp miệng**: chọn thư mục nhân vật (thân + các hình miệng, xem `examples/nhan_vat_mau`), nhân vật đứng trong cảnh, miệng cử động theo giọng đọc và tự chớp mắt.
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

### Hội thoại

Chọn "Nhân vật nói" là một thư mục chứa nhiều thư mục con, mỗi thư mục con là một nhân vật (tên thư mục = tên trong kịch bản, xem `examples/dan_nhan_vat`). Giọng của từng nhân vật đặt trong `nhanvat.json`:

```json
{ "voice": "vi-VN-NamMinhNeural", "rate": "+5%", "pitch": "-10Hz", "volume": 1.0, "faces": "right" }
```

`faces` là hướng nhân vật đang nhìn trong hình vẽ; app tự lật hình để nhân vật quay vào giữa khung. Edge TTS chỉ có hai giọng tiếng Việt (Hoài My, Nam Minh), nên dùng `pitch` và `rate` để các nhân vật nghe khác nhau.

```text
[bo_song.png]
Ngày xửa ngày xưa, bên bờ sông có hai người bạn.
Mèo: Hôm nay mình đi câu cá nhé!
Chó: Được thôi,
nhưng nhớ mang theo bánh mì.

Kể: Thế là hai bạn lên đường.
```

Dòng không có tên nối tiếp lời của dòng trước; `Kể:` là lời người dẫn chuyện (giọng ở tab Voice). Trong mỗi cảnh chỉ những nhân vật có lời mới xuất hiện, xếp từ trái sang phải theo thứ tự nói.

Khi bật giọng AI, mỗi cảnh dài bằng lời đọc cộng thời gian nghỉ; khi tắt voice, mỗi cảnh dài theo "Giây/cảnh". Dùng 16:9 cho video YouTube thường, 9:16 cho Shorts.

## Tạo nhân vật

Tab Hoạt hình → "Tạo nhân vật…": chọn tên (tên này dùng trong kịch bản, ví dụ `Lan: Chào bạn!`), loài, màu da/lông, màu áo/bụng, màu tóc, giọng và cao độ.

- **Người (nét vẽ tay)**: nửa người, phong cách minh hoạ, ráp từ bộ [Notionists](https://heyzoish.gumroad.com/l/notionists) của Zoish (giấy phép CC0, dùng thương mại không cần ghi nguồn; lấy qua [DiceBear](https://www.dicebear.com)). Chọn kiểu tóc, áo, tay (cầm điện thoại, chỉ tay...), mắt, lông mày, mũi, kính, râu. Nhân vật nhìn nghiêng nên app tự lật để hai người quay vào nhau.
- **Mèo, chó, thỏ, gấu, người hoạt hình, quái vật**: app tự vẽ, toàn thân, chọn kiểu mắt và phụ kiện (nơ, kính, mũ, khăn). Khung bên phải xem trước nhân vật đang nói và chớp mắt; nút "Ngẫu nhiên" để thử nhanh.

"Lưu nhân vật" ghi vào `<thư mục dàn nhân vật>/<tên>/` đủ `body.png`, `mouth_X..H.png`, `blink.png` và `nhanvat.json`, rồi tự chọn thư mục đó làm "Nhân vật nói". Tạo vài nhân vật vào cùng một thư mục là có ngay dàn nhân vật cho hội thoại. Các file là PNG thường nên bạn có thể mở bằng phần mềm vẽ để chỉnh thêm.

Muốn nhân vật riêng hơn thì tự vẽ theo hướng dẫn bên dưới. Bộ Notionists vẽ miệng theo biểu cảm nên app chọn 9 kiểu môi gần nhất với 9 khẩu hình; khớp miệng không chính xác bằng hình tự vẽ riêng cho từng khẩu hình.

## Nhân vật nói khớp miệng

Khẩu hình miệng lấy theo một trong hai cách:

- **Theo độ to giọng đọc** (mặc định khi chưa có Rhubarb): không cần cài thêm, miệng đóng/mở theo âm lượng.
- **[Rhubarb Lip Sync](https://github.com/DanielSWolf/rhubarb-lip-sync)** (MIT): chính xác hơn, phân biệt được khẩu hình A–H. Tải bản cho hệ điều hành của bạn ở trang Releases, giải nén vào thư mục `rhubarb` cạnh app (hoặc đặt biến `VSTUDIO_RHUBARB`). App dùng bộ nhận dạng `phonetic` (không phụ thuộc ngôn ngữ) cho giọng tiếng Việt.

## Bản .exe cho Windows

Mỗi lần CI chạy, job `windows-exe` đóng gói app bằng PyInstaller, tự kiểm tra bản đóng gói (dựng thử một cảnh có giọng Edge TTS) rồi tải lên mục **Artifacts** của lượt chạy (tab Actions trên GitHub, giữ 30 ngày). Tải `VideoStudio-windows`, giải nén, chạy `VideoStudio.exe`. FFmpeg không đóng gói kèm: cài bằng winget hoặc chép vào `ffmpeg\bin` cạnh file .exe (xem `HUONG_DAN.txt`).

Tự đóng gói trên máy: `py -3 -m pip install -r requirements.txt pyinstaller` rồi `powershell -ExecutionPolicy Bypass -File packaging\build_windows.ps1`.

## Kiểm thử

```bash
pip install -r requirements-dev.txt
pytest
VSTUDIO_TEST_TTS=1 pytest -k "tts or voice"   # thêm test gọi Edge TTS thật, cần mạng
VSTUDIO_RHUBARB=đường/dẫn/rhubarb pytest -k rhubarb   # test khớp miệng bằng Rhubarb
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
| `video_studio/thumbnail.py` | Ảnh bìa YouTube |
| `video_studio/selftest.py` | Tự kiểm tra bản đóng gói (`VideoStudio.exe --selftest kq.json`) |
| `video_studio/character_maker.py` | Tạo nhân vật: vẽ thân, 9 khẩu hình, mắt nhắm bằng QPainter |
| `video_studio/notionists.py` | Ráp nhân vật nét vẽ tay từ `assets/notionists.json` (CC0, xuất bằng `tools/export_notionists.mjs`) |
| `video_studio/gui/character_dialog.py` | Cửa sổ "Tạo nhân vật" |
| `video_studio/lipsync.py` | Nhân vật nói khớp miệng: khẩu hình từ Rhubarb hoặc độ to, chớp mắt |
| `video_studio/gui/main_window.py` | Giao diện PySide6 |

## Lưu ý sử dụng

Chỉ dùng video, nhạc và hình ảnh bạn sở hữu hoặc có quyền sử dụng. Edge TTS là dịch vụ không chính thức của Microsoft, có thể thay đổi hoặc ngừng bất cứ lúc nào.
