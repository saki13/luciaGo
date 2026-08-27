import json
import os
import shutil
from typing import List

import matplotlib.pyplot as plt
import numpy as np
from PIL import Image

from ..loader import go_board_init
from ..structure.board import next_state
from ..structure.constant import *


def _plot_board_state(state: List, moves: List, save_path: str, bgc: bool = True) -> None:
    board_size = state.shape[1]

    black_list, white_list = [], []
    for init_point in zip(*np.where(state[BLACK_CHAN] == 1)):
        black_list.append([init_point[1], board_size - init_point[0] - 1])
    for init_point in zip(*np.where(state[WHITE_CHAN] == 1)):
        white_list.append([init_point[1], board_size - init_point[0] - 1])
    _plot_go_figure(
        board_size, black_list, white_list, os.path.join(save_path, "original.png"), bgc=bgc,
    )

    for idx, move in enumerate(moves):
        next_state(state, move)
        black_list, white_list = [], []
        for init_point in zip(*np.where(state[BLACK_CHAN] == 1)):
            black_list.append([init_point[1], board_size - init_point[0] - 1])
        for init_point in zip(*np.where(state[WHITE_CHAN] == 1)):
            white_list.append([init_point[1], board_size - init_point[0] - 1])
        _plot_go_figure(
            board_size,
            black_list,
            white_list,
            os.path.join(save_path, "step" + str(idx + 1).zfill(2) + ".png"),
            bgc=bgc,
        )


def _plot_go_figure(board_size, black_list, white_list, save_path, bgc):
    fig = plt.figure(figsize=[8, 8])
    if bgc:
        fig.patch.set_facecolor((1, 1, 0.8))
    ax = fig.add_subplot(111)
    for x in range(board_size):
        ax.plot([x, x], [0, board_size - 1], "k")
    for y in range(board_size):
        ax.plot([0, board_size - 1], [y, y], "k")
    ax.set_position([0, 0, 1, 1])
    ax.set_axis_off()
    ax.set_xlim(-1, board_size)
    ax.set_ylim(-1, board_size)

    for point in black_list:
        ax.plot(
            *point,
            "o",
            markersize=350 // board_size,
            markeredgecolor=(0.5, 0.5, 0.5),
            markerfacecolor="k",
            markeredgewidth=2
        )
    for point in white_list:
        ax.plot(
            *point,
            "o",
            markersize=350 // board_size,
            markeredgecolor=(0, 0, 0),
            markerfacecolor="w",
            markeredgewidth=2
        )
    plt.savefig(save_path)
    plt.close()


def plot_go_board(
    state: np.array,
    moves: List,
    export_path: str = "output/current_state/",
    generate_gif: bool = True,
    bgc: bool = True,
) -> None:
    dir_name = export_path
    if not os.path.exists(dir_name):
        os.mkdir(dir_name)
    else:
        shutil.rmtree(dir_name)
        os.mkdir(dir_name)
    _plot_board_state(state, moves, dir_name, bgc=bgc)
    if generate_gif:
        imgs = (Image.open(os.path.join(dir_name, f)) for f in sorted(os.listdir(dir_name)))
        img = next(imgs)  # extract first image from iterator
        img.save(
            fp=os.path.join(dir_name, "result.gif"),
            format="GIF",
            append_images=imgs,
            save_all=True,
            duration=700,
            loop=0,
        )


def plot_go_file(
    file_path: str, export_path: str = None, generate_gif: bool = True, bgc: bool = True,
) -> None:
    board_info = json.load(open(file_path))
    board_size = board_info["board_size"]
    moves = [move[0] * board_size[0] + move[1] for move in board_info["ground_truth"]]
    state = go_board_init(file_path)
    dir_name = export_path if export_path else file_path.rstrip(".json") + "/"
    if not os.path.exists(dir_name):
        os.mkdir(dir_name)
    else:
        shutil.rmtree(dir_name)
        os.mkdir(dir_name)
    try:
        _plot_board_state(state, moves, dir_name, bgc=bgc)
        if generate_gif:
            imgs = (Image.open(os.path.join(dir_name, f)) for f in sorted(os.listdir(dir_name)))
            img = next(imgs)
            img.save(
                fp=os.path.join(dir_name, "result.gif"),
                format="GIF",
                append_images=imgs,
                save_all=True,
                duration=700,
                loop=0,
            )
    except:
        shutil.rmtree(dir_name)
        print(dir_name)
