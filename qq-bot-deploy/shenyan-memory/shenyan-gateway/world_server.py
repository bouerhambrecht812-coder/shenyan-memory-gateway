#!/usr/bin/env python3
"""沈砚 · 世界事件 MCP 服务端（stdio 传输，零第三方依赖）

MCP 的 stdio 传输就是「一行一个 JSON-RPC 2.0 消息」，所以不需要官方 SDK。
这样做的原因：网关跑在 AstrBot 基础镜像里，那个镜像本身锁了 pydantic 版本，
引入官方 SDK 会和镜像打架；协议本身很小，自己实现反而更好测。

支持的方法：
    initialize / notifications/initialized / tools/list / tools/call / ping

工具：
    clock.now          当前时间（新加坡）、星期、时段
    weather.now        新加坡实时天气（Open-Meteo，无需 Key）
    news.headlines     头条标题（RSS，可换源）
"""
from __future__ import annotations

import json
import os
import sys
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime
from zoneinfo import ZoneInfo

PROTOCOL_VERSION = '2025-06-18'
SERVER_INFO = {'name': 'shenyan-world', 'version': '1.0.0'}

TZ = ZoneInfo(os.getenv('WORLD_TZ', 'Asia/Singapore'))
NEWS_FEED = os.getenv(
    'WORLD_NEWS_FEED',
    'https://www.channelnewsasia.com/api/v1/rss-outbound-feed?_format=xml',
)
HTTP_TIMEOUT = float(os.getenv('WORLD_HTTP_TIMEOUT', '6'))

# 新加坡默认坐标，可被工具参数覆盖
DEFAULT_LAT = 1.3521
DEFAULT_LON = 103.8198

# WMO weather code → 中文
WMO = {
    0: '晴', 1: '大致晴朗', 2: '局部多云', 3: '阴',
    45: '雾', 48: '霜雾',
    51: '小毛毛雨', 53: '毛毛雨', 55: '大毛毛雨',
    56: '冻毛毛雨', 57: '强冻毛毛雨',
    61: '小雨', 63: '中雨', 65: '大雨',
    66: '冻雨', 67: '强冻雨',
    71: '小雪', 73: '中雪', 75: '大雪', 77: '雪粒',
    80: '小阵雨', 81: '阵雨', 82: '强阵雨',
    85: '阵雪', 86: '强阵雪',
    95: '雷阵雨', 96: '雷阵雨伴小冰雹', 99: '雷阵雨伴大冰雹',
}

TOOLS = [
    {
        'name': 'clock.now',
        'description': '获取当前时间、星期和时段（新加坡时区）。用于知道现在是几点、是不是深夜。',
        'inputSchema': {'type': 'object', 'properties': {}, 'additionalProperties': False},
    },
    {
        'name': 'weather.now',
        'description': '获取某个城市当前的天气（温度、湿度、天气现象）。默认新加坡。',
        'inputSchema': {
            'type': 'object',
            'properties': {
                'city': {'type': 'string', 'description': '城市名，默认 Singapore'},
                'latitude': {'type': 'number'},
                'longitude': {'type': 'number'},
            },
            'additionalProperties': False,
        },
    },
    {
        'name': 'news.headlines',
        'description': '获取当前的新闻头条标题，可用来知道世界上正在发生什么。',
        'inputSchema': {
            'type': 'object',
            'properties': {'limit': {'type': 'integer', 'minimum': 1, 'maximum': 10}},
            'additionalProperties': False,
        },
    },
]


def part_of_day(hour: int) -> str:
    if hour < 5:
        return '凌晨'
    if hour < 9:
        return '早上'
    if hour < 12:
        return '上午'
    if hour < 14:
        return '中午'
    if hour < 18:
        return '下午'
    if hour < 22:
        return '晚上'
    return '深夜'


def tool_clock_now(_args: dict) -> str:
    now = datetime.now(TZ)
    weekdays = ['周一', '周二', '周三', '周四', '周五', '周六', '周日']
    return (
        f'{now:%Y-%m-%d} {now:%H:%M} {weekdays[now.weekday()]} {part_of_day(now.hour)}\n'
        f'时区：Asia/Singapore'
    )


