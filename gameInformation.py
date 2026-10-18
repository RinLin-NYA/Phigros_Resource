import json
import os
import sys
from UnityPy import Environment
import zipfile
from io import BytesIO
from log import init_console_logger
import logging

DEBUG = False

LANGUAGE_KEYS = (
    ("chinese", "zh_cn"),
    ("chineseTraditional", "zh_tw"),
    ("english", "en"),
    ("japanese", "ja"),
    ("korean", "ko"),
)

def multi_language(value, unescape_newline=False):
    result = {}
    for key, out_key in LANGUAGE_KEYS:
        text = value[key]
        if unescape_newline:
            text = text.replace("\\n", "\n")
        result[out_key] = text
    return result

def multi_language_attr(obj, unescape_newline=False):
    result = {}
    for key, out_key in LANGUAGE_KEYS:
        text = getattr(obj, key)
        if unescape_newline:
            text = text.replace("\\n", "\n")
        result[out_key] = text
    return result

def collection_file_item(item):
    return {
        "key": item["key"],
        "sub_index": item["subIndex"],
        "name": multi_language(item["name"]),
        "date": item["date"],
        "supervisor": multi_language(item["supervisor"]),
        "category": item["category"],
        "content": multi_language(item["content"], True),
        "properties": multi_language(item["properties"]),
    }

def export_collection(database, control, logger):
    items = database["items"]
    folders = []
    for folder in control["folders"]:
        start = folder["startIndex"]
        end = folder["endIndex"]
        excluded = [(r["start"], r["end"]) for r in folder["excludedFiles"]]
        files = []
        for item in items:
            index = abs(item["getSong"])
            if start <= index <= end and not any(s <= index <= e for s, e in excluded):
                files.append(item)
        for ref in folder["includedIsolatedFiles"]:
            hit = next((item for item in items
                        if item["key"] == ref["key"] and item["subIndex"] == ref["subIndex"]), None)
            if hit is not None and hit not in files:
                files.append(hit)
        folders.append({
            "title": multi_language(folder["title"]),
            "sub_title": multi_language(folder["subTitle"]),
            "cover": folder["cover"],
            "files": [collection_file_item(item) for item in files],
        })
    with open("info/collection.json", "w", encoding="utf8") as f:
        json.dump(folders, f, ensure_ascii=False, separators=(",", ":"))
    logger.info("collection.json: %d folders, %d files",
                len(folders), sum(len(folder["files"]) for folder in folders))

