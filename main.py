import os
import subprocess
import time
import requests
import atexit
import sys
import tempfile
import winreg
import logging
import pychrome

import help  # 导入拦截模块

# ---------------- 配置部分 ----------------
DEBUG_PORT = 9222
DEVTOOLS_URL = f"http://127.0.0.1:{DEBUG_PORT}/json"
TARGET_HOME_PAGE = "https://tuxun.fun/"
USE_SEPARATE_PROFILE = True
USER_DATA_DIR = os.path.abspath(os.path.join(tempfile.gettempdir(), "edge_dev_profile_py"))
LOG_DIR = os.path.join(os.getcwd(), "logs")
LOG_FILE = os.path.join(LOG_DIR, "runtime.log")
# ------------------------------------------------


# =============== 日志系统初始化 ===============
def setup_logger():
    os.makedirs(LOG_DIR, exist_ok=True)
    logger = logging.getLogger("EdgeInterceptor")
    logger.setLevel(logging.DEBUG)

    # 控制台输出
    ch = logging.StreamHandler()
    ch.setLevel(logging.DEBUG)
    ch.setFormatter(logging.Formatter("[%(asctime)s] [%(levelname)s] %(message)s", "%H:%M:%S"))

    # 文件保存
    fh = logging.FileHandler(LOG_FILE, encoding="utf-8")
    fh.setLevel(logging.DEBUG)
    fh.setFormatter(logging.Formatter("[%(asctime)s] [%(levelname)s] %(message)s", "%Y-%m-%d %H:%M:%S"))

    logger.addHandler(ch)
    logger.addHandler(fh)

    logger.info("📄 日志系统已初始化，日志保存至 logs/runtime.log")
    return logger


logger = setup_logger()
# =============================================


def find_msedge_path():
    """从注册表查找 Edge 可执行路径"""
    keys = [
        (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\msedge.exe"),
        (winreg.HKEY_CURRENT_USER,  r"SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\msedge.exe"),
        (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\App Paths\msedge.exe")
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


def start_edge(msedge_path):
    """启动带 remote debugging 的 Edge"""
    if USE_SEPARATE_PROFILE:
        os.makedirs(USER_DATA_DIR, exist_ok=True)
    cmd = [msedge_path, f"--remote-debugging-port={DEBUG_PORT}"]
    if USE_SEPARATE_PROFILE:
        cmd += [f"--user-data-dir={USER_DATA_DIR}", "--no-first-run", "--disable-extensions"]
    proc = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return proc


def wait_devtools(timeout=10.0):
    """等待 Edge DevTools 接口就绪"""
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            r = requests.get(DEVTOOLS_URL, timeout=1.0)
            if r.status_code == 200:
                return r.json()
        except requests.RequestException:
            pass
        time.sleep(0.2)
    raise TimeoutError("DevTools endpoint 未在指定时间内就绪")


# Edge 进程全局变量
edge_proc = None
def cleanup():
    """退出时关闭 Edge"""
    global edge_proc
    if edge_proc:
        try:
            edge_proc.terminate()
            edge_proc.wait(timeout=2)
        except Exception:
            try:
                edge_proc.kill()
            except Exception:
                pass
atexit.register(cleanup)


def main():
    global edge_proc
    msedge = find_msedge_path()
    if not msedge:
        logger.error("❌ 未在注册表中找到 msedge.exe，请确认 Edge 已安装。")
        sys.exit(1)

    logger.info(f"✅ 找到 Edge: {msedge}")
    logger.info("🚀 启动 Edge（带 remote debugging）...")
    edge_proc = start_edge(msedge)

    try:
        tabs = wait_devtools(timeout=15.0)
    except TimeoutError as e:
        logger.error(f"等待 DevTools 超时: {e}")
        cleanup()
        sys.exit(1)

    logger.info(f"DevTools 已就绪，共 {len(tabs)} 个标签页。")
    browser = pychrome.Browser(url=f"http://127.0.0.1:{DEBUG_PORT}")

    tab = browser.list_tab()[0]
    tab.start()
    tab.call_method("Network.enable")

    logger.info(f"🌐 自动打开主页：{TARGET_HOME_PAGE}")
    tab.call_method("Page.navigate", url=TARGET_HOME_PAGE)
    time.sleep(2)

    # 初始化 handler
    help.init_handler(browser, tab, msedge, logger)
    tab.set_listener("Network.responseReceived", help.on_response_received)

    logger.info(f"✅ 已附加到 {TARGET_HOME_PAGE}，触发请求后会输出结果。按 Ctrl+C 退出。")
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        logger.info("🛑 用户中断退出。")
    finally:
        tab.stop()
        cleanup()


if __name__ == "__main__":
    main()
