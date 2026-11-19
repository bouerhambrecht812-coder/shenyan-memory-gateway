#!/usr/bin/env python3
"""双击用的启动器（.py 版本）。

为什么不是 .bat：Windows 11 的智能应用控制（Smart App Control）在强制模式下
会按文件类型拦掉 .bat / .ps1，就算文件是本机生成的也一样。
.py 只是数据文件，真正被检查的是 python.exe，它带有效签名，能过。

    python start-demo.py          演示模式，不调用模型
    python start-demo.py --live   用真的 DeepSeek（会问你要 Key）
"""
import getpass
import os
import subprocess
import sys
import time
import urllib.request
import webbrowser
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
RUNTIME = HERE / '.runtime'
DATA = HERE / '.local-data'
GATEWAY_DIR = HERE / 'shenyan-gateway'
WEB_DIR = REPO / 'web-demo'

GATEWAY_PORT = 8000
WEB_PORT = 8080
SECRET_FILE = DATA / 'secret.env'


def free_port(port: int) -> None:
    """上一次没关干净时，端口还被占着。先收掉，否则报错让人一头雾水。"""
    try:
        out = subprocess.run(['netstat', '-ano', '-p', 'TCP'],
                             capture_output=True, text=True, timeout=10).stdout
    except Exception:
        return
    pids = set()
    for line in out.splitlines():
        parts = line.split()
        if len(parts) >= 5 and parts[1].endswith(f':{port}') and parts[3].upper() == 'LISTENING':
            pids.add(parts[4])
    for pid in pids:
        if pid.isdigit() and int(pid) != os.getpid():
            print(f'  端口 {port} 被进程 {pid} 占着，先关掉它')
            subprocess.run(['taskkill', '/F', '/PID', pid], capture_output=True)
    if pids:
        time.sleep(1)


def wait_http(url, seconds=40):
    deadline = time.time() + seconds
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=2) as r:
                if r.status == 200:
                    return True
        except Exception:
            time.sleep(0.4)
    return False


def load_saved_key() -> str:
    if not SECRET_FILE.exists():
        return ''
    try:
        for line in SECRET_FILE.read_text(encoding='utf-8').splitlines():
            if line.startswith('DEEPSEEK_API_KEY='):
                return line.split('=', 1)[1].strip()
    except Exception:
        pass
    return ''


def save_key(key: str) -> None:
    try:
        SECRET_FILE.parent.mkdir(parents=True, exist_ok=True)
        SECRET_FILE.write_text(f'DEEPSEEK_API_KEY={key}\n', encoding='utf-8')
        print(f'  Key 已保存到 {SECRET_FILE}')
        print('  （明文存在本机，只在这台电脑上，不会被上传）')
    except Exception as ex:
        print(f'  保存失败（不影响这次使用）：{ex}')


def ask_key() -> str:
    print()
    print('需要 DeepSeek 的 API Key。')
    print('去 https://platform.deepseek.com 登录 → API keys → 创建一个，复制下来。')
    print()
    try:
        key = getpass.getpass('粘贴 Key 后回车（输入时不显示，是正常的）: ').strip()
    except Exception:
        key = input('粘贴 Key 后回车: ').strip()
    if not key:
        return ''
    if not key.startswith('sk-'):
        print('  这看起来不像 DeepSeek 的 Key（一般以 sk- 开头），先按你填的试。')
    try:
        ans = input('要保存下来，下次不用再输吗？(Y/n) ').strip().lower()
    except Exception:
        ans = 'n'
    if ans in ('', 'y', 'yes'):
        save_key(key)
    return key


def build_env(key: str) -> dict:
    env = os.environ.copy()
    env.update({
        'PYTHONPATH': str(RUNTIME) + os.pathsep + env.get('PYTHONPATH', ''),
        'DATA_DIR': str(DATA),
        'PERSONA_DIR': str(HERE / 'shenyan-persona'),
        'ASSETS_DIR': str(HERE / 'shenyan-assets'),
        'GATEWAY_KEY': 'dev-local-key',
        'DEMO_MODE': '1',
        'DEMO_PASSCODE': '',
        'DEMO_EXTRACT_EVERY': '2',
        'WORLD_CONTEXT_TOOLS': 'clock.now,weather.now',
        'TZ': 'Asia/Singapore',
        'GATEWAY_URL': f'http://127.0.0.1:{GATEWAY_PORT}',
        'PYTHONIOENCODING': 'utf-8',
        'PYTHONUNBUFFERED': '1',
    })
    if key:
        env['DEEPSEEK_API_KEY'] = key
        env.pop('SHENYAN_MOCK', None)
    else:
        env['SHENYAN_MOCK'] = '1'
    return env


