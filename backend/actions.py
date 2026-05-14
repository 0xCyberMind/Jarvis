import os
import shlex
import subprocess
from typing import Any, Dict

from browser_agent import BrowserAgent
from desktop_agent import DesktopAgent
from research_engine import ResearchEngine
from task_manager import TaskManager


class ActionRouter:
    def __init__(self, memory_store: Any) -> None:
        self.memory = memory_store
        self.browser = BrowserAgent()
        self.desktop = DesktopAgent()
        self.research = ResearchEngine()
        self.tasks = TaskManager()
        self.allow_shell = os.getenv("ALLOW_SHELL_ACTIONS", "false").lower() == "true"

    async def execute(self, user_text: str) -> Dict[str, Any]:
        text = user_text.strip()
        lower = text.lower()

        if lower.startswith("remember "):
            value = text[9:].strip()
            mem_id = self.memory.add_memory(value, {"source": "user"})
            return {"type": "memory", "message": f"Stored memory #{mem_id}."}

        if lower.startswith("recall "):
            query = text[7:].strip()
            results = self.memory.search_memories(query)
            if not results:
                return {"type": "memory", "message": "No memory matches found."}
            summary = "\n".join(f"- {item['content']}" for item in results)
            return {"type": "memory", "message": f"I found:\n{summary}", "data": results}

        if lower.startswith("open ") and ("http" in lower or "." in text):
            url = text[5:].strip()
            result = await self.browser.open_url(url)
            return {"type": "browser", "message": result["message"], "data": result}

        if lower.startswith("research "):
            query = text[9:].strip()
            findings = await self.research.search(query)
            lines = [f"- {item['title']} ({item['url']})" for item in findings["results"] if item.get("title")]
            return {"type": "research", "message": "\n".join(lines) if lines else "No research results.", "data": findings}

        if lower.startswith("task "):
            title = text[5:].strip()
            task = self.tasks.create_task(title)
            return {"type": "task", "message": f"Task created: {task.title}", "data": {"id": task.id}}

        if lower == "list tasks":
            tasks = self.tasks.list_tasks()
            if not tasks:
                return {"type": "task", "message": "No tasks yet."}
            lines = [f"- [{item['status']}] {item['title']} ({item['id'][:8]})" for item in tasks]
            return {"type": "task", "message": "\n".join(lines), "data": tasks}

        if lower.startswith("run "):
            command = text[4:].strip()
            if not self.allow_shell:
                return {"type": "shell", "message": "Shell actions are disabled. Set ALLOW_SHELL_ACTIONS=true to enable."}
            if any(token in command for token in ["rm -rf", "shutdown", "format", "del /f"]):
                return {"type": "shell", "message": "Blocked potentially unsafe command."}
            try:
                proc = subprocess.run(shlex.split(command), capture_output=True, text=True, timeout=20, check=False)
                message = (proc.stdout or proc.stderr or "No output").strip()[:2000]
                return {"type": "shell", "message": message, "data": {"code": proc.returncode}}
            except Exception as exc:
                return {"type": "shell", "message": f"Command failed: {exc}"}

        if "system info" in lower:
            info = self.desktop.system_info()
            return {"type": "desktop", "message": f"Platform: {info['platform']} {info['release']}"}

        return {"type": "chat", "message": "I understood your request but no direct action matched. Ask me to remember, recall, research, open URL, or manage tasks."}
