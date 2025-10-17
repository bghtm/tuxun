import json
import requests
import re
import subprocess
import traceback
import base64

CHINA_URL = "tuxun.fun/api/v0/tuxun/mapProxy/getPanoInfo"
GLOBAL_URL = "tile.chao-fan.com/$rpc/google.internal.maps.mapsjs.v1.MapsJsInternalService/GetMetadata"

GEOCODE_URL = "https://www.google.com/maps/search/{lat},{lng}/"
#GEOCODE_URL = "https://uri.amap.com/marker?position={lng},{lat}"
#GEOCODE_URL = "https://api.map.baidu.com/marker?location={lat},{lng}&output=html"


# 全局变量
browser = tab = edge_path  = None
last_coords = [None, None]


def init_handler(_browser, _tab, _edge_path):
    """由主程序注入依赖与打印函数"""
    global browser, tab, edge_path
    browser, tab, edge_path = _browser, _tab, _edge_path
    print("✅ 拦截模块初始化完成。")


def _safe_get_response_body(reqid: str):
    """
    安全地获取响应体。
    - 如果 requestId 无效或请求已完成导致无法获取 body，则返回 None。
    - 自动处理 base64 编码。
    """
    try:
        result = tab.call_method("Network.getResponseBody", requestId=reqid)
        if not result:
            print(f"⚠️ Network.getResponseBody 返回空结果，requestId={reqid}")
            return None

        body = result.get("body")
        if body is None:
            print(f"⚠️ Network.getResponseBody body 为空，requestId={reqid}")
            return None

        if result.get("base64Encoded"):
            try:
                body = base64.b64decode(body).decode(errors="ignore")
            except Exception as e:
                print(f"⚠️ base64 解码失败: {e}")
                return None

        return body

    except Exception as e:
        print(f"⚠️ Network.getResponseBody 调用失败: {e}")
        return None


def _handle_coords(lat, lng, source):
    """统一坐标处理逻辑"""
    global last_coords, edge_path, print
    if not lat or not lng:
        print(f"⚠️ {source}: 坐标为空，跳过。")
        return

    try:
        lat, lng = float(lat), float(lng)
    except Exception:
        print(f"⚠️ {source}: 坐标格式异常：{lat}, {lng}")
        return

    if (lat, lng) != tuple(last_coords):
        last_coords[:] = [lat, lng]
        query_url = GEOCODE_URL.format(lat=lat, lng=lng)
        print(f"🆕 [{source}] 新坐标：{lat}, {lng}")
        print(f"➡️ 打开：{query_url}")
        subprocess.Popen([edge_path, query_url])
    else:
        print(f"⚪ [{source}] 坐标未变化：{lat}, {lng}")


def on_response_received(**params):
    """统一处理 China 与 Global 请求"""
    try:
        resp = params.get("response", {})
        url = resp.get("url", "")
        reqid = params.get("requestId")

        # ---------- 处理 CHINA_URL ----------
        if CHINA_URL in url:
            print(f"🌐 捕获到 China 请求：{url}")
            try:
                body = requests.get(url).text
                print(f"🗒 获取返回数据：{body}")
                data = json.loads(body)
                lat = data.get("data", {}).get("bd09Lat")
                lng = data.get("data", {}).get("bd09Lng")
                _handle_coords(lat, lng, "China")
            except json.JSONDecodeError:
                print(f"❌ {url} 响应不是合法 JSON。")
            except Exception as e:
                print(f"❌ {url} 解析失败: {e}")
                print(traceback.format_exc())
            return

        # ---------- 处理 GLOBAL_URL ----------
        if GLOBAL_URL in url:
            print(f"📡 捕获到 Global 响应：{url}")
            try:
                body = _safe_get_response_body(reqid)
                if not body:
                    print(f"⚠️ {url}: 响应体为空，跳过 Global 解析")
                    return
                print(f"🗒 获取返回数据：{body}")

                coords = re.findall(r"-?\d+\.\d{5,}", body)
                if len(coords) >= 2:
                    _handle_coords(coords[0], coords[1], "Global")
                else:
                    print("⚠️ Global: 未检测到有效经纬度。")
            except Exception as e:
                print(f"❌ Global 解析失败: {e}")
                print(traceback.format_exc())

    except Exception as e:
        # 兜底防止监听中断
        print("🔥 on_response_received 未捕获异常:", e)
        print(traceback.format_exc())
