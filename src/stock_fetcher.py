"""
行情数据获取模块 - 使用新浪财经API获取实时行情
通过新浪财经HTTP接口获取数据，稳定可靠，支持批量查询
备用：腾讯财经接口
"""
import threading
import re
import requests
import time
from datetime import datetime

# 请求超时时间（秒）— 分连接和读取
CONNECT_TIMEOUT = 3
READ_TIMEOUT = 5
TIMEOUT = (CONNECT_TIMEOUT, READ_TIMEOUT)  # 元组: (连接超时, 读取超时)

# 最大重试次数
MAX_RETRIES = 3
RETRY_DELAY = 0.5  # 重试间隔秒

# 请求头
HEADERS = {
    'Referer': 'https://finance.sina.com.cn',
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
}

# 腾讯请求头
TENCENT_HEADERS = {
    'Referer': 'https://gu.qq.com/',
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
}


class StockFetcher:
    """行情数据获取器 - 基于新浪/腾讯财经API"""

    def __init__(self):
        self._lock = threading.Lock()
        self._name_cache = {}

    def _get_market_prefix(self, code):
        """
        根据代码判断市场前缀
        新浪格式: sh600519, sz000001
        """
        code = code.strip()
        if code.startswith('6'):
            return 'sh', code  # 沪市
        elif code.startswith('0') or code.startswith('3'):
            return 'sz', code  # 深市
        elif code.startswith('8') or code.startswith('4'):
            return 'bj', code  # 北交所
        else:
            return 'sz', code  # 默认深市

    def get_stock_info(self, code):
        """
        获取单只标的实时信息
        """
        results = self.get_stocks_info([code])
        if results:
            return results[0]
        return self._error_result(code, "获取失败")

    def get_stocks_info(self, codes):
        """
        批量获取多只标的信息
        使用新浪财经接口，一次性查询多只标的
        """
        if not codes:
            return []

        try:
            # 构建新浪查询字符串
            sina_codes = []
            code_map = {}  # 前缀+code -> 原始code
            for code in codes:
                prefix, stock_code = self._get_market_prefix(code)
                sina_code = f"{prefix}{stock_code}"
                sina_codes.append(sina_code)
                code_map[sina_code] = code

            # 新浪接口URL — 优先用HTTP，避免HTTPS超时
            # 尝试多个域名，依次重试
            urls = [
                f"http://hq.sinajs.cn/list={','.join(sina_codes)}",
                f"https://hq.sinajs.cn/list={','.join(sina_codes)}",
                f"http://money.sinajs.cn/list={','.join(sina_codes)}",
            ]

            resp = None
            last_err = None
            for url in urls:
                for attempt in range(MAX_RETRIES):
                    try:
                        session = requests.Session()
                        session.headers.update(HEADERS)
                        resp = session.get(url, timeout=TIMEOUT)
                        resp.encoding = 'gbk'
                        if resp.status_code == 200 and resp.text.strip():
                            break
                        last_err = f"HTTP {resp.status_code}"
                    except Exception as e:
                        last_err = e
                        time.sleep(RETRY_DELAY)
                if resp and resp.status_code == 200 and resp.text.strip():
                    break

            if not resp or not resp.text.strip():
                raise requests.exceptions.ConnectionError(f"所有新浪接口均失败: {last_err}")

            results = []
            # 解析返回数据
            # 格式: var hq_str_sh600519="贵州茅台,1800.000,1799.000,1805.000,..."
            lines = resp.text.strip().split('\n')

            for line in lines:
                line = line.strip()
                if not line:
                    continue

                try:
                    # 提取代码和名称
                    match = re.match(r'var hq_str_(\w+)="(.*)"', line)
                    if not match:
                        continue

                    sina_code = match.group(1)
                    content = match.group(2)

                    if not content:
                        # 空数据
                        orig_code = code_map.get(sina_code, sina_code)
                        results.append(self._error_result(orig_code, "无数据"))
                        continue

                    fields = content.split(',')

                    # 新浪行情数据字段（A股）:
                    # 0:名称, 1:今开, 2:昨收, 3:最新价, 4:最高, 5:最低, 6:买1, 7:卖1
                    # 8:成交量(股), 9:成交额, ... 30:日期, 31:时间
                    name = fields[0]
                    open_price = self._safe_float(fields[1])
                    pre_close = self._safe_float(fields[2])
                    price = self._safe_float(fields[3])
                    high = self._safe_float(fields[4])
                    low = self._safe_float(fields[5])
                    volume = self._safe_int(fields[8])
                    amount = self._safe_float(fields[9])
                    date_str = fields[30] if len(fields) > 30 else ""
                    time_str = fields[31] if len(fields) > 31 else ""

                    # 涨跌幅计算
                    if pre_close and pre_close > 0:
                        change_pct = (price - pre_close) / pre_close * 100
                        change_amt = price - pre_close
                    else:
                        change_pct = 0.0
                        change_amt = 0.0

                    orig_code = code_map.get(sina_code, sina_code)

                    # 缓存名称
                    self._name_cache[orig_code] = name

                    results.append({
                        'code': orig_code,
                        'name': name,
                        'price': price,
                        'change_pct': round(change_pct, 2),
                        'change_amt': round(change_amt, 3),
                        'high': high,
                        'low': low,
                        'open': open_price,
                        'pre_close': pre_close,
                        'volume': volume,
                        'amount': amount,
                        'date': date_str,
                        'time': time_str,
                        'valid': True if price and price > 0 else False
                    })

                except Exception as e:
                    print(f"[Fetcher] 解析数据失败: {e}, line: {line[:50]}")
                    orig_code = code_map.get(sina_code, '')
                    results.append(self._error_result(orig_code, str(e)))

            # 确保返回数量与输入一致
            while len(results) < len(codes):
                results.append(self._error_result(codes[len(results)], "解析失败"))

            return results

        except requests.exceptions.ConnectionError:
            # 网络错误，尝试腾讯接口
            print("[Fetcher] 新浪接口连接失败，尝试腾讯接口...")
            return self._fetch_from_tencent(codes)
        except Exception as e:
            print(f"[Fetcher] 新浪接口获取失败: {e}")
            # 尝试腾讯接口
            try:
                return self._fetch_from_tencent(codes)
            except Exception as e2:
                print(f"[Fetcher] 腾讯接口也失败: {e2}")
                return [self._error_result(c, str(e2)) for c in codes]

    def _fetch_from_tencent(self, codes):
        """腾讯财经接口作为备用"""
        results = []
        try:
            # 构建腾讯查询字符串
            tencent_codes = []
            code_map = {}
            for code in codes:
                prefix, stock_code = self._get_market_prefix(code)
                # 腾讯格式: s_sh600519, s_sz000001
                tencent_code = f"s_{prefix}{stock_code}"
                tencent_codes.append(tencent_code)
                code_map[tencent_code] = code

            # 腾讯接口 — 也尝试HTTP + HTTPS，加重试
            urls = [
                f"http://qt.gtimg.cn/q={','.join(tencent_codes)}",
                f"https://qt.gtimg.cn/q={','.join(tencent_codes)}",
            ]

            resp = None
            last_err = None
            for url in urls:
                for attempt in range(MAX_RETRIES):
                    try:
                        resp = requests.get(url, timeout=TIMEOUT, headers=TENCENT_HEADERS)
                        resp.encoding = 'gbk'
                        if resp.status_code == 200 and resp.text.strip():
                            break
                        last_err = f"HTTP {resp.status_code}"
                    except Exception as e:
                        last_err = e
                        time.sleep(RETRY_DELAY)
                if resp and resp.status_code == 200 and resp.text.strip():
                    break

            if not resp or not resp.text.strip():
                raise Exception(f"腾讯接口均失败: {last_err}")

            lines = resp.text.strip().split(';')

            for line in lines:
                line = line.strip()
                if not line:
                    continue

                try:
                    match = re.match(r'v_s_(\w+)="(.*)"', line)
                    if not match:
                        continue

                    tencent_code = match.group(1)
                    content = match.group(2)

                    if not content:
                        orig_code = code_map.get(f"s_{tencent_code}", tencent_code)
                        results.append(self._error_result(orig_code, "无数据"))
                        continue

                    fields = content.split('~')
                    # 腾讯简版行情:
                    # 0:代码, 1:名称, 2:最新价, 3:昨收, 4:今开, 5:成交量(手)
                    # 6:涨跌额, 7:涨跌幅, ... 31:最高, 32:最低

                    name = fields[1] if len(fields) > 1 else ''
                    price = self._safe_float(fields[2]) if len(fields) > 2 else 0
                    pre_close = self._safe_float(fields[3]) if len(fields) > 3 else 0
                    open_price = self._safe_float(fields[4]) if len(fields) > 4 else 0
                    change_amt = self._safe_float(fields[6]) if len(fields) > 6 else 0
                    change_pct = self._safe_float(fields[7]) if len(fields) > 7 else 0
                    high = self._safe_float(fields[31]) if len(fields) > 31 else 0
                    low = self._safe_float(fields[32]) if len(fields) > 32 else 0
                    volume = self._safe_int(fields[5]) if len(fields) > 5 else 0

                    orig_code = code_map.get(f"s_{tencent_code}", tencent_code)
                    self._name_cache[orig_code] = name

                    results.append({
                        'code': orig_code,
                        'name': name,
                        'price': price,
                        'change_pct': round(change_pct, 2),
                        'change_amt': round(change_amt, 3),
                        'high': high,
                        'low': low,
                        'open': open_price,
                        'pre_close': pre_close,
                        'volume': volume,
                        'amount': 0.0,
                        'valid': True if price and price > 0 else False
                    })

                except Exception as e:
                    print(f"[Fetcher] 腾讯数据解析失败: {e}")
                    results.append(self._error_result(code, str(e)))

            while len(results) < len(codes):
                results.append(self._error_result(codes[len(results)], "解析失败"))

            return results

        except Exception as e:
            print(f"[Fetcher] 腾讯接口也失败: {e}")
            return [self._error_result(c, str(e)) for c in codes]

    def _safe_float(self, val):
        """安全转换为float"""
        try:
            v = float(val)
            return v if v == v else 0.0  # 检查NaN
        except (ValueError, TypeError):
            return 0.0

    def _safe_int(self, val):
        """安全转换为int"""
        try:
            return int(float(val))
        except (ValueError, TypeError):
            return 0

    def _error_result(self, code, error_msg=""):
        """生成错误结果"""
        name = self._name_cache.get(code, code)
        return {
            'code': code,
            'name': name,
            'price': 0.0,
            'change_pct': 0.0,
            'change_amt': 0.0,
            'high': 0.0,
            'low': 0.0,
            'open': 0.0,
            'pre_close': 0.0,
            'volume': 0,
            'amount': 0.0,
            'valid': False,
            'error': error_msg
        }

    def clear_cache(self):
        """清除缓存"""
        with self._lock:
            self._name_cache.clear()


# 单例模式
_stock_fetcher = None


def get_stock_fetcher():
    global _stock_fetcher
    if _stock_fetcher is None:
        _stock_fetcher = StockFetcher()
    return _stock_fetcher
