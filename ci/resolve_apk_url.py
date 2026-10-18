"""解析 Phigros 最新 APK 的 TapTap 限时直链。

链路 (均已实测):
  1. 访问 taptap.cn 应用页拿 WAF cookie (否则第 3 步 403)
  2. webapiv2 detail-by-id 取 apk_id
  3. 带签名 POST api.taptapdada.com/apk/v1/detail 换 d-tc.tapapks.com 直链
     (签名盐为 TapTap 客户端硬编码, 若失效需更新 SALT/X_UA)

通过 GITHUB_OUTPUT 输出:
  url=<直链>  md5=<APK md5>  size=<字节数>
"""
import hashlib
import http.cookiejar
import json
import os
import random
import string
import time
import urllib.parse
import urllib.request
import uuid

APP_ID = 165287
SALT = "PeCkE6Fu0B10Vm9BKfPfANwCUAn5POcs"
# 客户端 X-UA 用于 api.taptapdada.com; taptap.cn 网页接口用浏览器 UA
CLIENT_X_UA = (
    "V=1&PN=TapTap&VN=2.40.1-rel.100000&VN_CODE=240011000&LOC=CN"
    "&LANG=zh_CN&CH=default&UID=%s&NT=1&SR=1080x2030&DEB=Xiaomi"
    "&DEM=Redmi+Note+5&OSV=9"
)
WEB_X_UA = (
    "V=1&PN=TapTap&VN=2.83.2-rel.100100&VN_CODE=283021001&LOC=CN"
    "&LANG=zh_CN&CH=default&VID=37363707"
)
BROWSER_UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/120.0 Safari/537.36"


def main():
    node = str(uuid.uuid4())
    cookie_jar = http.cookiejar.CookieJar()
    opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cookie_jar))

    # 1. WAF cookie
    req = urllib.request.Request(
        "https://www.taptap.cn/app/%d" % APP_ID,
        headers={"User-Agent": BROWSER_UA},
    )
    opener.open(req, timeout=30).read()

    # 2. apk_id
    req = urllib.request.Request(
        "https://www.taptap.cn/webapiv2/app/v2/detail-by-id/%d?X-UA=%s"
        % (APP_ID, urllib.parse.quote(WEB_X_UA)),
        headers={
            "User-Agent": BROWSER_UA,
            "Referer": "https://www.taptap.cn/app/%d" % APP_ID,
        },
    )
    with opener.open(req, timeout=30) as resp:
        detail = json.load(resp)
    apk_id = detail["data"]["download"]["apk_id"]
    print("apk_id =", apk_id)

    # 3. 签名换直链
    x_ua = CLIENT_X_UA % node
    nonce = "".join(random.sample(string.ascii_lowercase + string.digits, 5))
    timestamp = int(time.time())
    param = (
        "abi=arm64-v8a,armeabi-v7a,armeabi&id=%d&node=%s&nonce=%s"
        "&sandbox=1&screen_densities=xhdpi&time=%s" % (apk_id, node, nonce, timestamp)
    )
    sign = hashlib.md5(("X-UA=%s&%s%s" % (x_ua, param, SALT)).encode()).hexdigest()
    req = urllib.request.Request(
        "https://api.taptapdada.com/apk/v1/detail?X-UA=" + urllib.parse.quote(x_ua),
        data=("%s&sign=%s" % (param, sign)).encode(),
        headers={
            "Content-Type": "application/x-www-form-urlencoded",
            "User-Agent": "okhttp/3.12.1",
        },
    )
    with opener.open(req, timeout=30) as resp:
        result = json.load(resp)
    apk = result["data"]["apk"]
    print("name =", apk["name"], "size =", apk["size"], "md5 =", apk["md5"])

    output = os.environ.get("GITHUB_OUTPUT")
    if output:
        with open(output, "a", encoding="utf8") as f:
            f.write("url=%s\n" % apk["download"])
            f.write("md5=%s\n" % apk["md5"])
            f.write("size=%s\n" % apk["size"])
    else:
        print(apk["download"])


if __name__ == "__main__":
    main()
