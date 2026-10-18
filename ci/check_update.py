"""检查 TapTap 上是否有比 info 分支更新的 Phigros 版本。

用法: python ci/check_update.py <version.txt 路径>

通过 GITHUB_OUTPUT 输出:
  updated=true/false  是否有更新 (或 force 模式)
  version=<版本名>    TapTap 上的最新版本名
"""
import json
import os
import sys
import urllib.parse
import urllib.request

APP_ID = 165287
X_UA = "V=1&PN=TapTap&VN_CODE=283021001&LANG=zh_CN"


def latest_version():
    url = (
        "https://api.taptapdada.com/apk/v1/list-by-app"
        "?app_id=%d&X-UA=%s&from=0&limit=1"
        % (APP_ID, urllib.parse.quote(X_UA))
    )
    req = urllib.request.Request(url, headers={"User-Agent": "okhttp/3.12.1"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        data = json.load(resp)
    item = data["data"]["list"][0]
    # version_label 形如 "4.0.1 (157)", version.txt 只存版本名
    return item["version_label"].split(" ")[0], item["version_code"]


def main():
    version_file = sys.argv[1]
    force = os.environ.get("FORCE", "").lower() == "true"

    current = None
    if os.path.exists(version_file):
        with open(version_file, encoding="utf8") as f:
            current = f.read().strip()

    version, version_code = latest_version()
    updated = force or version != current
    print("current=%r latest=%r (code %d) force=%s -> updated=%s"
          % (current, version, version_code, force, updated))

    output = os.environ.get("GITHUB_OUTPUT")
    if output:
        with open(output, "a", encoding="utf8") as f:
            f.write("updated=%s\n" % str(updated).lower())
            f.write("version=%s\n" % version)
    if not updated:
        print("无新版本，跳过")


if __name__ == "__main__":
    main()