def tail(path: Path, n=20) -> str:
    try:
        lines = path.read_text(encoding='utf-8', errors='replace').splitlines()
        return '\n'.join(lines[-n:])
    except Exception:
        return '(读不到日志)'


def main() -> int:
    live = '--live' in sys.argv

    if not RUNTIME.exists() or not (RUNTIME / 'uvicorn').exists():
        print('依赖还没装好。先运行一次安装脚本：')
        print(f'  {HERE}\\scripts\\run-local.ps1')
        return 1

    DATA.mkdir(parents=True, exist_ok=True)

    print('=' * 58)
    print('  沈砚记忆网关 · 本地演示')
    print('=' * 58)

    key = ''
    if live:
        key = os.environ.get('DEEPSEEK_API_KEY', '').strip() or load_saved_key()
        if key:
            print()
            print('  用已保存的 Key，接真模型。')
        else:
            key = ask_key()
        if not key:
            print()
            print('  没给 Key，这次先用演示模式（回复是固定话术）。')
            live = False
    else:
        print()
        print('  演示模式：不调用模型，回复是固定话术。')
        print('  想看真模型，用「启动沈砚演示（真模型）」那个图标。')

    env = build_env(key if live else '')
    print()

    free_port(GATEWAY_PORT)
    free_port(WEB_PORT)

    glog = DATA / 'gateway.log'
    wlog = DATA / 'web.log'
    procs = []

    try:
        mode = '真模型' if live else '演示模式'
        print(f'启动网关（{mode}）...')
        g = subprocess.Popen(
            [sys.executable, '-m', 'uvicorn', 'app:app',
             '--host', '127.0.0.1', '--port', str(GATEWAY_PORT), '--workers', '1'],
            cwd=str(GATEWAY_DIR), env=env,
            stdout=open(glog, 'w', encoding='utf-8'), stderr=subprocess.STDOUT,
        )
        procs.append(g)

        if not wait_http(f'http://127.0.0.1:{GATEWAY_PORT}/healthz'):
            print()
            print('网关没起来。日志最后几行：')
            print(tail(glog))
            return 1
        print('  网关 OK')

        print('启动网页...')
        w = subprocess.Popen(
            [sys.executable, '-m', 'uvicorn', 'proxy.server:app',
             '--host', '127.0.0.1', '--port', str(WEB_PORT), '--workers', '1'],
            cwd=str(WEB_DIR), env=env,
            stdout=open(wlog, 'w', encoding='utf-8'), stderr=subprocess.STDOUT,
        )
        procs.append(w)

        if not wait_http(f'http://127.0.0.1:{WEB_PORT}/healthz'):
            print()
            print('网页没起来。日志最后几行：')
            print(tail(wlog))
            return 1

        url = f'http://127.0.0.1:{WEB_PORT}'
        print()
        print('  ' + '=' * 52)
        print(f'   打开：{url}')
        print('  ' + '=' * 52)
        print()
        print('  这个窗口别关，关了网页就打不开了。')
        print('  看完按 Ctrl+C，或者直接关掉这个窗口。')
        print()
        webbrowser.open(url)

        while True:
            if g.poll() is not None:
                print('网关退出了，日志：')
                print(tail(glog))
                return 1
            if w.poll() is not None:
                print('网页服务退出了，日志：')
                print(tail(wlog))
                return 1
            time.sleep(1)

    except KeyboardInterrupt:
        print()
        print('正在停止...')
        return 0

    finally:
        for p in procs:
            try:
                p.terminate()
            except Exception:
                pass
        time.sleep(0.5)
        for p in procs:
            try:
                p.kill()
            except Exception:
                pass
        try:
            subprocess.run(
                ['taskkill', '/F', '/FI', 'WINDOWTITLE eq *world_server*'],
                capture_output=True,
            )
        except Exception:
            pass


if __name__ == '__main__':
    try:
        sys.exit(main())
    except Exception as ex:
        print()
        print(f'出错了：{type(ex).__name__}: {ex}')
        try:
            input('按回车关闭...')
        except Exception:
            pass
        sys.exit(1)
