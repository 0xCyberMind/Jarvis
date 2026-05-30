import logging
from typing import Any, Dict

from agents.base_agent import BaseAgent

log = logging.getLogger("jarvis.vision_agent")


class VisionAgent(BaseAgent):
    def __init__(self, manager: Any):
        super().__init__(manager, name="VisionAgent", capabilities=["vision.ocr", "vision.screen"])
        try:
            import screen

            self._screen = screen
        except Exception:
            self._screen = None

    async def execute_task(self, task: Dict[str, Any]) -> Dict[str, Any]:
        op = task.get("op")
        if op == "capture":
            try:
                if self._screen and hasattr(self._screen, "capture"):
                    img = self._screen.capture()
                    return {"status": "ok", "image": img}
                return {"status": "ok", "image": None}
            except Exception:
                log.exception("Vision capture failed")
                return {"status": "error"}

        if op == "ocr":
            try:
                text = None
                if self._screen and hasattr(self._screen, "ocr"):
                    text = self._screen.ocr()
                return {"status": "ok", "text": text}
            except Exception:
                log.exception("Vision OCR failed")
                return {"status": "error"}

        return {"status": "unknown_op"}
