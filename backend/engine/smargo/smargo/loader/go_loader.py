import json

import numpy as np

from ..structure.board import compute_valid_moves
from ..structure.constant import *


def go_board_init(board_path: str) -> np.array:
    board_info = json.load(open(board_path))
    board = np.array(board_info["state"])
    state = np.zeros((CHAN, board_info["board_size"][0], board_info["board_size"][1]))
    state[BLACK_CHAN][np.where(board == 0)] = 1
    state[WHITE_CHAN][np.where(board == 1)] = 1
    state[ORIGIN_WHITE_CHAN] = state[WHITE_CHAN]
    state[ORIGIN_BLACK_CHAN] = state[BLACK_CHAN]
    state[TURN_CHAN] = board_info["turn"]
    state[VALID_CHAN] = compute_valid_moves(state, board_info["turn"])
    return state


def go_info_init(board_path: str) -> np.array:
    board_info = json.load(open(board_path))
    size = board_info["board_size"][0]
    ground_truth = np.array(board_info["ground_truth"])
    ground_truth = [move[0] * size + move[1] for move in ground_truth]
    return np.array(ground_truth), size
