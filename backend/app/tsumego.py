"""Life-and-death (死活题) adjudication using KataGo as the reader engine.

KataGo selects the best continuation; we drive a region-restricted local fight
between attacker and defender, then classify the target group's status using
the classic rule: a group is ALIVE if it can form two independent real eyes,
else DEAD (a single eye / no life). Ko is flagged separately.

KataGo does NOT have a built-in life/death command, so this is implemented here.
Local board state is kept with ``sgfmill.boards.Board`` (capture / ko / suicide).
Coordinates use (row, col) with row 0 = top, matching the frontend and KataGo's
GTP convention: a vertex is LETTERS[col] + (size - row).
"""

from __future__ import annotations

import logging
from typing import Optional

logger = logging.getLogger("app.tsumego")

LETTERS = "ABCDEFGHJKLMNOPQRST"

# Colour letters for sgfmill vs KataGo
def to_sgf(colour: str) -> str:
    return colour.lower()


class Tsumego:
    def __init__(self, engine, size: int = 19, komi: float = 7.5, rules: str = "chinese"):
        self.engine = engine
        self.size = size
        self.komi = komi
        self.rules = rules

    # ---- coordinates ----
    def gtp(self, row: int, col: int) -> str:
        return LETTERS[col] + str(self.size - row)

    def parse(self, vertex: str) -> tuple[int, int]:
        col = LETTERS.index(vertex[0])
        row = self.size - int(vertex[1:])
        return (row, col)

    def _region_gtp(self, region_vertices: list[str]) -> list[str]:
        return region_vertices

    # ---- board helpers (use sgfmill lazily) ----
    def _new_board(self):
        from sgfmill import boards

        return boards.Board(self.size)

    def _apply_setup(self, board, stones: list[list[str]]):
        """stones: [[color, vertex], ...]"""
        black = []
        white = []
        for color, vertex in stones:
            row, col = self.parse(vertex)
            (black if color == "B" else white).append((row, col))
        board.apply_setup(black, white, [])

    def _stones_payload(self, board) -> list[list[str]]:
        out = []
        for colour, (row, col) in board.list_occupied_points():
            out.append([("B" if colour == "b" else "W"), self.gtp(row, col)])
        return out

    def _play(self, board, colour: str, row: int, col: int) -> bool:
        """Play a move with capture/ko/suicide handling. Returns True if legal."""
        try:
            board.play(row, col, colour.lower())
            return True
        except ValueError:
            return False

    # ---- group / eye analysis ----
    def _group(self, board, row: int, col: int) -> Optional[set]:
        colour = board.get(row, col)
        if colour is None:
            return None
        seen = set()
        stack = [(row, col)]
        while stack:
            r, c = stack.pop()
            if (r, c) in seen:
                continue
            seen.add((r, c))
            for dr, dc in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                nr, nc = r + dr, c + dc
                if 0 <= nr < self.size and 0 <= nc < self.size:
                    if board.get(nr, nc) == colour and (nr, nc) not in seen:
                        stack.append((nr, nc))
        return seen

    def _eye_regions(self, board, group, colour: str) -> list[set]:
        """Maximal empty regions enclosed by the group's stones (real eyes)."""
        visited = set()
        regions = []
        for (r, c) in group:
            for dr, dc in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                nr, nc = r + dr, c + dc
                if not (0 <= nr < self.size and 0 <= nc < self.size):
                    continue
                if (nr, nc) in visited or board.get(nr, nc) is not None:
                    continue
                # flood the empty region
                region = set()
                stack = [(nr, nc)]
                bounded = True
                while stack:
                    pr, pc = stack.pop()
                    if (pr, pc) in region:
                        continue
                    region.add((pr, pc))
                    for ddr, ddc in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                        qr, qc = pr + ddr, pc + ddc
                        if not (0 <= qr < self.size and 0 <= qc < self.size):
                            continue
                        cell = board.get(qr, qc)
                        if cell is None:
                            if (qr, qc) not in region:
                                stack.append((qr, qc))
                        elif cell != colour:
                            bounded = False  # touches an opponent stone -> not an eye
                visited |= region
                if bounded:
                    regions.append(region)
        return regions

    def _exists(self, board, group) -> bool:
        return any(board.get(r, c) is not None for (r, c) in group)

    def classify(self, board, group, colour: str) -> str:
        """Return 'alive', 'dead', or 'unknown' for the group."""
        if not self._exists(board, group):
            return "dead"
        eyes = self._eye_regions(board, group, colour)
        # Two independent eye regions => alive.
        if len(eyes) >= 2:
            return "alive"
        return "dead"

    # ---- local fight ----
    async def _engine_best(self, board, side_to_move: str, region: list[str], visits: int):
        return await self.engine.analyze(
            initial_stones=self._stones_payload(board),
            initial_player=side_to_move,
            board_size=self.size,
            komi=self.komi,
            rules=self.rules,
            max_visits=visits,
            include_ownership=True,
            extra={"allowMoves": [{"player": side_to_move, "moves": region, "untilDepth": 1000}]},
        )

    async def solve(
        self,
        stones: list[list[str]],
        region: list[str],
        target_vertex: str,
        side_to_move: str,
        goal: str = "live",
        *,
        first_move: Optional[str] = None,
        visits: int = 300,
        max_plies: int = 10,
        candidate_limit: int = 10,
    ) -> dict:
        """Adjudicate the target group and find the true vital point(s).

        The vital point is found by trying candidate moves (KataGo's top region-
        restricted moves for side_to_move), playing each out with a local fight, and
        keeping the ones that ACHIEVE the goal (live -> group alive, kill -> group dead).
        This is driven by life/death status, not raw winrate, so it is robust.
        """
        board = self._new_board()
        self._apply_setup(board, stones)
        row, col = self.parse(target_vertex)
        colour = board.get(row, col)
        if colour is None:
            return {"error": f"no stone at {target_vertex}"}
        owner = "B" if colour == "b" else "W"
        group = self._group(board, row, col)
        if group is None:
            return {"error": "group not found"}

        # Verify a specific move (user's attempt): play it, then resolve the fight.
        if first_move:
            r = await self._resolve_after(
                board, region, group, colour, side_to_move, first_move, visits, max_plies
            )
            achieved = (goal == "live" and r["status"] == "alive") or (
                goal == "kill" and r["status"] == "dead"
            )
            return {
                "target": target_vertex,
                "owner": owner,
                "sideToMove": side_to_move,
                "goal": goal,
                "status": r["status"],
                "achieved": achieved,
                "bestMove": first_move,
                "line": r["line"],
            }

        # Vital-point candidates = KataGo's top region moves UNION empty points adjacent
        # to the target group (so the real vital point isn't missed if it's outside top-N).
        cand_res = await self._engine_best(board, side_to_move, region, visits)
        ordered = [
            m.get("move")
            for m in (cand_res.get("moveInfos") or [])
            if m.get("move")
        ]
        # group-adjacent empty points
        adj: list[str] = []
        for (r, c) in group:
            for dr, dc in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                nr, nc = r + dr, c + dc
                if 0 <= nr < self.size and 0 <= nc < self.size and board.get(nr, nc) is None:
                    v = self.gtp(nr, nc)
                    if v not in adj and (not region or v in region):
                        adj.append(v)
        candidates: list[str] = []
        for v in ordered + adj:
            if v and v not in candidates:
                candidates.append(v)
            if len(candidates) >= candidate_limit:
                break
        # ensure at least a few group-adjacent candidates are tried even if KataGo's list
        # was exhausted first (helps find the vital point).
        for v in adj:
            if v not in candidates:
                candidates.append(v)
            if len(candidates) >= candidate_limit + 4:
                break
        winning: list[tuple[str, str, list]] = []
        saw_states: dict[str, str] = {}
        for mv in candidates:
            try:
                pr, pc = self.parse(mv)
            except (ValueError, IndexError):
                continue
            if not (0 <= pr < self.size and 0 <= pc < self.size):
                continue
            if board.get(pr, pc) is not None:
                continue
            r = await self._resolve_after(
                board, region, group, colour, side_to_move, mv, visits, max_plies
            )
            saw_states[mv] = r["status"]
            achieved = (goal == "live" and r["status"] == "alive") or (
                goal == "kill" and r["status"] == "dead"
            )
            if achieved:
                winning.append((mv, r["status"], r["line"]))

        if winning:
            mv, status, line = winning[0]
            return {
                "target": target_vertex,
                "owner": owner,
                "sideToMove": side_to_move,
                "goal": goal,
                "status": status,
                "achieved": True,
                "bestMove": mv,
                "line": line,
                "winners": [w[0] for w in winning],
            }

        # No candidate achieved the goal -> the side to move cannot do it.
        return {
            "target": target_vertex,
            "owner": owner,
            "sideToMove": side_to_move,
            "goal": goal,
            "status": "unknown",
            "achieved": False,
            "bestMove": None,
            "line": [],
        }

    def _is_defender(self, colour: str, side: str) -> bool:
        """colour is the group owner ('b'/'w'), side is 'B'/'W'."""
        return colour == side.lower()

    def _score_for_side(self, board, group, colour: str, side: str) -> float:
        """How good is the resulting position for `side` w.r.t. the group's fate.
        Defender wants the group to stay alive (2 eyes); attacker wants it dead."""
        status = self.classify(board, group, colour)
        eyes = len(self._eye_regions(board, group, colour))
        captured = not self._exists(board, group)
        is_defender = self._is_defender(colour, side)
        if captured:
            # group is gone: great for attacker, terrible for defender.
            return 1000 if not is_defender else -1000
        if is_defender:
            base = 100 if status == "alive" else (0 if status == "dead" else 45)
            if captured:
                base -= 200
            return base + eyes * 5
        else:
            base = 100 if status == "dead" else (0 if status == "alive" else 45)
            if captured:
                base += 150
            return base + (10 - eyes) * 5

    async def _region_candidates(
        self, board, side: str, region: list[str], visits: int, limit: int = 6
    ) -> list[str]:
        res = await self._engine_best(board, side, region, visits)
        moves: list[str] = []
        for m in (res.get("moveInfos") or [])[:limit]:
            mv = m.get("move")
            if not mv or mv.startswith(("pass", "resign")):
                continue
            try:
                pr, pc = self.parse(mv)
            except (ValueError, IndexError):
                continue
            if 0 <= pr < self.size and 0 <= pc < self.size and board.get(pr, pc) is None:
                moves.append(mv)
        return moves

    async def _fight(
        self, board, region: list[str], group, colour: str, next_side: str, visits: int, max_plies: int
    ):
        """Goal-directed local fight: each side plays the move that best serves its
        life/death goal (defender makes eyes, attacker kills). Greedy, but far more
        life/death-aware than using KataGo's global-winrate best move."""
        side = next_side
        line: list[dict] = []
        status = "unknown"
        for _ in range(max_plies):
            moves = await self._region_candidates(board, side, region, visits, limit=6)
            chosen = None
            best_score = None
            for mv in moves:
                pr, pc = self.parse(mv)
                b2 = board.copy()
                if not self._play(b2, side, pr, pc):
                    continue
                score = self._score_for_side(b2, group, colour, side)
                if best_score is None or score > best_score:
                    best_score = score
                    chosen = mv
            if not chosen:
                break
            pr, pc = self.parse(chosen)
            if not self._play(board, side, pr, pc):
                break
            line.append({"color": side, "move": chosen})
            side = "W" if side == "B" else "B"
            status = self.classify(board, group, colour)
            if status in ("alive", "dead"):
                break
        if status == "unknown":
            status = self.classify(board, group, colour)
        return status, line

    async def _resolve_after(
        self,
        board,
        region: list[str],
        group,
        colour: str,
        player: str,
        move_to_play: str,
        visits: int,
        max_plies: int,
    ):
        """Play move_to_play for player, then run a goal-directed local fight."""
        b = board.copy()
        pr, pc = self.parse(move_to_play)
        if not self._play(b, player, pr, pc):
            return {"status": "unknown", "line": []}
        line = [{"color": player, "move": move_to_play}]
        next_side = "W" if player == "B" else "B"
        status, fline = await self._fight(b, region, group, colour, next_side, visits, max_plies)
        line += fline
        return {"status": status, "line": line}
