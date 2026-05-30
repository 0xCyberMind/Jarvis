import logging
from typing import Any, Dict

from agents.base_agent import BaseAgent

log = logging.getLogger("jarvis.device_agent")


class DeviceAgent(BaseAgent):
    def __init__(self, manager: Any):
        super().__init__(manager, name="DeviceAgent", capabilities=["device.action", "device.monitor"])
        try:
            import actions
            import monitor
            import tracking
            self._actions = actions
            self._monitor = monitor
            self._tracking = tracking
        except Exception:
            self._actions = None
            self._monitor = None
            self._tracking = None

    async def execute_task(self, task: Dict[str, Any]) -> Dict[str, Any]:
        op = task.get("op")
        if op == "run_action":
            name = task.get("name")
            args = task.get("args", {})
            try:
                if self._actions and hasattr(self._actions, "execute_action"):
                    res = self._actions.execute_action(name, **args)
                    return {"status": "ok", "result": res}
                return {"status": "error", "reason": "actions module not available"}
            except Exception:
                log.exception("Device action failed")
                return {"status": "error", "reason": "exception"}

        if op == "monitor":
            try:
                if self._monitor and hasattr(self._monitor, "snapshot"):
                    snap = self._monitor.snapshot()
                    return {"status": "ok", "snapshot": snap}
                return {"status": "ok", "snapshot": None}
            except Exception:
                log.exception("Monitor failed")
                return {"status": "error"}

        return {"status": "unknown_op"}
