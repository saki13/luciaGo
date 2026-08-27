import copy
from operator import itemgetter

import numpy as np
from tqdm import tqdm

from ..structure.board import *


class TreeNode:
    def __init__(self, parent, prior_p):
        self.parent = parent
        self.children = {}
        self.n_visits = 0
        self.Q = 0
        self.U = 0
        self.value = 0
        self.P = prior_p

    def select(self, c_puct):
        return max(self.children.items(), key=lambda act_node: act_node[1].get_value(c_puct))

    def expand(self, action_priors):
        for action, prob in action_priors:
            if action not in self.children:
                self.children[action] = TreeNode(self, prob)

    def update(self, leaf_value):
        self.value += leaf_value
        self.n_visits += 1
        self.Q += 1.0 * (leaf_value - self.Q) / self.n_visits

    def update_recursive(self, leaf_value):
        if self.parent:
            self.parent.update_recursive(-leaf_value)
        self.update(leaf_value)

    def get_value(self, c_puct):
        self.U = c_puct * self.P * np.sqrt(self.parent.n_visits) / (1 + self.n_visits)
        return self.Q + self.U

    def is_leaf(self):
        return self.children == {}


class MCTS:
    def __init__(self, c_puct=5):
        self.root = TreeNode(None, 1.0)
        self.root_total = self.root
        self.c_puct = c_puct
        self.depth = 0

    def policy_value_fn(self, game_state_simulator):
        availables = valid_moves(game_state_simulator)
        action_probs = np.random.rand(len(availables))
        return zip(availables, action_probs)

    def playout(self, simulate_game_state):
        node = self.root
        depth = self.depth
        while True:
            if node.is_leaf():
                break
            depth += 1
            action, node = node.select(self.c_puct)
            next_state(simulate_game_state, action)
        winner = if_win(simulate_game_state)
        if winner is not False:
            leaf_value = 1.0 if turn(simulate_game_state) == winner else -1.0
        elif depth < self.total_play and not if_end(simulate_game_state):
            availables = valid_moves(simulate_game_state)
            action_probs = np.ones(len(availables)) / len(availables)
            node.expand(zip(availables, action_probs))
            leaf_value = self.evaluate_rollout(simulate_game_state, depth=depth)
        else:
            leaf_value = 0
        node.update_recursive(-leaf_value)

    def get_move(self, game, n_playout=10000):
        self.n_playout = n_playout
        self.total_play = np.prod(game.shape[1:])
        for _ in tqdm(range(self.n_playout), desc=f"Training Monte Carlo Trees: "):
            game_state = copy.deepcopy(game)
            self.playout(game_state)
        return max(self.root.children.items(), key=lambda act_node: act_node[1].n_visits)[0]

    def update_with_move(self, last_move):
        if last_move in self.root.children:
            self.root = self.root.children[last_move]
            self.root.parent = None
        else:
            self.root = TreeNode(None, 1.0)

    def evaluate_rollout(self, simulate_game_state, depth):
        game_state_copy = copy.deepcopy(simulate_game_state)
        player = turn(game_state_copy)
        for _ in range(self.total_play - depth):
            winner = if_win(game_state_copy)
            if winner is not False:
                return 1.0 if player == winner else -1.0
            if if_end(game_state_copy):
                return 0
            depth += 1
            action_probs = self.policy_value_fn(game_state_copy)
            max_action = max(action_probs, key=itemgetter(1))[0]
            next_state(game_state_copy, max_action)
        else:
            return 0

    def train(self, game_init, init_playout=500, num_moves=None):
        self.depth = 0
        game = copy.deepcopy(game_init)

        self.total_play = np.prod(game.shape[1:])
        self.init_playout = init_playout

        game_state = copy.deepcopy(game)
        self.playout(game_state)

        while True:
            if num_moves:
                if num_moves == self.depth:
                    break
                else:
                    iter_times = self.init_playout
                    # iter_times = int(((num_moves - self.depth)/num_moves) * self.init_playout)
            else:
                iter_times = self.init_playout
            for _ in tqdm(
                range(iter_times), desc=f'Training Monte Carlo Trees, depth "{self.depth}": ',
            ):
                game_state = copy.deepcopy(game)
                self.playout(game_state)
            if self.root.is_leaf():
                break
            move = max(self.root.children.items(), key=lambda act_node: act_node[1].n_visits,)[0]
            print("current move is:", move)
            print([{x[0]: x[1].n_visits} for x in self.root.children.items()])
            print([{x[0]: x[1].value} for x in self.root.children.items()])
            self.root = self.root.children[move]
            self.depth += 1
            next_state(game, move)
        self.root = self.root_total

    def _train_iter(self, game, iter_playout):
        count_num, total = 0, 0
        temp = max(
            self.root.children.items(), key=lambda act_node: act_node[1].get_value(self.c_puct),
        )
        while count_num < iter_playout:
            total += 1
            if total > 2000:
                break
            game_state = copy.deepcopy(game)
            self.playout(game_state)
            move = max(
                self.root.children.items(), key=lambda act_node: act_node[1].get_value(self.c_puct),
            )
            if move != temp:
                temp = move
                count_num = 0
            else:
                count_num += 1
        print("total iter:", total)

    def result_moves(self, num_moves=None):
        move_list = []
        self.root = self.root_total
        while not self.root.is_leaf() and len(move_list) != num_moves:
            move = max(self.root.children.items(), key=lambda act_node: act_node[1].n_visits,)[0]
            move_list.append(move)
            self.root = self.root.children[move]
            self.root.parent = None
        return move_list

    def result_moves_top3(self, num_moves=None):
        move_list = []
        self.root = self.root_total
        while not self.root.is_leaf() and len(move_list) != num_moves:
            move = max(self.root.children.items(), key=lambda act_node: act_node[1].n_visits,)[0]
            move_result = sorted(
                self.root.children.items(), key=lambda act_node: act_node[1].n_visits,
            )[:3]
            move_result = [x[0] for x in move_result]
            move_list.append(move_result)
            self.root = self.root.children[move]
            self.root.parent = None
        return move_list
