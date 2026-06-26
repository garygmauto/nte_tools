# config_data.py
# 所有的坐标点数据都在这里，方便修改

FISH_CONFIG = {
    "game_res": [1600, 900],
    "check_points": {
        "cast_fishing": { 
            "coords": [[1490, 810], [1490, 800], [1490, 820]], 
            "color": [255, 255, 255], 
            "tol": 15 
        },
        "fish_hooked": { 
            "coords": [[1512, 800], [1511, 800], [1508, 794], [1511, 820]], 
            "color": [32, 124, 255], 
            "tol": 25 
        },
        "success_text": { 
            "coords": [[795, 820], [783, 820], [782, 820]], 
            "color": [227, 227, 227], 
            "tol": 15 
        }
    },
    "reeling_area": {
        "y_range": [58, 70],
        "bar_x_range": [510, 1100],
        "slider_x_range": [500, 1110]
    }
}