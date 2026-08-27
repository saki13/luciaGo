import json
import os
import re
import shutil
from typing import Dict, Union

import numpy as np
from _ctypes import PyObj_FromPtr

from ..structure.board import compute_valid_moves, next_state
from ..structure.constant import *


class NoIndent(object):
    def __init__(self, value):
        if not isinstance(value, (list, tuple)):
            raise TypeError("Only lists and tuples can be wrapped")
        self.value = value


class MyEncoder(json.JSONEncoder):
    FORMAT_SPEC = "@@{}@@"
    regex = re.compile(FORMAT_SPEC.format(r"(\d+)"))

    def __init__(self, **kwargs):
        ignore = {"cls", "indent"}
        self._kwargs = {k: v for k, v in kwargs.items() if k not in ignore}
        super(MyEncoder, self).__init__(**kwargs)

    def default(self, obj):
        return (
            self.FORMAT_SPEC.format(id(obj))
            if isinstance(obj, NoIndent)
            else super(MyEncoder, self).default(obj)
        )

    def iterencode(self, obj, **kwargs):
        format_spec = self.FORMAT_SPEC
        for encoded in super(MyEncoder, self).iterencode(obj, **kwargs):
            match = self.regex.search(encoded)
            if match:
                id = int(match.group(1))
                no_indent = PyObj_FromPtr(id)
                json_repr = json.dumps(no_indent.value, **self._kwargs)
                encoded = encoded.replace('"{}"'.format(format_spec.format(id)), json_repr)
            yield encoded


def load_sgf(file_path: str) -> Dict:
    board_info = {}
    sgf_info = "".join(
        [line.strip("\n") for line in open(file_path, "r", encoding="utf-8").readlines()]
    )
    add_step = _load_sgf_str(sgf_info)
    if "turn" not in board_info:
        board_info["turn"] = 0
    add_step, board_info["turn"] = _board_rotate(add_step, board_info["turn"])
    board_info["ground_truth"] = add_step["ground_truth"]
    board_info["board_size"] = add_step["board_size"]
    board_info["state"] = np.ones(board_info["board_size"], dtype=int) * 2
    for x in add_step.items():
        if x[0] == "AB":
            for idx in x[1]:
                board_info["state"][idx[0], idx[1]] = 0
        elif x[0] == "AW":
            for idx in x[1]:
                board_info["state"][idx[0], idx[1]] = 1
    board_info["state"] = board_info["state"].tolist()
    board_info["source"] = file_path
    return board_info


def _test_valid(board_info):
    board_size = board_info["board_size"]
    moves = [move[0] * board_size[0] + move[1] for move in board_info["ground_truth"]]
    board = np.array(board_info["state"])
    state = np.zeros((CHAN, board_info["board_size"][0], board_info["board_size"][1]))
    state[BLACK_CHAN][np.where(board == 0)] = 1
    state[WHITE_CHAN][np.where(board == 1)] = 1
    state[ORIGIN_WHITE_CHAN] = state[WHITE_CHAN]
    state[ORIGIN_BLACK_CHAN] = state[BLACK_CHAN]
    state[TURN_CHAN] = board_info["turn"]
    state[VALID_CHAN] = compute_valid_moves(state, board_info["turn"])
    try:
        for move in moves:
            next_state(state, move)
        return True
    except:
        return False


def _load_sgf_str(sgf_info: str):
    init_b = _prase_sgf_str(sgf_info, "AB")
    init_w = _prase_sgf_str(sgf_info, "AW")
    ground_b = _prase_sgf_str(sgf_info, ";B")
    ground_w = _prase_sgf_str(sgf_info, ";W")
    b_indexs = [[ord(x[1]) - 97, ord(x[0]) - 97] for x in init_b]
    w_indexs = [[ord(x[1]) - 97, ord(x[0]) - 97] for x in init_w]
    b_ground = [[ord(x[1]) - 97, ord(x[0]) - 97] for x in ground_b]
    w_ground = [[ord(x[1]) - 97, ord(x[0]) - 97] for x in ground_w]
    ground_truth = []
    if len(b_ground) == len(w_ground):
        for idx in range(len(b_ground)):
            ground_truth.append(b_ground[idx])
            ground_truth.append(w_ground[idx])
    elif len(b_ground) == len(w_ground) + 1:
        ground_truth.append(b_ground[0])
        for idx in range(len(b_ground) - 1):
            ground_truth.append(b_ground[idx + 1])
            ground_truth.append(w_ground[idx])
    step_info = {
        "AB": b_indexs,
        "AW": w_indexs,
        "ground_truth": ground_truth,
    }
    return step_info


