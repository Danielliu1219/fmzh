# -*- coding: utf-8 -*-
"""诊断实验 v3（决定性）：
同一张含中文的长图，分别用【标准 base64】与【PlantUML 官方字母表】编码请求 PNG：
- 两者像素相同 → 服务器两种编码都认，68 张图编码没问题，乱码是字体问题
- 两者不同 → 我们的编码被服务器错误解码，68 张图是乱码图，换官方编码重渲染即可
另：官方编码请求 SVG，检查 SVG 里是否含中文原文（验证官方路径端到端正确）
"""
import zlib, base64, urllib.request, io, hashlib, time
from PIL import Image, ImageFilter
import numpy as np


def enc_std(s):
    d = zlib.compress(s.encode('utf-8'), 9)[2:-4]
    return base64.urlsafe_b64encode(d).decode('ascii')


def enc_plantuml(s):
    d = zlib.compress(s.encode('utf-8'), 9)[2:-4]
    out = []
    for i in range(0, len(d), 3):
        b1, b2, b3 = d[i], d[i + 1] if i + 1 < len(d) else 0, d[i + 2] if i + 2 < len(d) else 0
        c1 = b1 >> 2
        c2 = ((b1 & 0x3) << 4) | (b2 >> 4)
        c3 = ((b2 & 0xF) << 2) | (b3 >> 6)
        c4 = b3 & 0x3F
        for c in (c1, c2, c3, c4):
            if c < 10: out.append(chr(48 + c))
            elif c < 36: out.append(chr(65 + c - 10))
            elif c < 62: out.append(chr(97 + c - 36))
            elif c == 62: out.append('-')
            else: out.append('_')
    return ''.join(out)


def fetch(url, retries=2):
    for a in range(retries + 1):
        try:
            req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
            return urllib.request.urlopen(req, timeout=30).read()
        except Exception as e:
            if a == retries:
                raise
            time.sleep(2)


def edges(data):
    im = Image.open(io.BytesIO(data)).convert('L')
    e = im.filter(ImageFilter.FIND_EDGES)
    return int((np.asarray(e) > 30).sum())


HOST = 'https://www.plantuml.com/plantuml'
SRC = ('@startuml\n'
       'skinparam defaultFontName "Noto Sans CJK SC"\n'
       'start\n'
       ':注册账号登录系统复习资料;\n'
       ':压力指数情绪记录提醒通知;\n'
       ':second line;\n'
       ':third line;\n'
       'stop\n'
       '@enduml')

print('=== 同一张图 × 两种编码 × PNG ===')
res = {}
for name, fn in [('标准base64', enc_std), ('官方字母表', enc_plantuml)]:
    try:
        data = fetch(f'{HOST}/png/' + fn(SRC))
        res[name] = data
        print(f'  {name:12s} HTTP200 size={len(data):6d} edges={edges(data):6d} sha={hashlib.sha1(data).hexdigest()[:10]}')
    except Exception as e:
        print(f'  {name:12s} ERROR {e}')

if len(res) == 2:
    a, b = res['标准base64'], res['官方字母表']
    print('  → 两张图像素完全一致' if a == b else '  → 两张图【不同】！标准 base64 被服务器错误解码')

print('=== 官方编码 × SVG：检查中文是否端到端正确 ===')
try:
    data = fetch(f'{HOST}/svg/' + enc_plantuml(SRC)).decode('utf-8', 'replace')
    for key in ['注册账号登录系统复习资料', '压力指数情绪记录提醒通知']:
        print(f'  SVG 含 {key!r}:', key in data)
    import re
    print('  font-family 列表:', sorted(set(re.findall(r'font-family="([^"]+)"', data))))
except Exception as e:
    print('  ERROR', e)
