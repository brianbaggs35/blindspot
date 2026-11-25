"""Keeps the running missions alive: one asyncio task for each, started when a mission starts or
resumes, picked up again after a restart, and stopped when the server stops."""

import asyncio
import uuid

from app.agents.engine import MissionEngine


class MissionSupervisor:
    def __init__(self, engine: MissionEngine) -> None:
        self.engine = engine
        self._tasks: dict[uuid.UUID, asyncio.Task[None]] = {}
        self._again: set[uuid.UUID] = set()

    def active(self, mission_id: uuid.UUID) -> bool:
        return mission_id in self._tasks

    async def start(self) -> None:
        """After a restart: interrupted steps are marked, and every mission that was running
        carries on."""
        for mission_id in await self.engine.recover():
            self.launch(mission_id)

    def launch(self, mission_id: uuid.UUID) -> None:
        """Run the mission, unless it is already running here. A launch that arrives while the
        mission is finishing makes it run once more, so a late approval is not lost."""
        if mission_id in self._tasks:
            self._again.add(mission_id)
            return
        task = asyncio.get_running_loop().create_task(self.engine.run(mission_id))
        self._tasks[mission_id] = task
        task.add_done_callback(lambda done: self._finished(mission_id, done))

    async def launch_after_response(self, mission_id: uuid.UUID) -> None:
        """`launch` for a background task of a request: those run plain functions in a thread, where
        there is no event loop, but a coroutine runs on the server's loop."""
        self.launch(mission_id)
        await asyncio.sleep(0)  # the mission takes its first turn before the request's work ends

    def _finished(self, mission_id: uuid.UUID, done: asyncio.Task[None]) -> None:
        del self._tasks[mission_id]
        if mission_id in self._again and not done.cancelled():
            self._again.discard(mission_id)
            self.launch(mission_id)

    async def stop(self) -> None:
        """Stop every mission where it is. A step that was running is marked interrupted when the
        server starts again."""
        self._again.clear()
        running = list(self._tasks.values())
        for task in running:
            task.cancel()
        await asyncio.gather(*running, return_exceptions=True)
