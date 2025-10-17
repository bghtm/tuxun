import json
import base64
import re
import subprocess
import traceback

# 常量定义
CHINA_URL = "tuxun.fun/api/v0/tuxun/mapProxy/getPanoInfo"
GLOBAL_URL = "tile.chao-fan.com/$rpc/google.internal.maps.mapsjs.v1.MapsJsInternalService/GetMetadata"
GEOCODE_URL = "https://www.google.com/maps/search/{lat},{lng}/"

# 全局变量
browser = tab = edge_path = logger = None
last_coords = [None, None]


def init_handler(_browser, _tab, _edge_path, _logger):
    """由主程序注入依赖与日志"""
    global browser, tab, edge_path, logger
    browser, tab, edge_path, logger = _browser, _tab, _edge_path, _logger
    logger.info("✅ 拦截模块初始化完成。")


def _safe_get_response_body(reqid: str):
    """安全地获取响应体"""
    try:
        result = tab.call_method("Network.getResponseBody", requestId=reqid)
        body = result.get("body", "")
        if result.get("base64Encoded"):
            body = base64.b64decode(body).decode(errors="ignore")
        return body
    except Exception as e:
        logger.warning(f"⚠️ Network.getResponseBody 调用失败: {e}")
        return None



def _handle_coords(lat, lng, source):
    """统一坐标处理逻辑"""
    global last_coords, edge_path, logger
    if not lat or not lng:
        logger.warning(f"⚠️ {source}: 坐标为空，跳过。")
        return

    try:
        lat, lng = float(lat), float(lng)
    except Exception:
        logger.warning(f"⚠️ {source}: 坐标格式异常：{lat}, {lng}")
        return

    if (lat, lng) != tuple(last_coords):
        last_coords[:] = [lat, lng]
        query_url = GEOCODE_URL.format(lat=lat, lng=lng)
        logger.info(f"🆕 [{source}] 新坐标：{lat}, {lng}")
        logger.info(f"➡️ 打开：{query_url}")
        subprocess.Popen([edge_path, query_url])
    else:
        logger.debug(f"⚪ [{source}] 坐标未变化：{lat}, {lng}")


def on_response_received(**params):
    """统一处理 Tuxun 与 Chao-Fan 请求"""
    global logger

    try:
        resp = params.get("response", {})
        url = resp.get("url", "")
        reqid = params.get("requestId")

        # ---------- 处理 CHINA_URL ----------
        if CHINA_URL in url:
            logger.info(f"🌐 捕获到 China 请求：{url}")
            try:
                body = _safe_get_response_body(reqid)
                data = json.loads(body)
                lat = data.get("data", {}).get("bd09Lat")
                lng = data.get("data", {}).get("bd09Lng")
                _handle_coords(lat, lng, "China")
            except json.JSONDecodeError:
                logger.error("❌ China 响应不是合法 JSON。")
            except Exception as e:
                logger.error(f"❌ China 解析失败: {e}")
                logger.debug(traceback.format_exc())
            return

        # ---------- 处理 GLOBAL_URL ----------
        if GLOBAL_URL in url:
            logger.info(f"📡 捕获到 Global 响应：{url}")
            try:
                body = _safe_get_response_body(reqid)
                coords = re.findall(r"-?\d+\.\d{5,}", body)
                if len(coords) >= 2:
                    _handle_coords(coords[0], coords[1], "Global")
                else:
                    logger.warning("⚠️ Global: 未检测到有效经纬度。")
            except Exception as e:
                logger.error(f"❌ Global 解析失败: {e}")
                logger.debug(traceback.format_exc())

    except Exception as e:
        # 兜底防止监听中断
        if logger:
            logger.critical(f"🔥 on_response_received 未捕获异常: {e}")
            logger.debug(traceback.format_exc())
        else:
            print("on_response_received 异常:", e)
