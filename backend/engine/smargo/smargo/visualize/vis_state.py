import matplotlib.pyplot as plt
import numpy as np

from ..structure.constant import *


def plot_go_state(state: np.array, save_path: str = None) -> None:
    board_size = state.shape[1]
    fig = plt.figure(figsize=[8, 8])
    fig.patch.set_facecolor((1, 1, 0.8))
    ax = fig.add_subplot(111)
    for x in range(board_size):
        ax.plot([x, x], [0, board_size - 1], "k")
    for y in range(7):
        ax.plot([0, board_size - 1], [y, y], "k")
    ax.set_position([0, 0, 1, 1])
    ax.set_axis_off()
    ax.set_xlim(-1, board_size)
    ax.set_ylim(-1, board_size)

    for init_point in zip(*np.where(state[BLACK_CHAN] == 1)):
        ax.plot(
            init_point[1],
            board_size - init_point[0] - 1,
            "o",
            markersize=50,
            markeredgecolor=(0.5, 0.5, 0.5),
            markerfacecolor="k",
            markeredgewidth=2,
        )
    for init_point in zip(*np.where(state[WHITE_CHAN] == 1)):
        ax.plot(
            init_point[1],
            board_size - init_point[0] - 1,
            "o",
            markersize=50,
            markeredgecolor=(0, 0, 0),
            markerfacecolor="w",
            markeredgewidth=2,
        )
    if save_path:
        plt.savefig(save_path)
    else:
        plt.show()
    plt.close()
