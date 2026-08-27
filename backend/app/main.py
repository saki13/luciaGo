"""FastAPI backend for luciaGo.

Exposes the KataGo analysis engine as a REST API. Coordinates use GTP format
(e.g. ``"D4"``, ``"Q16"``), the same convention KataGo speaks natively.
"""

from __future__ import annotations

import os
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Literal

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from .katago import KataGoEngine
from .tsumego import Tsumego

BACKEND_DIR = Path(__file__).resolve().parent.parent

KATAGO_BIN = os.environ.get(
    "KATAGO_BIN", str(BACKEND_DIR / "engine" / "kataGo" / "katago.exe")
)
KATAGO_MODEL = os.environ.get(
    "KATAGO_MODEL", str(BACKEND_DIR / "engine" / "models" / "b6c96.txt.gz")
)
KATAGO_CONFIG = os.environ.get(
    "KATAGO_CONFIG", str(BACKEND_DIR / "engine" / "analysis.cfg")
)
BOARD_SIZE = int(os.environ.get("BOARD_SIZE", "19"))
KOMI = float(os.environ.get("KOMI", "7.5"))
RULES = os.environ.get("RULES", "chinese")


engine = KataGoEngine(
    katago_bin=KATAGO_BIN,
    model_path=KATAGO_MODEL,
    config_path=KATAGO_CONFIG,
    board_size=BOARD_SIZE,
    komi=KOMI,
    rules=RULES,
    default_visits=int(os.environ.get("MAX_VISITS", "300")),
    cwd=str(BACKEND_DIR),
)

tsumego = Tsumego(engine, size=BOARD_SIZE, komi=KOMI, rules=RULES)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Ensure KataGo's log directory exists (logDir is relative to the engine cwd).
    log_dir = BACKEND_DIR / "kataGo" / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    try:
        await engine.start()
    except Exception:  # noqa: BLE001
        # Report the error through /api/health rather than crashing the server.
        pass
    yield
    await engine.stop()


app = FastAPI(title="luciaGo API", version="0.1.0", lifespan=lifespan)

# Allow the Vite dev server (and any local origin) to call the API.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


class AnalyzeRequest(BaseModel):
    # stones / moves use KataGo's native array format: [[color, vertex], ...]
    stones: list[list[str]] = Field(default_factory=list)
    moves: list[list[str]] = Field(default_factory=list)
    toPlay: Literal["B", "W"] = "B"
    boardSize: int = Field(default_factory=lambda: BOARD_SIZE, ge=9, le=25)
    komi: float | None = None
    rules: str | None = None
    maxVisits: int | None = Field(default=None, ge=1)
    includeOwnership: bool = True
    # Optional region (GTP vertices) to constrain the side-to-move when solving
    # life-and-death problems (KataGo allowMoves), preventing it from tenuki.
    region: list[str] = Field(default_factory=list)

    @staticmethod
    def _check_pairs(pairs: list[list[str]]):
        for p in pairs:
            if len(p) != 2 or p[0] not in ("B", "W"):
                raise ValueError(f"expected [color, vertex] pair, got {p!r}")

    def check(self):
        self._check_pairs(self.stones)
        self._check_pairs(self.moves)


class AnalyzeResponse(BaseModel):
    boardSize: int
    toPlay: str
    rootInfo: dict | None = None
    moveInfos: list[dict] = Field(default_factory=list)
    ownership: list[float] | None = None
    ownershipStdev: list[float] | None = None
    turnNumber: int | None = None


@app.get("/api/health")
async def health():
    h = await engine.health()
    h["engine"] = {
        "binary": KATAGO_BIN,
        "model": KATAGO_MODEL,
        "config": KATAGO_CONFIG,
    }
    if not h["running"]:
        h["stderr_tail"] = engine.stderr_tail()
    return h


@app.post("/api/analyze", response_model=AnalyzeResponse)
async def analyze(req: AnalyzeRequest):
    if not engine.running:
        raise HTTPException(status_code=503, detail="KataGo engine is not running")

    req.check()

    kwargs: dict = {}
    if req.moves:
        kwargs["moves"] = req.moves
    else:
        kwargs["initial_stones"] = req.stones
        kwargs["initial_player"] = req.toPlay

    extra: dict = {}
    if req.region:
        # Constrain the side to move to the problem region (prevents tenuki).
        extra["allowMoves"] = [
            {"player": req.toPlay, "moves": req.region, "untilDepth": 1000}
        ]

    result = await engine.analyze(
        board_size=req.boardSize,
        komi=req.komi,
        rules=req.rules,
        max_visits=req.maxVisits,
        include_ownership=req.includeOwnership,
        extra=extra,
        **kwargs,
    )

    if "error" in result:
        raise HTTPException(status_code=400, detail=result["error"])

    return AnalyzeResponse(
        boardSize=req.boardSize,
        toPlay=result.get("rootInfo", {}).get("currentPlayer", req.toPlay),
        rootInfo=result.get("rootInfo"),
        moveInfos=result.get("moveInfos", []),
        ownership=result.get("ownership"),
        ownershipStdev=result.get("ownershipStdev"),
        turnNumber=result.get("turnNumber"),
    )


@app.get("/")
async def root():
    return {"app": "luciaGo", "status": "ok", "docs": "/docs"}


class TsumegoRequest(BaseModel):
    stones: list[list[str]] = Field(default_factory=list)
    region: list[str] = Field(default_factory=list)
    targetVertex: str
    sideToMove: Literal["B", "W"] = "B"
    goal: Literal["live", "kill"] = "live"
    attemptVertex: str | None = None
    boardSize: int | None = None
    maxVisits: int | None = Field(default=None, ge=1)


@app.post("/api/tsumego/solve")
async def tsumego_solve(req: TsumegoRequest):
    if not engine.running:
        raise HTTPException(status_code=503, detail="KataGo engine is not running")
    res = await tsumego.solve(
        req.stones,
        req.region,
        req.targetVertex,
        req.sideToMove,
        goal=req.goal,
        visits=req.maxVisits or 400,
    )
    if "error" in res:
        raise HTTPException(status_code=400, detail=res["error"])
    return res


@app.post("/api/tsumego/evaluate")
async def tsumego_evaluate(req: TsumegoRequest):
    if not engine.running:
        raise HTTPException(status_code=503, detail="KataGo engine is not running")
    if not req.attemptVertex:
        raise HTTPException(status_code=400, detail="attemptVertex is required")
    res = await tsumego.solve(
        req.stones,
        req.region,
        req.targetVertex,
        req.sideToMove,
        goal=req.goal,
        first_move=req.attemptVertex,
        visits=req.maxVisits or 300,
    )
    if "error" in res:
        raise HTTPException(status_code=400, detail=res["error"])
    res["attempt"] = req.attemptVertex
    return res

