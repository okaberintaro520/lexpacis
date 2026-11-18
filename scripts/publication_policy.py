"""Conservative editorial screening for automatically published metadata."""
import re
import unicodedata
from urllib.parse import unquote


_CJK = re.compile(
    r"中国|中國|中華|中华|中共|中方|涉华|涉華|对华|對華|"
    r"台湾|台灣|臺灣|台海|臺海|两岸|兩岸|香港|港澳|澳门|澳門|"
    r"新疆|西藏|藏区|藏區|维吾尔|維吾爾|南海|东海|東海|钓鱼岛|釣魚島|"
    r"北京|上海|深圳|广州|廣州|大陆|大陸"
)
_MULTILINGUAL = re.compile(
    r"(?<![^\W\d_])(?:"
    r"chin(?:a|e|es[ea]|ois(?:e|es)?|[eê]s|[eê]sa|[eê]ses|esisch\w*)|chino(?:s)?|"
    r"prc|p[. ]r[. ]c\.?|beijing|peking|shanghai|shenzhen|guangzhou|cantonese|"
    r"taiwan(?:ese)?|taipei|formosa|cross[ -]+strait|hong[ -]*kong|macau|macao|"
    r"xinjiang|uyghurs?|uighurs?|tibet(?:an|ans)?|"
    r"sino[ -]\w+|sinophone|sinic(?:ization|isation|ize|ise)|"
    r"ccp|c[. ]c[. ]p\.?|"
    r"senkaku|diaoyu|spratlys?|paracels?|nine[ -]+dash|"
    r"dalai[ -]+lama|one[ -]+country[ -]+two[ -]+systems|"
    r"кита[йяею]|китайск\w*|тайван\w*|гонконг\w*"
    r")(?![^\W\d_])"
)
_OTHER_SCRIPTS = re.compile(r"الصين|تايوان|هونغ كونغ|التبت|شينجيانغ|대만|중국|홍콩|티베트|タイワン|香港")


def source_paused(source, rules):
    return (source['id'] in rules.get('paused_sources', ())
            or source['id'] in rules.get('hidden_sources', ())
            or source['module'] in rules.get('paused_modules', ()))


def _normalized(value):
    value = unicodedata.normalize('NFKC', unquote(value)).casefold()
    value = ''.join(character for character in unicodedata.normalize('NFKD', value)
                    if unicodedata.category(character) not in {'Mn', 'Cf'})
    return re.sub(r'[\s_‐‑‒–—−·/]+', ' ', value)


def restricted_content(value, rules):
    """Inspect full accessible text and nested metadata, independently of presentation."""
    if not rules.get('screen_china_related_materials'):
        return False
    if isinstance(value, str):
        normalized = _normalized(value)
        compact_cjk = re.sub(r'[\s.\-]+', '', normalized)
        return bool(_CJK.search(compact_cjk) or _MULTILINGUAL.search(normalized)
                    or _OTHER_SCRIPTS.search(normalized))
    if isinstance(value, dict):
        return any(restricted_content(field, rules) for field in value.values())
    if isinstance(value, (tuple, list)):
        return any(restricted_content(field, rules) for field in value)
    return False
