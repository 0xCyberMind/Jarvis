from typing import Dict


class BrowserAgent:
    async def open_url(self, url: str) -> Dict[str, str]:
        if not url.startswith(("http://", "https://")):
            url = f"https://{url}"
        return {"status": "ok", "message": f"Browser action prepared for: {url}", "url": url}
