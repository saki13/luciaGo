import numpy as np
from scipy import ndimage
from scipy.ndimage import measurements

from .constant import *


def next_state(state, action1d):
    board_shape = state.shape[1:]
    action2d = action1d // board_shape[0], action1d % board_shape[1]
    player = turn(state)
    ko_protect = None
    assert state[VALID_CHAN, action2d[0], action2d[1]] == 1, (
        "Invalid move",
        action2d,
        state[VALID_CHAN, :, :],
    )
    state[player, action2d[0], action2d[1]] = 1
    adj_locs, surrounded = adj_data(state, action2d, player)
    killed_groups = update_pieces(state, adj_locs, player)
    if len(killed_groups) == 1 and surrounded:
        killed_group = killed_groups[0]
        if len(killed_group) == 1:
            ko_protect = killed_group[0]
    state[TURN_CHAN] = 1 - state[TURN_CHAN]
    player = turn(state)
    state[VALID_CHAN] = compute_valid_moves(state, player, ko_protect)


def update_pieces(state, adj_locs, player):
    opponent = 1 - player
    killed_groups = []
    all_pieces = np.sum(state[[BLACK_CHAN, WHITE_CHAN]], axis=0)
    empties = 1 - all_pieces
    all_opp_groups, _ = ndimage.measurements.label(state[opponent])
    all_adj_labels = all_opp_groups[adj_locs[:, 0], adj_locs[:, 1]]
    all_adj_labels = np.unique(all_adj_labels)
    for opp_group_idx in all_adj_labels[np.nonzero(all_adj_labels)]:
        opp_group = all_opp_groups == opp_group_idx
        liberties = empties * ndimage.binary_dilation(opp_group)
        if np.sum(liberties) <= 0:
            opp_group_locs = np.argwhere(opp_group)
            state[opponent, opp_group_locs[:, 0], opp_group_locs[:, 1]] = 0
            killed_groups.append(opp_group_locs)
    return killed_groups


def adj_data(state, action2d, player):
    neighbors = neighbor_deltas + action2d
    valid = (neighbors >= 0) & (neighbors < state.shape[1])
    valid = np.prod(valid, axis=1)
    neighbors = neighbors[np.nonzero(valid)]
    opp_pieces = state[1 - player]
    surrounded = (opp_pieces[neighbors[:, 0], neighbors[:, 1]] > 0).all()
    return neighbors, surrounded


# return: valid 1 invalid 0
def compute_valid_moves(state, player, ko_protect=None):
    all_pieces = np.sum(state[[BLACK_CHAN, WHITE_CHAN]], axis=0)
    empties = 1 - all_pieces
    possible_invalid_array = np.zeros(state.shape[1:])
    definite_valids_array = np.zeros(state.shape[1:])
    all_own_groups, num_own_groups = measurements.label(state[player])
    all_opp_groups, num_opp_groups = measurements.label(state[1 - player])
    expanded_own_groups = np.zeros((num_own_groups, *state.shape[1:]))
    expanded_opp_groups = np.zeros((num_opp_groups, *state.shape[1:]))
    for i in range(num_own_groups):
        expanded_own_groups[i] = all_own_groups == (i + 1)
    for i in range(num_opp_groups):
        expanded_opp_groups[i] = all_opp_groups == (i + 1)
    all_own_liberties = empties[np.newaxis] * ndimage.binary_dilation(
        expanded_own_groups, surround_struct[np.newaxis]
    )
    all_opp_liberties = empties[np.newaxis] * ndimage.binary_dilation(
        expanded_opp_groups, surround_struct[np.newaxis]
    )
    own_liberty_counts = np.sum(all_own_liberties, axis=(1, 2))
    opp_liberty_counts = np.sum(all_opp_liberties, axis=(1, 2))

    possible_invalid_array += np.sum(all_own_liberties[own_liberty_counts == 1], axis=0)
    possible_invalid_array += np.sum(all_opp_liberties[opp_liberty_counts > 1], axis=0)
    definite_valids_array += np.sum(all_own_liberties[own_liberty_counts > 1], axis=0)
    definite_valids_array += np.sum(all_opp_liberties[opp_liberty_counts == 1], axis=0)

    all_pieces_con = ndimage.convolve(all_pieces, surround_struct, mode="constant", cval=1)
    own_con = ndimage.convolve(state[player], surround_struct, mode="constant", cval=1)
    opp_con = ndimage.convolve(state[1 - player], surround_struct, mode="constant", cval=1)
    own_con_corner = ndimage.convolve(
        state[player], surround_struct_corner, mode="constant", cval=1
    )

    surrounded = all_pieces_con == 4
    invalid_moves = all_pieces + possible_invalid_array * (definite_valids_array == 0) * surrounded

    own_surrounded = own_con == 4
    opp_surrounded = opp_con == 4
    invalid_moves += own_surrounded
    invalid_moves += opp_surrounded

    possible_valid_array = np.logical_and(
        own_con_corner >= 2, np.logical_and(empties, opp_surrounded).astype(int)
    ).astype(int)

    for point in zip(*np.where(possible_valid_array == 1)):
        flag = True
        empties_now = np.copy(empties)
        empties_now[point] = 0
        adj_locs, _ = adj_data(state, point, player)
        all_adj_labels = all_opp_groups[adj_locs[:, 0], adj_locs[:, 1]]
        all_adj_labels = np.unique(all_adj_labels)
        for opp_group_idx in all_adj_labels[np.nonzero(all_adj_labels)]:
            opp_group = all_opp_groups == opp_group_idx
            liberties = empties_now * ndimage.binary_dilation(opp_group)
            if np.sum(liberties) <= 0:
                flag = False
                break
        if flag:
            possible_valid_array[point] = 0
    if ko_protect is not None:
        invalid_moves[ko_protect[0], ko_protect[1]] = 1
    valid_points = ndimage.binary_dilation(all_pieces, structure=valid_surround).astype(
        all_pieces.dtype
    )
    invalid_moves += 1 - valid_points + all_pieces
    total_valid = np.logical_or(1 - (invalid_moves > 0), possible_valid_array).astype(int)
    return total_valid