def tool_weather_now(args: dict) -> str:
    city = str(args.get('city') or 'Singapore')
    lat = float(args.get('latitude', DEFAULT_LAT))
    lon = float(args.get('longitude', DEFAULT_LON))
    query = urllib.parse.urlencode({
        'latitude': lat,
        'longitude': lon,
        'current': 'temperature_2m,relative_humidity_2m,weather_code,precipitation',
        'timezone': 'Asia/Singapore',
    })
    url = f'https://api.open-meteo.com/v1/forecast?{query}'
    try:
        with urllib.request.urlopen(url, timeout=HTTP_TIMEOUT) as resp:
            data = json.loads(resp.read().decode('utf-8'))
    except Exception as ex:
        return f'{city} 天气获取失败：{type(ex).__name__}'

    cur = data.get('current') or {}
    code = cur.get('weather_code')
    text = WMO.get(code, '未知天气') if isinstance(code, int) else '未知天气'
    temp = cur.get('temperature_2m')
    hum = cur.get('relative_humidity_2m')
    rain = cur.get('precipitation')
    bits = [f'{city} 现在 {text}']
    if temp is not None:
        bits.append(f'{temp}°C')
    if hum is not None:
        bits.append(f'湿度 {hum}%')
    if rain:
        bits.append(f'降水 {rain}mm')
    return '，'.join(bits)


def tool_news_headlines(args: dict) -> str:
    limit = int(args.get('limit', 5))
    limit = max(1, min(10, limit))
    try:
        req = urllib.request.Request(NEWS_FEED, headers={'User-Agent': 'shenyan-world/1.0'})
        with urllib.request.urlopen(req, timeout=HTTP_TIMEOUT) as resp:
            raw = resp.read()
    except Exception as ex:
        return f'新闻获取失败：{type(ex).__name__}'

    try:
        root = ET.fromstring(raw)
    except Exception:
        return '新闻源返回的内容无法解析'

    items = root.findall('.//item')[:limit]
    if not items:
        return '今天没有拿到头条'
    lines = []
    for i, item in enumerate(items, 1):
        title = (item.findtext('title') or '').strip()
        if title:
            lines.append(f'{i}. {title}')
    return '\n'.join(lines) if lines else '今天没有拿到头条'


HANDLERS = {
    'clock.now': tool_clock_now,
    'weather.now': tool_weather_now,
    'news.headlines': tool_news_headlines,
}


def handle(msg: dict) -> dict | None:
    method = msg.get('method')
    msg_id = msg.get('id')

    # 通知（没有 id）不需要回复
    if msg_id is None:
        return None

    if method == 'initialize':
        return {
            'jsonrpc': '2.0', 'id': msg_id,
            'result': {
                'protocolVersion': PROTOCOL_VERSION,
                'capabilities': {'tools': {'listChanged': False}},
                'serverInfo': SERVER_INFO,
            },
        }

    if method == 'ping':
        return {'jsonrpc': '2.0', 'id': msg_id, 'result': {}}

    if method == 'tools/list':
        return {'jsonrpc': '2.0', 'id': msg_id, 'result': {'tools': TOOLS}}

    if method == 'tools/call':
        params = msg.get('params') or {}
        name = params.get('name')
        args = params.get('arguments') or {}
        handler = HANDLERS.get(name)
        if handler is None:
            return {
                'jsonrpc': '2.0', 'id': msg_id,
                'error': {'code': -32602, 'message': f'unknown tool: {name}'},
            }
        try:
            text = handler(args if isinstance(args, dict) else {})
            return {
                'jsonrpc': '2.0', 'id': msg_id,
                'result': {'content': [{'type': 'text', 'text': text}], 'isError': False},
            }
        except Exception as ex:
            return {
                'jsonrpc': '2.0', 'id': msg_id,
                'result': {
                    'content': [{'type': 'text', 'text': f'工具执行失败：{type(ex).__name__}'}],
                    'isError': True,
                },
            }

    return {
        'jsonrpc': '2.0', 'id': msg_id,
        'error': {'code': -32601, 'message': f'method not found: {method}'},
    }


def serve_stdio() -> None:
    # 注意：stdout 只用来写协议消息，日志一律走 stderr
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            msg = json.loads(line)
        except Exception:
            print('world: bad json', file=sys.stderr)
            continue
        reply = handle(msg)
        if reply is not None:
            sys.stdout.write(json.dumps(reply, ensure_ascii=False) + '\n')
            sys.stdout.flush()


if __name__ == '__main__':
    if '--list-tools' in sys.argv:
        print(json.dumps(TOOLS, ensure_ascii=False, indent=2))
    else:
        serve_stdio()
