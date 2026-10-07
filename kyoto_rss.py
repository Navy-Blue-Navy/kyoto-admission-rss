import requests
from bs4 import BeautifulSoup
import xml.etree.ElementTree as ET
from pathlib import Path
from datetime import datetime, timezone, timedelta
from email.utils import format_datetime, parsedate_to_datetime
from urllib.parse import urljoin
import hashlib
import re

URL = "https://www.kyoto-u.ac.jp/ja/news?audience=45&tag=51"
OUTPUT = Path(__file__).parent / "kyoto.xml"

JST = timezone(timedelta(hours=9))

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/154.0.0.0 Safari/537.36"
    )
}

# 京都大学NEWSで使われるタグ
KNOWN_TAGS = [
    "入試",
    "学生支援",
    "教育",
    "研究",
    "国際交流",
    "社会連携",
    "大学案内",
]


# --------------------------------------------------
# 既存RSSを読み込む
# --------------------------------------------------

old_items = {}

if OUTPUT.exists():
    try:
        old_tree = ET.parse(OUTPUT)

        for item in old_tree.getroot().findall("./channel/item"):
            guid = item.findtext("guid", "")

            if guid:
                old_items[guid] = {
                    "title": item.findtext("title", ""),
                    "link": item.findtext("link", ""),
                    "description": item.findtext("description", ""),
                    "pubDate": item.findtext("pubDate", ""),
                    "guid": guid,
                }

    except Exception:
        old_items = {}


# --------------------------------------------------
# 京都大学NEWSを取得
# --------------------------------------------------

response = requests.get(
    URL,
    headers=HEADERS,
    timeout=30
)

response.raise_for_status()

soup = BeautifulSoup(
    response.text,
    "html.parser"
)

current_items = []
seen_urls = set()


# --------------------------------------------------
# 記事を抽出
# --------------------------------------------------

date_pattern = re.compile(
    r"^News\s+公開日\s+"
    r"(\d{4})年(\d{2})月(\d{2})日\s+"
    r"タグ\s+(.+)$"
)

for a in soup.find_all("a", href=True):

    href = a.get("href", "")

    # 個別NEWS記事だけを対象にする
    if "/ja/news/" not in href:
        continue

    article_url = urljoin(
        URL,
        href
    )

    # 重複を除外
    if article_url in seen_urls:
        continue

    raw_text = a.get_text(
        " ",
        strip=True
    )

    raw_text = re.sub(
        r"\s+",
        " ",
        raw_text
    ).strip()

    match = date_pattern.match(
        raw_text
    )

    if not match:
        continue

    year = int(
        match.group(1)
    )

    month = int(
        match.group(2)
    )

    day = int(
        match.group(3)
    )

    remainder = match.group(4).strip()


    # --------------------------------------------------
    # タグ部分と記事タイトルを分離
    # --------------------------------------------------

    tags = []

    while True:

        found = False

        for tag in KNOWN_TAGS:

            if remainder == tag:
                tags.append(tag)
                remainder = ""
                found = True
                break

            if remainder.startswith(tag + " "):
                tags.append(tag)

                remainder = remainder[
                    len(tag):
                ].strip()

                found = True
                break

        if not found:
            break


    # 「入試」タグが付いている記事だけ
    if "入試" not in tags:
        continue


    # タグを取り除いた残りが記事タイトル
    title = remainder.strip()

    if not title:
        continue


    # --------------------------------------------------
    # RSS項目を作成
    # --------------------------------------------------

    seen_urls.add(
        article_url
    )

    pub_date = datetime(
        year,
        month,
        day,
        12,
        0,
        0,
        tzinfo=JST
    )

    guid = hashlib.sha256(
        article_url.encode("utf-8")
    ).hexdigest()

    tag_text = "・".join(
        tags
    )

    current_items.append({
        "title": title,
        "link": article_url,
        "description": (
            f"京都大学NEWS　タグ：{tag_text}"
        ),
        "pubDate": format_datetime(
            pub_date
        ),
        "guid": guid,
    })


# --------------------------------------------------
# 以前のRSSにしかない記事も残す
# --------------------------------------------------

all_items = []
seen_guids = set()

for item in current_items:

    if item["guid"] not in seen_guids:

        all_items.append(
            item
        )

        seen_guids.add(
            item["guid"]
        )


for guid, item in old_items.items():

    if guid not in seen_guids:

        all_items.append(
            item
        )

        seen_guids.add(
            guid
        )


# --------------------------------------------------
# 公開日の新しい順に並べる
# --------------------------------------------------

def get_date(item):

    try:
        return parsedate_to_datetime(
            item["pubDate"]
        )

    except Exception:
        return datetime.min.replace(
            tzinfo=timezone.utc
        )


all_items.sort(
    key=get_date,
    reverse=True
)

# 最大300件保存
all_items = all_items[:300]


# --------------------------------------------------
# RSS 2.0を作成
# --------------------------------------------------

rss = ET.Element(
    "rss",
    version="2.0"
)

channel = ET.SubElement(
    rss,
    "channel"
)

ET.SubElement(
    channel,
    "title"
).text = "京都大学 NEWS（受験生・入試）"

ET.SubElement(
    channel,
    "link"
).text = URL

ET.SubElement(
    channel,
    "description"
).text = (
    "京都大学NEWSの"
    "「対象者：受験生」"
    "「タグ：入試」の新着情報"
)

ET.SubElement(
    channel,
    "language"
).text = "ja"


# --------------------------------------------------
# RSS記事を書き込む
# --------------------------------------------------

for item in all_items:

    element = ET.SubElement(
        channel,
        "item"
    )

    ET.SubElement(
        element,
        "title"
    ).text = item["title"]

    ET.SubElement(
        element,
        "link"
    ).text = item["link"]

    ET.SubElement(
        element,
        "description"
    ).text = item["description"]

    ET.SubElement(
        element,
        "pubDate"
    ).text = item["pubDate"]

    guid_element = ET.SubElement(
        element,
        "guid"
    )

    guid_element.set(
        "isPermaLink",
        "false"
    )

    guid_element.text = item["guid"]


# --------------------------------------------------
# XMLファイルとして保存
# --------------------------------------------------

tree = ET.ElementTree(
    rss
)

ET.indent(
    tree,
    space="  "
)

tree.write(
    OUTPUT,
    encoding="utf-8",
    xml_declaration=True
)


# --------------------------------------------------
# 実行結果を表示
# --------------------------------------------------

print("RSS作成成功")
print(
    "今回取得:",
    len(current_items),
    "件"
)

print(
    "RSS保存件数:",
    len(all_items),
    "件"
)

print(
    "保存先:",
    OUTPUT
)

print()
print("最新15件:")

for item in current_items[:15]:

    print(
        item["pubDate"],
        item["title"],
        "->",
        item["link"]
    )