def valid_moves(state):
    result = np.argwhere(state[VALID_CHAN].flatten() == 1)
    result = [x[0] for x in result]
    return result


def turn(state):
    return int(state[TURN_CHAN][0, 0])


def if_win(state):
    all_pieces = np.sum(state[[BLACK_CHAN, WHITE_CHAN]], axis=0)
    empties = 1 - all_pieces
    all_own_groups, _ = measurements.label(state[WHITE_CHAN])
    adj_locs = np.where(state[ORIGIN_WHITE_CHAN] == 1)
    all_adj_labels = all_own_groups[adj_locs]
    all_adj_labels = np.unique(all_adj_labels)
    expanded_own_groups = np.zeros((len(all_adj_labels), *state.shape[1:]))
    for idx, num in enumerate(all_adj_labels):
        expanded_own_groups[idx] = all_own_groups == num
    expanded_own_groups = np.sum(expanded_own_groups, axis=0)

    all_eyes = ndimage.convolve(expanded_own_groups, surround_struct, mode="constant", cval=1) == 4
    index_eyes = np.where(all_eyes * empties == 1)
    if len(index_eyes[0]) > 1:
        index_eyes = list(zip(*index_eyes))
        count = 0
        # match_eyes = {}
        # valid_eyes = []
        for eye in index_eyes:
            neighbors = neighbor_corner + eye
            valid = (neighbors >= 0) & (neighbors < state.shape[1])
            valid = np.prod(valid, axis=1)
            neighbors = neighbors[np.nonzero(valid)]
            corner_sum = 8 - len(neighbors)
            white_sum = np.sum([state[WHITE_CHAN, nei[0], nei[1]] for nei in neighbors])
            eyes_sum = np.sum([1 if (nei[0], nei[1]) in index_eyes else 0 for nei in neighbors])
            total_num = corner_sum + white_sum + eyes_sum
            if total_num >= 7:
                count += 1
        if count >= 2:
            return 1

    result1 = state[ORIGIN_WHITE_CHAN] * state[WHITE_CHAN]
    if np.sum(result1) != np.sum(state[ORIGIN_WHITE_CHAN]):
        return 0
    # result2 = state[ORIGIN_BLACK_CHAN] * state[BLACK_CHAN]
    # if np.sum(result2) != np.sum(state[ORIGIN_BLACK_CHAN]):
    #     return 1
    return False


def if_end(state):
    m, n = state.shape[1:]
    return True if np.count_nonzero(state[VALID_CHAN] == 0) == m * n else False
