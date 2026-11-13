import sys


def run(argv: list[str] | None = None) -> None:
    """Mở giao diện. `--selftest kết_quả.json [tts]` kiểm tra bản đóng gói rồi thoát (dùng trong CI)."""
    argv = sys.argv[1:] if argv is None else argv
    if argv[:1] == ["--selftest"]:
        from video_studio.selftest import selftest

        sys.exit(selftest(argv[1] if len(argv) > 1 else "selftest.json", tts="tts" in argv[2:]))
    from video_studio.gui.main_window import main

    main()


if __name__ == "__main__":
    run()
