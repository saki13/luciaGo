from ..model.mcts import TreeNode


def print_go_tree(node: TreeNode, max_depth: int = 3, _depth: int = 0) -> None:
    if _depth < max_depth:
        length = len(list(node.children))
        for idx, child in enumerate(node.children.items()):
            if idx + 1 == length:
                print(
                    "│    " * _depth + "└──",
                    "move" + str(child[0]) + ": " + str(child[1].n_visits) + ",",
                    "v: " + str(child[1].value),
                )
                print_go_tree(child[1], max_depth=max_depth, _depth=_depth + 1)
            else:
                print(
                    "│    " * _depth + "├──",
                    "move" + str(child[0]) + ": " + str(child[1].n_visits) + ", ",
                    "v: " + str(child[1].value),
                )
                print_go_tree(child[1], max_depth=max_depth, _depth=_depth + 1)
