import asyncio
import sys
sys.path.insert(0, r'C:\Users\bhask\Desktop\jarvis-main\jarvis-main')
from agents.agent_manager import AgentManager
from agents.commander_agent import CommanderAgent

class R:
    capabilities = ['research.web']
    async def execute_task(self, task):
        return {'status': 'ok', 'results': [{'title': 'x'}]}

class Coder:
    capabilities = ['code.generate']
    async def execute_task(self, task):
        return {'status': 'ok', 'stats': {'files': 1}}

class Sec:
    capabilities = ['security.check']
    async def execute_task(self, task):
        return {'status': 'ok', 'approved': True}

async def main():
    mgr = AgentManager()
    r = R()
    c = Coder()
    s = Sec()
    mgr.register('research', r)
    mgr.register('coder', c)
    mgr.register('security', s)
    commander = CommanderAgent(mgr)
    mgr.register('commander', commander)
    out = await commander.execute_task({'op': 'intent', 'text': 'Build a landing page'})
    print('OUT:', out)

if __name__ == '__main__':
    asyncio.run(main())
