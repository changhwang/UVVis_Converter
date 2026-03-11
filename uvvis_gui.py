def main() -> None:
    try:
        from uvvis_app.gui.main_window import main as gui_main
    except ImportError as exc:
        raise SystemExit(
            "PySide6 is required for the desktop app. Install requirements first, then rerun.\n"
            f"Import error: {exc}"
        )
    gui_main()


if __name__ == "__main__":
    main()
