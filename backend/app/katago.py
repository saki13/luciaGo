"""Async wrapper around the KataGo analysis engine.

KataGo's ``analysis`` mode speaks newline-delimited JSON over stdin/stdout.
Each request carries an ``id``; each response echoes that ``id``. Multiple
positions may be in flight at once. This wrapper keeps the process alive,
writes requests, and resolves the matching :class:`asyncio.Future` per id.
"""

from __future__ import annotations

import asyncio
import json
import logging
import subprocess
import uuid
from typing import Any

logger = logging.getLogger("app.katago")


class KataGoEngine:
    def __init__(
        self,
        katago_bin: str,
        model_path: str,
        config_path: str,
        *,
        board_size: int = 19,
        komi: float = 7.5,
        rules: str = "chinese",
        default_visits: int = 300,
        default_pv_len: int = 10,
        cwd: str | None = None,
    ) -> None:
        self.cmd = [katago_bin, "analysis", "-model", model_path, "-config", config_path]
        self.cwd = cwd
        self.board_size = board_size
        self.komi = komi
        self.rules = rules
        self.default_visits = default_visits
        self.default_pv_len = default_pv_len

        self._proc: asyncio.subprocess.Process | None = None
        self._pending: dict[str, asyncio.Future[dict]] = {}
        self._stderr_tail: list[str] = []

    @property
    def running(self) -> bool:
        return self._proc is not None and self._proc.returncode is None

    async def start(self) -> None:
        if self.running:
            return
        self._proc = await asyncio.create_subprocess_exec(
            *self.cmd,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=self.cwd,
        )
        asyncio.create_task(self._read_stdout())
        asyncio.create_task(self._read_stderr())
        logger.info("KataGo analysis engine started (pid=%s)", self._proc.pid)

    async def stop(self) -> None:
        if not self.running:
            return
        assert self._proc is not None
        try:
            self._proc.terminate()
            await asyncio.wait_for(self._proc.wait(), timeout=10)
        except (asyncio.TimeoutError, ProcessLookupError):
            self._proc.kill()
        for fut in self._pending.values():
            if not fut.done():
                fut.set_exception(RuntimeError("KataGo engine stopped"))
        self._pending.clear()
        self._proc = None

    async def _read_stdout(self) -> None:
        assert self._proc is not None
        assert self._proc.stdout is not None
        while True:
            line = await self._proc.stdout.readline()
            if not line:
                break
            try:
                data = json.loads(line.decode("utf-8"))
            except (json.JSONDecodeError, UnicodeDecodeError):
                continue
            rid = data.get("id")
            if rid is None:
                continue
            fut = self._pending.pop(rid, None)
            if fut is not None and not fut.done():
                loot = data.get("isDuringSearch", False)
                # Keep waiting for the final report if a partial arrived first.
                if loot:
                    self._pending[rid] = fut
                    continue
                fut.set_result(data)

    async def _read_stderr(self) -> None:
        assert self._proc is not None
        assert self._proc.stderr is not None
        while True:
            line = await self._proc.stderr.readline()
            if not line:
                break
            text = line.decode("utf-8", errors="replace").rstrip()
            if text:
                self._stderr_tail.append(text)
                if len(self._stderr_tail) > 200:
                    self._stderr_tail.pop(0)
                logger.debug("katago stderr: %s", text)

    def stderr_tail(self) -> list[str]:
        return self._stderr_tail[-20:]

    async def analyze(
        self,
        *,
        moves: list[list[str]] | None = None,
        initial_stones: list[list[str]] | None = None,
        initial_player: str | None = None,
        board_size: int | None = None,
        komi: float | None = None,
        rules: str | None = None,
        max_visits: int | None = None,
        include_ownership: bool = True,
        include_ownership_stdev: bool = False,
        include_policy: bool = False,
        include_pv_visits: bool = True,
        analysis_pv_len: int | None = None,
        extra: dict[str, Any] | None = None,
    ) -> dict:
        if not self.running:
            raise RuntimeError("KataGo engine is not running")

        rid = uuid.uuid4().hex
        fut = asyncio.get_running_loop().create_future()
        self._pending[rid] = fut

        req: dict[str, Any] = {
            "id": rid,
            "boardXSize": board_size or self.board_size,
            "boardYSize": board_size or self.board_size,
            "komi": self.komi if komi is None else komi,
            "rules": self.rules if rules is None else rules,
            "maxVisits": self.default_visits if max_visits is None else max_visits,
            "includeOwnership": include_ownership,
            "includeOwnershipStdev": include_ownership_stdev,
            "includePolicy": include_policy,
            "includePVVisits": include_pv_visits,
            "analysisPVLen": self.default_pv_len if analysis_pv_len is None else analysis_pv_len,
        }
        if moves is not None:
            req["moves"] = moves
        else:
            req["moves"] = []
        if initial_stones is not None:
            req["initialStones"] = initial_stones
        if initial_player is not None:
            req["initialPlayer"] = initial_player
        if extra:
            req.update(extra)

        assert self._proc is not None
        assert self._proc.stdin is not None
        self._proc.stdin.write((json.dumps(req) + "\n").encode("utf-8"))
        await self._proc.stdin.drain()

        try:
            return await asyncio.wait_for(fut, timeout=180)
        finally:
            self._pending.pop(rid, None)

    async def health(self) -> dict:
        return {
            "running": self.running,
            "board_size": self.board_size,
            "komi": self.komi,
            "rules": self.rules,
            "default_visits": self.default_visits,
        }
