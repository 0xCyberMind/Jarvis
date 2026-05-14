from typing import Dict, List


class Planner:
    def create_plan(self, user_text: str) -> Dict[str, List[str]]:
        normalized = user_text.strip()
        if not normalized:
            return {"goal": "", "steps": []}

        separators = [" and then ", " then ", ",", ";"]
        steps = [normalized]
        for separator in separators:
            if separator in normalized.lower():
                parts = [p.strip() for p in normalized.split(separator) if p.strip()]
                if len(parts) > 1:
                    steps = parts
                    break

        return {"goal": normalized, "steps": steps}
