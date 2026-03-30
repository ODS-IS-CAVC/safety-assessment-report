import json
import csv
import argparse
import os

DETECT_CSV_HEADER = [
    "frame",
    "file",
    # "obj_id",
    "distance_x",
    "distance_y",
    "distance_z",
    "angle_1",
    "angle_2",
    "left_distance_x",
    "left_distance_y",
    "left_distance_z",
    "left_angle_1",
    "left_angle_2",
    "right_distance_x",
    "right_distance_y",
    "right_distance_z",
    "right_angle_1",
    "right_angle_2"
]

# launch.json
# {
#     "name": "detect2csv.py",
#     "type": "debugpy",
#     "request": "launch",
#     "program": "repo/try_bravs/tool/detect2csv.py",
#     "console": "integratedTerminal",
#     "args": [
#         "--rel_coord_file","repo/try_bravs/divp/~/detection_distance_result.json"
#     ]
# }

def main():
    parser = argparse.ArgumentParser(description="相対距離推定結果jsonファイルCSV変換")
    parser.add_argument(
        "--rel_coord_file",
        type=str,
        required=True,
        help="相対距離推定結果jsonファイルパス",
    )

    args = parser.parse_args()
    rel_coord_file = args.rel_coord_file
    assert isinstance(rel_coord_file, str)

    with open(rel_coord_file, mode='r', encoding='utf-8') as f:
        rel_coord_result = json.load(f)

    detect_csv = os.path.splitext(rel_coord_file)[0] + ".csv"

    obj_results = {}
    for item in rel_coord_result['results']:
        frame = item['frame']
        file = item['file']

        for detect in item['segmentations']:
            obj_id = str(detect['obj_id'])
            if obj_id not in obj_results.keys():
                obj_results[obj_id] = []
            distances = []
            angles = []
            for calc in detect['calculate']:
                distance = calc['distance']
                angle = calc['angle']
                distances.append(distance)
                angles.append(angle)
            for i in range(3 - len(distances)):
                distances.append([None, None, None])
                angles.append([None, None, None])
                
            obj_results[obj_id].append(dict(zip(
                DETECT_CSV_HEADER,
                [
                    frame, file,
                    distances[0][0], distances[0][1], distances[0][2],
                    angles[0][0], angles[0][1],
                    distances[1][0], distances[1][1], distances[1][2],
                    angles[1][0], angles[1][1],
                    distances[2][0], distances[2][1], distances[2][2],
                    angles[2][0], angles[2][1],
                ]
            )))
    
    for key in obj_results.keys():
        detect_csv = os.path.splitext(rel_coord_file)[0] + key + ".csv"
        with open(detect_csv, mode='w', encoding='utf-8') as f:
            writer = csv.DictWriter(f, fieldnames=DETECT_CSV_HEADER)
            writer.writeheader()
            writer.writerows(obj_results[key])


if __name__ == "__main__":
    main()
