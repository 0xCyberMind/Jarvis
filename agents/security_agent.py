import logging
from typing import Any, Dict

from agents.base_agent import BaseAgent

log = logging.getLogger("jarvis.security_agent")


class SecurityAgent(BaseAgent):
    def __init__(self, manager: Any):
        super().__init__(manager, name="SecurityAgent", capabilities=["security.check", "security.audit"])
        try:
            import security
            self._sec = security
        except Exception:
            self._sec = None

    async def execute_task(self, task: Dict[str, Any]) -> Dict[str, Any]:
        op = task.get("op")
        if op == "approve_action":
            action = task.get("action")
            context = task.get("context", {})
            try:
                if self._sec and hasattr(self._sec, "approve_action"):
                    ok = self._sec.approve_action(action, context)
                    return {"status": "ok", "approved": bool(ok)}
                # default conservative deny
                return {"status": "ok", "approved": False}
            except Exception:
                log.exception("Security approval failed")
                return {"status": "error", "approved": False}

        if op == "audit":
            entry = task.get("entry")
            try:
                if self._sec and hasattr(self._sec, "audit"):
                    self._sec.audit(entry)
                    return {"status": "ok"}
                return {"status": "ok"}
            except Exception:
                log.exception("Audit failed")
                return {"status": "error"}

        return {"status": "unknown_op"}
