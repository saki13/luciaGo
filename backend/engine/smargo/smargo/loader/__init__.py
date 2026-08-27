"""Smart Tsumego Loader."""

from .go_convert import convert_go_sgf, dump_json, load_sgf
from .go_loader import go_board_init, go_info_init
from .go_web_scrap import go_scraping

__all__ = [
    "load_sgf",
    "dump_json",
    "convert_go_sgf",
    "go_board_init",
    "go_scraping",
    "go_info_init",
]
