import asyncio
from pathlib import Path

from actions import create_text_file, make_folder, write_text_file
from server import detect_action_fast


def test_create_text_file_writes_content(tmp_path):
    target = tmp_path / "notes" / "demo.txt"
    result = asyncio.run(create_text_file(str(target), "hello world"))
    assert result["success"] is True
    assert target.exists()
    assert target.read_text(encoding="utf-8") == "hello world"


def test_write_text_file_overwrites_content(tmp_path):
    target = tmp_path / "demo.txt"
    target.write_text("old", encoding="utf-8")
    result = asyncio.run(write_text_file(str(target), "new content"))
    assert result["success"] is True
    assert target.read_text(encoding="utf-8") == "new content"


def test_make_folder_creates_directory(tmp_path):
    folder = tmp_path / "new-folder"
    result = asyncio.run(make_folder(str(folder)))
    assert result["success"] is True
    assert folder.exists() and folder.is_dir()


def test_detect_action_fast_routes_file_operations():
    assert detect_action_fast("create file test.txt")["action"] == "create_file"
    assert detect_action_fast("create folder docs")["action"] == "create_folder"
    assert detect_action_fast("write file test.txt")["action"] == "write_file"
    assert detect_action_fast("edit file test.txt")["action"] == "edit_file"


def test_detect_action_fast_routes_settings_variants():
    assert detect_action_fast("open settings")["action"] == "open_settings"
    assert detect_action_fast("settings kholo")["action"] == "open_settings"
    assert detect_action_fast("setting open karo")["action"] == "open_settings"
    assert detect_action_fast("open setings")["action"] == "open_settings"


def test_detect_action_fast_routes_hinglish_device_commands():
    assert detect_action_fast("wifi check kar")["action"] == "network_status"
    whatsapp = detect_action_fast("whatsapp kholo")
    assert whatsapp["action"] == "open_app"
    assert whatsapp["target"] == "whatsapp"
    browser = detect_action_fast("browser kholo")
    assert browser["action"] == "open_app"
    assert browser["target"] == "chrome"


def test_detect_action_fast_routes_single_word_apps():
    cases = {
        "WhatsApp": ("open_app", "whatsapp"),
        "Chrome": ("open_app", "chrome"),
        "Browser": ("open_app", "chrome"),
        "Edge": ("open_app", "edge"),
        "Calculator": ("open_app", "calculator"),
        "Notepad": ("open_app", "notepad"),
    }
    for text, (expected_action, expected_target) in cases.items():
        action = detect_action_fast(text)
        assert action["action"] == expected_action
        assert action["target"] == expected_target
        assert action["confidence"] >= 0.8


def test_detect_action_fast_routes_special_single_word_apps():
    assert detect_action_fast("Settings")["action"] == "open_settings"
    assert detect_action_fast("Explorer")["action"] == "open_file_explorer"
    assert detect_action_fast("File Explorer")["action"] == "open_file_explorer"


def test_detect_action_fast_routes_open_app_aliases_and_typos():
    cases = {
        "open WhatsApp": ("open_app", "whatsapp"),
        "open whatsap": ("open_app", "whatsapp"),
        "open Chrome": ("open_app", "chrome"),
        "open Edge": ("open_app", "edge"),
        "calculator kholo": ("open_app", "calculator"),
        "notpad kholo": ("open_app", "notepad"),
    }
    for text, (expected_action, expected_target) in cases.items():
        action = detect_action_fast(text)
        assert action["action"] == expected_action
        assert action["target"] == expected_target


def test_detect_action_fast_routes_switch_to_app():
    action = detect_action_fast("switch to WhatsApp")
    assert action["action"] == "switch_app"
    assert action["target"] == "whatsapp"


def test_detect_action_fast_routes_window_commands():
    assert detect_action_fast("minimize window")["action"] == "minimize_window"
    assert detect_action_fast("maximize window")["action"] == "maximize_window"
    assert detect_action_fast("window minimize karo")["action"] == "minimize_window"
    assert detect_action_fast("window maximize karo")["action"] == "maximize_window"


def test_detect_action_fast_routes_wifi_commands():
    assert detect_action_fast("WiFi")["action"] == "network_status"
    assert detect_action_fast("WiFi check")["action"] == "network_status"
