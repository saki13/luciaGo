import os

import requests


def go_scraping(write_path="data/download/"):
    if not os.path.exists(write_path):
        os.mkdir(write_path)
    root_path = "https://gobase.org/studying/problems/"
    go_set = {
        "tsumego": [
            "S171",
            "S172",
            "S173",
            "S174",
            "S175",
            "S176",
            "S181",
            "S182",
            "S183",
            "S184",
            "S185",
            "S186",
        ],
        "korschelt": ["S1"],
        "warmingup": ["S1"],
    }

    for item in go_set.items():
        if item[0] == "tsumego":
            dir_path = os.path.join(write_path, item[0])
            if not os.path.exists(dir_path):
                os.mkdir(dir_path)
            for go_set in item[1]:
                dir_path = os.path.join(write_path, item[0], go_set)
                if not os.path.exists(dir_path):
                    os.mkdir(dir_path)
                for i in range(10):
                    filename = "prob-" + str(i + 1).zfill(2) + ".sgf"
                    image_url = os.path.join(root_path, item[0], go_set, filename)
                    print(image_url)
                    try:
                        r = requests.get(image_url)
                        with open(os.path.join(dir_path, filename), "wb") as f:
                            f.write(r.content)
                    except:
                        pass
        else:
            dir_path = os.path.join(write_path, item[0])
            if not os.path.exists(dir_path):
                os.mkdir(dir_path)
            for go_set in item[1]:
                for i in range(30):
                    filename = go_set.replace("S", "L") + "-" + str(i + 1).zfill(4) + ".sgf"
                    image_url = os.path.join(root_path, item[0], go_set, filename)
                    print(image_url)
                    try:
                        r = requests.get(image_url)
                        with open(os.path.join(dir_path, filename), "wb") as f:
                            f.write(r.content)
                    except:
                        pass