def _prase_sgf_str(string: str, index: str):
    result = "".join(
        [m.group().replace(index, "") for m in re.finditer(index + r"(\[[a-zA-Z]+\])+", string)]
    )
    result = result.strip("[").strip("]").split("][")
    return result


def _board_rotate(indexs: Dict, turn: int) -> Union[Dict, int]:
    total = []
    for x in indexs.items():
        total += x[1]
    value_mean = np.mean(np.array(total), axis=0)
    for item in indexs.items():
        if value_mean[0] > 10 and value_mean[1] < 10:
            indexs[item[0]] = [[18 - x[0], x[1]] for x in item[1]]
        elif value_mean[0] < 10 and value_mean[1] > 10:
            indexs[item[0]] = [[x[0], 18 - x[1]] for x in item[1]]
        elif value_mean[0] > 10 and value_mean[1] > 10:
            indexs[item[0]] = [[18 - x[0], 18 - x[1]] for x in item[1]]
    black_mean = np.mean(np.array(indexs["AB"]), axis=0)
    white_mean = np.mean(np.array(indexs["AW"]), axis=0)
    black_max = np.max(np.array(indexs["AB"]))
    white_max = np.max(np.array(indexs["AW"]))
    ground_max = np.max(np.array(indexs["ground_truth"]))
    max_num = max(black_max, white_max, ground_max)
    if max_num <= 6:
        indexs["board_size"] = (7, 7)
    elif max_num > 6 and max_num <= 8:
        indexs["board_size"] = (9, 9)
    elif max_num > 8 and max_num <= 10:
        indexs["board_size"] = (11, 11)
    elif max_num > 10 and max_num <= 12:
        indexs["board_size"] = (13, 13)
    else:
        indexs["board_size"] = (19, 19)
    if black_mean[0] < white_mean[0] and black_mean[1] < white_mean[1]:
        temp = indexs["AB"]
        indexs["AB"] = indexs["AW"]
        indexs["AW"] = temp
        turn = 1 - turn
    return indexs, turn


def dump_json(board_info, dump_path) -> None:
    board_info["state"] = [NoIndent(elem) for elem in board_info["state"]]
    board_info["ground_truth"] = [NoIndent(elem) for elem in board_info["ground_truth"]]
    if "predict" in board_info:
        board_info["predict"] = [NoIndent(elem) for elem in board_info["predict"]]
    with open(dump_path, "w") as f:
        json.dump(board_info, f, cls=MyEncoder, sort_keys=True, indent=4)


def convert_go_sgf(folder_name: str, dump_floder_name: str,) -> None:
    max_num = 0

    json_fold = os.path.join(dump_floder_name, "json")
    sgf_fold = os.path.join(dump_floder_name, "sgf")
    if not os.path.exists(json_fold):
        os.mkdir(json_fold)
    if not os.path.exists(sgf_fold):
        os.mkdir(sgf_fold)
    else:
        json_files = [_ for _ in os.listdir(dump_floder_name) if _.endswith(".json")]
        if len(json_files) != 0:
            max_num_file = sorted(json_files)[-1]
            max_num = int(max_num_file.rstrip(".json").split("_")[1]) + 1
    for path, _, file_list in os.walk(folder_name):
        for file_name in file_list:
            file_path = os.path.join(path, file_name)
            try:
                board_info = load_sgf(file_path)
                if _test_valid(board_info):
                    f_name = "tsumego_" + str(max_num).zfill(6)
                    dump_json(board_info, os.path.join(json_fold, f_name + ".json"))
                    shutil.copyfile(file_path, os.path.join(sgf_fold, f_name + ".sgf"))
                    max_num += 1
            except:
                print(file_path + " load err!")
