import logging
from typing import Any, Dict, Optional
import difflib

from agents.base_agent import BaseAgent

log = logging.getLogger("jarvis.coding_agent")


class CodingAgent(BaseAgent):
    def __init__(self, manager: Any):
        super().__init__(manager, name="CodingAgent", capabilities=["code.generate", "code.review", "code.patch"])

    def _make_patch(self, orig: str, new: str) -> str:
        """Return a unified diff patch string."""
        orig_lines = orig.splitlines(keepends=True)
        new_lines = new.splitlines(keepends=True)
        diff = difflib.unified_diff(orig_lines, new_lines, fromfile="a/file", tofile="b/file")
        return "".join(diff)

    async def execute_task(self, task: Dict[str, Any]) -> Dict[str, Any]:
        op = task.get("op")
        if op == "patch_file":
            path = task.get("path")
            content = task.get("content")
            if not path or content is None:
                return {"status": "error", "reason": "missing path or content"}
            try:
                # read existing
                with open(path, "r", encoding="utf-8") as f:
                    orig = f.read()
                patch = self._make_patch(orig, content)
                return {"status": "ok", "patch": patch}
            except FileNotFoundError:
                # create new file patch
                patch = self._make_patch("", content)
                return {"status": "ok", "patch": patch}
            except Exception:
                log.exception("CodingAgent patch failed")
                return {"status": "error", "reason": "patch_failed"}

        if op == "analyze_repo":
            # lightweight analysis
            import os

            root = task.get("root") or "."
            stats = {"files": 0, "loc": 0}
            for dirpath, dirnames, filenames in os.walk(root):
                for fn in filenames:
                    if fn.endswith((".py", ".ts", ".js", ".json", ".md")):
                        stats["files"] += 1
                        try:
                            with open(os.path.join(dirpath, fn), "r", encoding="utf-8") as f:
                                stats["loc"] += sum(1 for _ in f)
                        except Exception:
                            pass
            return {"status": "ok", "stats": stats}

        return {"status": "unknown_op"}
