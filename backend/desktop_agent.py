import platform
from typing import Dict


class DesktopAgent:
    def system_info(self) -> Dict[str, str]:
        return {
            "platform": platform.system(),
            "release": platform.release(),
            "supported": "true" if platform.system().lower() == "windows" else "false",
        }

    def open_application(self, app_name: str) -> Dict[str, str]:
        if platform.system().lower() != "windows":
            return {"status": "unsupported", "message": "Desktop automation currently supports Windows only."}
        return {"status": "ok", "message": f"Requested application launch: {app_name}"}
