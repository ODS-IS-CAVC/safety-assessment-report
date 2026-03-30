import os
import xml.etree.ElementTree as ET
import xml.dom.minidom as minidom
import argparse

def main():
    parser = argparse.ArgumentParser(description="OpenDRIVEファイルのelevationタグ初期化")
    parser.add_argument(
        "--xodr_file",
        type=str,
        # required=True,
        default="/workspace/try_bravs/map_tools/map_data/V-DriveROOT/data/XODR/E1A_EnsyuMorimachiPA_C.xodr",
        help="OpenDRIVEファイル",
    )

    args = parser.parse_args()
    xodr_file = args.xodr_file
    assert isinstance(xodr_file, str)

    tree = ET.parse(xodr_file)
    root = tree.getroot()

    roads = [child for child in root if child.tag == 'road']
    for road in roads:
        # elevationProfileタグを取得
        elevation_profile = road.find('elevationProfile')
        if elevation_profile is not None:
            # elevationタグをすべて削除
            for elevation in elevation_profile.findall('elevation'):
                elevation_profile.remove(elevation)

            # 新しいelevationタグを作成し、属性をすべて0に設定
            new_elevation = ET.Element('elevation', {'s': '0', 'a': '0', 'b': '0', 'c': '0', 'd': '0'})

            # elevationProfileタグに新しいelevationタグを追加
            elevation_profile.append(new_elevation)

        # lateralProfile
        lateral_profile = road.find('lateralProfile')
        if lateral_profile is not None:
            # elevationタグをすべて削除
            for superelevation in lateral_profile.findall('superelevation'):
                lateral_profile.remove(superelevation)

            # 新しいelevationタグを作成し、属性をすべて0に設定
            new_superelevation = ET.Element('superelevation', {'s': '0', 'a': '0', 'b': '0', 'c': '0', 'd': '0'})

            # elevationProfileタグに新しいelevationタグを追加
            lateral_profile.append(new_superelevation)
        

    # 修正されたXMLデータを文字列に変換
    new_xml_data = ET.tostring(root, encoding='unicode')
    reparsed = minidom.parseString(new_xml_data)
    pretty_string = reparsed.toprettyxml(indent="    ")
    pretty_string = "\n".join([line for line in pretty_string.split('\n') if line.strip()])
    
    # 修正されたXMLデータをファイルに保存
    output_file = os.path.splitext(xodr_file)[0] + "_mod.xodr"
    with open(output_file, "w", encoding='utf-8') as file:
        file.write(pretty_string)

if __name__ == "__main__":
    main()