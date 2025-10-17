import os
import subprocess
import time
import requests
import sys
import winreg
import pychrome
import help  # 导入拦截模块

# ---------------- 配置 ----------------
DEBUG_PORT = 1145
DEVTOOLS_URL = f"http://127.0.0.1:{DEBUG_PORT}/json"
TARGET_HOME_PAGE = "https://tuxun.fun/"

USE_SEPARATE_PROFILE = True
USER_DATA_DIR = "dev_profile_py"  # 简化路径，默认当前目录

# 可选浏览器: "edge" 或 "chrome"
BROWSER = "edge"

browser_proc = None  # 浏览器进程全局变量

# ---------------- 函数 ----------------
def find_browser_path(browser_name="edge"):
    """从注册表查找 Edge 或 Chrome 的安装路径"""
    browser_name = browser_name.lower()
    if browser_name == "edge":
        exe_name = "msedge.exe"
    elif browser_name == "chrome":
        exe_name = "chrome.exe"
    else:
        return None

    keys = [
        (winreg.HKEY_LOCAL_MACHINE, fr"SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\{exe_name}"),
        (winreg.HKEY_CURRENT_USER, fr"SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\{exe_name}"),
        (winreg.HKEY_LOCAL_MACHINE, fr"SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\App Paths\{exe_name}")
    ]

    for hive, sub in keys:
        try:
            with winreg.OpenKey(hive, sub) as k:
                path, _ = winreg.QueryValueEx(k, None)
                if path and os.path.isfile(path):
                    return path
        except FileNotFoundError:
            continue

    return None


def start_browser(browser_path):
    """启动带调试功能的浏览器"""
    cmd = [browser_path, f"--remote-debugging-port={DEBUG_PORT}"]
    if USE_SEPARATE_PROFILE:
        os.makedirs(USER_DATA_DIR, exist_ok=True)
        cmd += [f"--user-data-dir={os.path.abspath(USER_DATA_DIR)}", "--no-first-run", "--disable-extensions"]
    return subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def wait_devtools(timeout=10.0):
    """等待DevTools就绪"""
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            resp = requests.get(DEVTOOLS_URL, timeout=1.0)
            if resp.status_code == 200:
                return resp.json()
        except:
            pass
        time.sleep(0.2)
    raise TimeoutError("DevTools未就绪")


def cleanup():
    """退出时清理浏览器进程"""
    global browser_proc
    if browser_proc:
        try:
            browser_proc.terminate()
            browser_proc.wait(2)
        except:
            try:
                browser_proc.kill()
            except:
                pass


# ---------------- 主程序 ----------------
def main():
    global browser_proc
    browser_path = find_browser_path(BROWSER) or sys.exit(f"❌ 未找到 {BROWSER}，请确认已安装")

    print(f"✅ 找到并启动 {BROWSER}: {browser_path}")
    browser_proc = start_browser(browser_path)

    try:
        tabs = wait_devtools(15)
    except TimeoutError as e:
        print(f"❌ 超时: {e}")
        return cleanup()

    print(f"✅ DevTools就绪，{len(tabs)}个标签页")
    browser = pychrome.Browser(url=f"http://127.0.0.1:{DEBUG_PORT}")
    tab = browser.list_tab()[0]
    tab.start()
    tab.call_method("Network.enable")

    print(f"🌐 打开主页：{TARGET_HOME_PAGE}")
    tab.call_method("Page.navigate", url=TARGET_HOME_PAGE)
    time.sleep(2)

    help.init_handler(browser, tab, browser_path)
    tab.set_listener("Network.responseReceived", help.on_response_received)

    print("✅ 就绪，按Ctrl+C退出")
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("🛑 用户中断")
    finally:
        tab.stop()
        cleanup()


if __name__ == "__main__":
    main()