def run(path, logger):
    Tips = None
    GameInformation = None
    Collections = None
    CollectionDatabase = None
    SaturnOSControl = None
    with open("typetree.json") as f:
        typetree = json.load(f)
    env = Environment()
    with zipfile.ZipFile(path) as apk:
        if "assets/bin/Data/data.unity3d" in apk.NameToInfo:
            with apk.open("assets/bin/Data/data.unity3d") as f:
                env.load_file(BytesIO(f.read()), name="assets/bin/Data/data.unity3d")
        else:
            with apk.open("assets/bin/Data/globalgamemanagers.assets") as f:
                env.load_file(BytesIO(f.read()), name="assets/bin/Data/globalgamemanagers.assets")
            with apk.open("assets/bin/Data/level0") as f:
                env.load_file(BytesIO(f.read()))
    for obj in env.objects:
        if obj.type.name != "MonoBehaviour":
            continue
        data = obj.read()
        try:
            script = data.m_Script.get_obj()
            if script is None:
                continue
            script_name = script.read().name
        except Exception:
            continue   # Skip when fail

        if script_name == "GameInformation":
            GameInformation = obj.read_typetree(typetree["GameInformation"])
        elif script_name == "GetCollectionControl":
            Collections = obj.read_typetree(typetree["GetCollectionControl"], True)
        elif script_name == "TipsProvider":
            Tips = obj.read_typetree(typetree["TipsProvider"], True)
        elif script_name == "CollectionDatabase":
            CollectionDatabase = obj.read_typetree(typetree["CollectionDatabase"])
        elif script_name == "SaturnOSControl":
            SaturnOSControl = obj.read_typetree(typetree["SaturnOSControl"])

    rows = []
    for key, songs in GameInformation["song"].items():
        if key == "otherSongs":
            continue
        for song in songs:
            if len(song["difficulty"]) == 5:
                song["difficulty"].pop()
            if song["difficulty"][-1] == 0.0:
                song["difficulty"].pop()
                song["charter"].pop()
            for i in range(len(song["difficulty"])):
                song["difficulty"][i] = str(round(song["difficulty"][i], 1))
            song["songsId"] = song["songsId"][:-2]
            # phi-plugin info.csv 格式: 定长 4 谱师列 (EZC/HDC/INC/ATC) + 4 定数列 (EZ/HD/IN/AT), 缺失留空
            charters = (list(song["charter"]) + ["", "", "", ""])[:4]
            levels = (list(song["difficulty"]) + ["", "", "", ""])[:4]
            rows.append((song["songsId"], song["songsName"], song["composer"], song["illustrator"],
                         *charters, *levels))

    logger.info(rows)

    with open("info/info.csv", "w", encoding="utf8") as f:
        f.write("id\tsong\tcomposer\tillustrator\tEZC\tHDC\tINC\tATC\tEZ\tHD\tIN\tAT\n")
        for row in rows:
            f.write("\t".join(row))
            f.write("\n")

    single = []
    illustration = []
    for key in GameInformation["keyStore"]:
        if key["kindOfKey"] == 0:
            single.append(key["keyName"])
        elif key["kindOfKey"] == 2 and key["keyName"] != "Introduction" and key["keyName"] not in single:
            illustration.append(key["keyName"])

    with open("info/single.txt", "w", encoding="utf8") as f:
        for item in single:
            f.write("%s\n" % item)

    with open("info/illustration.txt", "w", encoding="utf8") as f:
        for item in illustration:
            f.write("%s\n" % item)
    logger.info(single)
    logger.info(illustration)

    D = {}
    for item in Collections.collectionItems:
        if item.key in D:
            D[item.key][1] = item.subIndex
        else:
            D[item.key] = [multi_language_attr(item.multiLanguageTitle), item.subIndex]

    with open("info/collection.tsv", "w", encoding="utf8") as f:
        for key, value in D.items():
            f.write("%s\t%s\t%s\n" % (key, value[0]["zh_cn"], value[1]))

    with open("info/collection_index.json", "w", encoding="utf8") as f:
        json.dump(
            [{"key": key, "title": value[0], "sub_index": value[1]}
             for key, value in D.items()],
            f, ensure_ascii=False, separators=(",", ":"))

    with open("info/avatar.txt", "w", encoding="utf8") as avatar:
        with open("info/tmp.tsv", "w", encoding="utf8") as tmp:
            for item in Collections.avatars:
                avatar.write(item.name)
                avatar.write("\n")
                tmp.write("%s\t%s\n" % (item.name, item.addressableKey[7:]))

    # tips 数组顺序固定为 chinese/chineseTraditional/english/japanese/korean
    tips_multi = {}
    for i, (_, out_key) in enumerate(LANGUAGE_KEYS):
        if i < len(Tips.tips):
            tips_multi[out_key] = list(Tips.tips[i].tips)

    with open("info/tips.json", "w", encoding="utf8") as f:
        json.dump(tips_multi, f, ensure_ascii=False, separators=(",", ":"))

    with open("info/tips.txt", "w", encoding="utf8") as f:
        for tip in tips_multi.get("zh_cn", []):
            f.write(tip)
            f.write("\n")

    # 收藏品完整内容（4.0 / versionCode 155 起才有 CollectionDatabase）
    if CollectionDatabase is not None and SaturnOSControl is not None:
        export_collection(CollectionDatabase, SaturnOSControl, logger)
    else:
        logger.warning("未找到 CollectionDatabase/SaturnOSControl，跳过 collection.json 导出")


if __name__ == "__main__":
    if len(sys.argv) == 1 and os.path.isdir("/data/"):
        import subprocess
        r = subprocess.run("pm path com.PigeonGames.Phigros",stdin=subprocess.DEVNULL,stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,shell=True)
        file_path = r.stdout[8:-1].decode()
    else:
        file_path = sys.argv[1]
    if not os.path.isdir("info"):
        os.mkdir("info")
    run(file_path, init_console_logger())
