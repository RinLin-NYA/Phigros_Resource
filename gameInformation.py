import csv
import json
import os
import re
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

COLLECTION_CSV_HEADER = ("folder", "folder_sub", "cover", "key", "sub_index",
                         "name", "date", "supervisor", "category", "content", "properties")

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
    # 按语言拆分, 每语言一个 csv; 正文内换行转义为字面 \n 以保证一行一条记录
    total = 0
    for _, out_key in LANGUAGE_KEYS:
        with open(f"info/collection_{out_key}.csv", "w", encoding="utf8", newline="") as f:
            writer = csv.writer(f, lineterminator="\n")
            writer.writerow(COLLECTION_CSV_HEADER)
            for folder in folders:
                for item in folder["files"]:
                    writer.writerow([
                        folder["title"][out_key],
                        folder["sub_title"][out_key],
                        folder["cover"],
                        item["key"],
                        item["sub_index"],
                        item["name"][out_key],
                        item["date"],
                        item["supervisor"][out_key],
                        item["category"],
                        item["content"][out_key].replace("\n", "\\n"),
                        item["properties"][out_key].replace("\n", "\\n"),
                    ])
                    total += 1
    logger.info("collection_<lang>.csv: %d folders, %d files x %d languages",
                len(folders), total // len(LANGUAGE_KEYS), len(LANGUAGE_KEYS))

def export_story(story, logger):
    data = {}
    for control, instances in story.items():
        data[control] = [
            [{"lines": [multi_language(line) for line in page["lines"]]}
             for page in instance["pages"]]
            for instance in instances
        ]
    with open("info/story.json", "w", encoding="utf8") as f:
        json.dump(data, f, ensure_ascii=False, separators=(",", ":"))
    logger.info("story.json: %s",
                {control: len(instances) for control, instances in story.items()})

def run(path, logger):
    Tips = None
    GameInformation = None
    Collections = None
    CollectionDatabase = None
    SaturnOSControl = None
    story = {"Chapter9StoryTextView": [], "C9StoryControl": []}
    with open("typetree.json") as f:
        typetree = json.load(f)
    env = Environment()
    with zipfile.ZipFile(path) as apk:
        if "assets/bin/Data/data.unity3d" in apk.NameToInfo:
            with apk.open("assets/bin/Data/data.unity3d") as f:
                env.load_file(BytesIO(f.read()), name="assets/bin/Data/data.unity3d")
        else:
            # 散装布局 (无 data.unity3d): 加载全部 level* 与 sharedassets*,
            # split 分片按序号合并为完整 SerializedFile
            names = apk.NameToInfo
            plain = []
            splits = {}  # sharedassetsN.assets -> [(index, entry_name)]
            for name in names:
                if not name.startswith("assets/bin/Data/"):
                    continue
                base = name[len("assets/bin/Data/"):]
                if base == "globalgamemanagers.assets" or re.fullmatch(r"level\d+", base):
                    plain.append(name)
                elif re.fullmatch(r"sharedassets\d+\.assets", base):
                    plain.append(name)
                else:
                    m = re.fullmatch(r"(sharedassets\d+)\.assets\.split(\d+)", base)
                    if m:
                        splits.setdefault(m.group(1), []).append((int(m.group(2)), name))
            for name in plain:
                with apk.open(name) as f:
                    env.load_file(BytesIO(f.read()), name=name)
            for base in sorted(splits):
                data = b"".join(
                    apk.read(name) for _, name in sorted(splits[base])
                )
                env.load_file(BytesIO(data), name=f"assets/bin/Data/{base}.assets")
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
        elif script_name in story:
            # 4.0.1 的 APK 并未附带剧情场景实例（热更新内容），此处为机会式提取
            try:
                story[script_name].append(obj.read_typetree(typetree[script_name]))
            except Exception:
                logger.warning("读取 %s 实例失败，跳过", script_name)

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

    # tips 数组顺序固定为 chinese/chineseTraditional/english/japanese/korean,
    # 按语言各输出一个 txt, 每行一条 (与上游 tips.txt 相同的纯文本格式)
    for i, (_, out_key) in enumerate(LANGUAGE_KEYS):
        if i >= len(Tips.tips):
            break
        with open(f"info/tips_{out_key}.txt", "w", encoding="utf8") as f:
            for tip in Tips.tips[i].tips:
                f.write(tip)
                f.write("\n")

    # 收藏品完整内容（4.0 / versionCode 155 起才有 CollectionDatabase）
    if CollectionDatabase is not None and SaturnOSControl is not None:
        export_collection(CollectionDatabase, SaturnOSControl, logger)
    else:
        logger.warning("未找到 CollectionDatabase/SaturnOSControl，跳过收藏品导出")

    # 第九章剧情文本（Chapter9StoryTextView / C9StoryControl 实例可能不存在）
    if any(story.values()):
        export_story(story, logger)
    else:
        logger.warning("未找到剧情文本控件，跳过 story.json 导出")


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
