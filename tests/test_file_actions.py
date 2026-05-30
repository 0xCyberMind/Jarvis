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
