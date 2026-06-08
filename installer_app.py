from __future__ import annotations

import ctypes
import shutil
import sys
from pathlib import Path


APP_NAME = "发票递交助手"


def message_box(text: str, title: str = APP_NAME, icon: int = 0x40) -> None:
    ctypes.windll.user32.MessageBoxW(None, text, title, 0x0 | icon)


def get_bundle_root() -> Path:
    if getattr(sys, "frozen", False):
        return Path(getattr(sys, "_MEIPASS")).resolve()
    return Path(__file__).resolve().parent


def create_shortcut(shortcut_path: Path, target_path: Path, working_directory: Path) -> None:
    import win32com.client

    shell = win32com.client.Dispatch("WScript.Shell")
    shortcut = shell.CreateShortcut(str(shortcut_path))
    shortcut.TargetPath = str(target_path)
    shortcut.WorkingDirectory = str(working_directory)
    shortcut.IconLocation = str(target_path)
    shortcut.Save()


def main() -> int:
    source_dir = get_bundle_root() / "payload" / APP_NAME
    if not source_dir.is_dir():
        message_box(f"安装文件不完整，缺少 {APP_NAME} 程序目录。", "安装失败", 0x10)
        return 1

    install_dir = Path.home() / "AppData" / "Local" / APP_NAME
    desktop_dir = Path.home() / "Desktop"
    start_menu_dir = Path.home() / "AppData" / "Roaming" / "Microsoft" / "Windows" / "Start Menu" / "Programs" / APP_NAME

    try:
        if install_dir.exists():
            shutil.rmtree(install_dir)
        shutil.copytree(source_dir, install_dir)

        exe_path = install_dir / f"{APP_NAME}.exe"
        if not exe_path.is_file():
            raise FileNotFoundError(f"未找到 {exe_path}")

        create_shortcut(desktop_dir / f"{APP_NAME}.lnk", exe_path, install_dir)
        start_menu_dir.mkdir(parents=True, exist_ok=True)
        create_shortcut(start_menu_dir / f"{APP_NAME}.lnk", exe_path, install_dir)
    except Exception as exc:
        message_box(f"安装失败：{exc}", "安装失败", 0x10)
        return 1

    message_box(f"{APP_NAME} 已安装完成。\n桌面快捷方式已创建。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
