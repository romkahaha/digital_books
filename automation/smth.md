In this diff I have modified the existing fetching to use async client
and introduced an api which provides residential ips to scrape items from steam market
concurrently. If you are going to apply similar changes to another repo, use this as an example/guideline.
Before actual scraping don't forget to check which ips are not banned by steam and set up correct timeouts.



diff --git a/base_screening_and_anal/check_fetchers.py b/base_screening_and_anal/check_fetchers.py
new file mode 100644
index 0000000..a0f232c
--- /dev/null
+++ b/base_screening_and_anal/check_fetchers.py
@@ -0,0 +1,68 @@
+from __future__ import annotations
+
+import argparse
+from pathlib import Path
+
+from fetchers import _csfloat_api_keys, fetch_all_prices
+
+
+DEFAULT_ITEMS = [
+    "AK-47 | Redline (Field-Tested)",
+    "AWP | Asiimov (Field-Tested)",
+]
+
+
+def build_parser() -> argparse.ArgumentParser:
+    parser = argparse.ArgumentParser(
+        description="Minimal Steam + CSFloat smoke-test for fetchers.py"
+    )
+    parser.add_argument("items", nargs="*", default=DEFAULT_ITEMS, help="market_hash_name items")
+    parser.add_argument("--csv", type=Path, help="Optional output CSV path")
+    parser.add_argument("--steam-delay", type=float, default=1.5, help="Base Steam delay in seconds")
+    parser.add_argument("--float-delay", type=float, default=1.5, help="Base CSFloat delay in seconds")
+    parser.add_argument("--steam-concurrency", type=int, default=4, help="Max in-flight Steam requests")
+    parser.add_argument("--float-concurrency", type=int, default=2, help="Max in-flight CSFloat requests")
+    parser.add_argument("--steam-currency", type=int, default=1, help="Steam currency id, default USD=1")
+    parser.add_argument("--steam-fetch-eur-also", action="store_true", help="Also fetch EUR cross-check column")
+    parser.add_argument("--prices-in-eur", action="store_true", help="Convert Float USD values into EUR")
+    parser.add_argument(
+        "--sync",
+        action="store_true",
+        help="Force legacy requests/threading path instead of aiohttp async mode",
+    )
+    return parser
+
+
+def main() -> None:
+    args = build_parser().parse_args()
+    keys_present = _csfloat_api_keys()
+    if not keys_present:
+        print(
+            "CSFloat API key is not configured. Fill `fetchers.env` from `fetchers.env.example` "
+            "or export `CSFLOAT_API_KEY` first."
+        )
+    df = fetch_all_prices(
+        list(args.items),
+        steam_delay=args.steam_delay,
+        float_delay=args.float_delay,
+        float_workers=args.float_concurrency,
+        steam_currency=args.steam_currency,
+        steam_fetch_eur_also=args.steam_fetch_eur_also,
+        prices_in_eur=args.prices_in_eur,
+        steam_concurrency=args.steam_concurrency,
+        float_concurrency=args.float_concurrency,
+        use_async=not args.sync,
+    )
+    if args.csv:
+        args.csv.parent.mkdir(parents=True, exist_ok=True)
+        df.to_csv(args.csv, index=False)
+        print(f"\nSaved CSV: {args.csv}")
+    if df.empty:
+        print("\nNo rows with both Steam and CSFloat prices.")
+        return
+    print("\nPreview:")
+    print(df.to_string(index=False))
+
+
+if __name__ == "__main__":
+    main()
diff --git a/base_screening_and_anal/fetcher_runtime.json b/base_screening_and_anal/fetcher_runtime.json
index f2d0442..7b6b0ca 100644
--- a/base_screening_and_anal/fetcher_runtime.json
+++ b/base_screening_and_anal/fetcher_runtime.json
@@ -4,6 +4,14 @@
   "STEAM_DELAY": 20.0,
   "__FLOAT_DELAY__": "то же между предметами CSFloat",
   "FLOAT_DELAY": 25.0,
+  "__STEAM_CONCURRENCY__": "максимум одновременных in-flight Steam-запросов в async-режиме",
+  "STEAM_CONCURRENCY": 4,
+  "__FLOAT_CONCURRENCY__": "максимум одновременных in-flight CSFloat-запросов в async-режиме",
+  "FLOAT_CONCURRENCY": 2,
+  "__HTTP_TIMEOUT_SEC__": "общий timeout для Steam/CSFloat HTTP-запросов",
+  "HTTP_TIMEOUT_SEC": 15.0,
+  "__FX_TIMEOUT_SEC__": "timeout для запроса курса USD->EUR",
+  "FX_TIMEOUT_SEC": 20.0,
   "__KEY_COOLDOWN_429_SEC__": "после 429 на ключе CSFloat — пауза только этого ключа (сек)",
   "KEY_COOLDOWN_429_SEC": 900.0,
   "__KEY_COOLDOWN_403_SEC__": "после 403 на ключе CSFloat — пауза по ключу (сек)",
diff --git a/base_screening_and_anal/fetchers.env.example b/base_screening_and_anal/fetchers.env.example
new file mode 100644
index 0000000..cca9a6b
--- /dev/null
+++ b/base_screening_and_anal/fetchers.env.example
@@ -0,0 +1,44 @@
+# Copy this file to `fetchers.env` in the same folder and fill in the values.
+# `fetchers.py` loads it automatically, unless you point `FETCHERS_ENV_FILE`
+# to a different file.
+
+# Required for CSFloat requests.
+CSFLOAT_API_KEY=
+
+# Optional second CSFloat key. The fetcher rotates keys and cools down only the
+# key that hit 429/403.
+CSFLOAT_API_KEY_2=
+
+# Optional additional CSFloat keys, comma/newline/space-separated. In proxy mode,
+# CSFloat uses one-to-one (key, IP) pairs, so use 5 keys for 5 CSFloat IPs.
+CSFLOAT_API_KEYS=
+
+# Optional: custom runtime JSON path. If empty, fetchers.py will look for
+# `fetchers_runtime.json` and then the legacy `fetcher_runtime.json`.
+FETCHERS_RUNTIME_CONFIG=
+
+# Optional: override the HTTP user-agent used for Steam / CSFloat / FX requests.
+FETCHERS_USER_AGENT=Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36
+
+# Optional: async mode toggle. Recommended to keep `true`.
+FETCHERS_USE_AIOHTTP=true
+
+# Optional: if `true`, fail fast when aiohttp is missing instead of falling back
+# to the older requests/threading path.
+FETCHERS_REQUIRE_AIOHTTP=false
+
+# Optional: enable rotating proxies for Steam and CSFloat.
+# Steam rotates IPs. CSFloat rotates (API key, IP) identities.
+FETCHERS_USE_PROXIES=false
+
+# Optional static proxies, comma-separated or newline-separated.
+# Entries can be full URLs or Webshare rows like addr:port:username:password.
+FETCHERS_PROXY_LIST=
+
+# Optional path to a file containing one proxy per line.
+FETCHERS_PROXY_FILE=
+
+# Optional Webshare API config. Used only when FETCHERS_USE_PROXIES=true and no
+# static proxy list/file is configured.
+WEBSHARE_API_KEY=
+WEBSHARE_PLAN_ID=13345956
diff --git a/base_screening_and_anal/fetchers.py b/base_screening_and_anal/fetchers.py
index 24161fa..1e6020f 100644
--- a/base_screening_and_anal/fetchers.py
+++ b/base_screening_and_anal/fetchers.py
@@ -2,76 +2,219 @@
 Steam + CSFloat price fetchers.
 Используется из ноутбуков: from fetchers import fetch_all_prices
 
-CSFloat: CSFLOAT_API_KEY + опционально CSFLOAT_API_KEY_2 (local_secrets или env) —
-при двух ключах round-robin только по ключам не в cooldown; HTTP 429/403 ставит ключ
-на паузу (KEY_COOLDOWN_*) и сразу берётся другой; если все в паузе — ждём до истечения
-(как в skin_homog/skin_screener.py).
+Что изменено:
+  • batch-fetching умеет async/aiohttp для Steam и CSFloat;
+  • secrets/config можно положить в fetchers.env (или путь в FETCHERS_ENV_FILE);
+  • старый requests-путь оставлен как fallback, если aiohttp не установлен.
 
-Валюты / расхождения с клиентом Steam:
-  • priceoverview отдаёт цену в выбранной валюте; USD и EUR — разные запросы (разные курсы/округление Steam).
-  • Сравнивать «доллары из API» с «евро в клиенте × курс банка» нельзя — у Steam свой FX.
-  • CSFloat listings API считает цены в USD (центы); «Float в евро» из API официально нет — только умножить на свой курс.
+CSFloat: нужны CSFLOAT_API_KEY, CSFLOAT_API_KEY_2 или список CSFLOAT_API_KEYS.
+Steam priceoverview для этого слоя публичный, Steam cookies тут не нужны.
 
-STEAM_FETCH_EUR_ALSO: второй запрос в EUR → колонка steam_ask_eur (сверка с EU клиентом).
-Спреды spread_*% считаются в одной валюте: steam_ask (primary STEAM_CURRENCY) и Float USD.
-
-Паузы STEAM_DELAY / FLOAT_DELAY — базовые секунды; между запросами sleep случайный в диапазоне 0.5×…1.5× от базы.
-
-PRICES_IN_EUR: Steam в EUR + Float USD × курс USD→EUR. Курс: api.frankfurter.app (ECB),
-при сбое — XML ЕЦБ eurofxref-daily. В CSV добавляется колонка fx_usd_to_eur.
-
-Опционально: файл fetchers_runtime.json рядом с fetchers.py (старое имя fetcher_runtime.json тоже ищется).
-Путь: переменная FETCHERS_RUNTIME_CONFIG или устар. FETCHER_RUNTIME_CONFIG.
-При изменении файла на диске подхватываются паузы и cooldown без перезапуска ядра.
-См. fetchers_runtime.example.json — скопировать в fetchers_runtime.json и править числа.
+Опционально:
+  • runtime JSON рядом с файлом: fetchers_runtime.json или legacy fetcher_runtime.json;
+  • env-файл: fetchers.env (см. fetchers.env.example).
 """
 
 from __future__ import annotations
 
+import asyncio
 import json
 import os
 import random
 import re
-import time
 import threading
+import time
 import xml.etree.ElementTree as ET
 from concurrent.futures import ThreadPoolExecutor
 from pathlib import Path
 
 import requests
-import pandas as pd
+try:
+    import pandas as pd
+except ImportError:  # pragma: no cover - depends on local environment
+    pd = None
+
+try:
+    import aiohttp
+except ImportError:  # pragma: no cover - depends on local environment
+    aiohttp = None
+
+try:
+    from .proxy_rotation import (
+        AsyncRotationPool,
+        ProxyEndpoint,
+        RotationLease,
+        SyncRotationPool,
+        load_proxy_endpoints_from_env,
+    )
+except ImportError:  # pragma: no cover - notebook/script import from this folder
+    from proxy_rotation import (
+        AsyncRotationPool,
+        ProxyEndpoint,
+        RotationLease,
+        SyncRotationPool,
+        load_proxy_endpoints_from_env,
+    )
 
 # ---------------------------------------------------------------------------
 #  Config (можно перезаписать перед вызовом fetch_all_prices)
 # ---------------------------------------------------------------------------
-STEAM_CURRENCY = 1       # 1=USD, 3=EUR — primary steam_ask + основа для spread_% (с Float в USD)
-STEAM_FETCH_EUR_ALSO = False  # True: доп. запрос EUR → колонка steam_ask_eur (если primary USD)
-# True: Steam priceoverview в EUR; CSFloat (USD) переводится в EUR по курсу (Frankfurter → ECB XML fallback)
+DEFAULT_USER_AGENT = (
+    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
+    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
+)
+
+STEAM_CURRENCY = 1
+STEAM_FETCH_EUR_ALSO = False
 PRICES_IN_EUR = False
-# Базовые секунды; фактическая пауза — random.uniform(base*0.5, base*1.5)
-STEAM_DELAY    = 10.0
-FLOAT_DELAY    = 10.0
+STEAM_DELAY = 10.0
+FLOAT_DELAY = 10.0
 FLOAT_MAX_WORKERS = 1
-# После 429/403 на ключе — не слать этим ключом до time.monotonic() (см. skin_screener).
+STEAM_MAX_CONCURRENCY = 4
 KEY_COOLDOWN_429_SEC = 600.0
 KEY_COOLDOWN_403_SEC = 900.0
-# Steam: при 429 подождать и повторить (секунды между попытками). Переопределение: fetchers_runtime.json.
 STEAM_429_RETRY_WAIT_SEC = 90.0
-# 0 = ждать бесконечно. Если >0 и включен STEAM_RETURN_MISS_ON_429, то после N ответов 429 вернуть MISS.
+HTTP_TIMEOUT_SEC = 15.0
+FX_TIMEOUT_SEC = 20.0
+PROXY_COOLDOWN_429_SEC = 600.0
+PROXY_COOLDOWN_403_SEC = 900.0
+PROXY_ERROR_COOLDOWN_SEC = 60.0
+
+_STEAM_SYM = {1: "$", 3: "€", 5: "₽"}
+FRANKFURTER_LATEST = "https://api.frankfurter.app/latest"
+ECB_DAILY_XML = "https://www.ecb.europa.eu/stats/eurofxref/eurofxref-daily.xml"
+STEAM_PRICEOVERVIEW_URL = "https://steamcommunity.com/market/priceoverview/"
+CSFLOAT_LISTINGS_URL = "https://csfloat.com/api/v1/listings"
 
-# --- runtime overrides, перечитывается при изменении mtime ---
 _RUNTIME_LOCK = threading.Lock()
 _runtime_mtime: float | None = None
 _runtime_data: dict = {}
-_runtime_warned_missing: bool = False
+_runtime_warned_missing = False
 _runtime_loaded_path: str | None = None
 
+_ENV_LOCK = threading.Lock()
+_env_mtime: float | None = None
+_env_loaded_path: str | None = None
+_env_file_values: dict[str, str] = {}
+
+try:
+    import local_secrets as _ls
+except ImportError:  # pragma: no cover - optional local fallback
+    _ls = None
+
+CSFLOAT_API_KEY: str | None = None
+CSFLOAT_API_KEY_2: str | None = None
+FETCHERS_USER_AGENT = DEFAULT_USER_AGENT
+FETCHERS_USE_AIOHTTP = True
+FETCHERS_REQUIRE_AIOHTTP = False
+FETCHERS_USE_PROXIES = False
+
+_warned_no_aiohttp = False
+_warned_proxy_load_failed = False
+_CSFLOAT_KEY_RR_LOCK = threading.Lock()
+_csfloat_key_rr_i = [0]
+_key_cooldown_mono: dict[int, float] = {}
+_tls_cf_key_tag = threading.local()
+
+
+def _first_non_empty(*values: object) -> str | None:
+    for value in values:
+        if value is None:
+            continue
+        text = str(value).strip()
+        if text:
+            return text
+    return None
+
+
+def _parse_bool(text: object | None, default: bool) -> bool:
+    if text is None:
+        return default
+    value = str(text).strip().lower()
+    if value in {"1", "true", "yes", "y", "on"}:
+        return True
+    if value in {"0", "false", "no", "n", "off"}:
+        return False
+    return default
+
+
+def _split_env_list(text: object | None) -> list[str]:
+    if text is None:
+        return []
+    return [part.strip() for part in re.split(r"[\s,;]+", str(text)) if part.strip()]
+
+
+def _env_config_path() -> str:
+    env = os.environ.get("FETCHERS_ENV_FILE")
+    if env and env.strip():
+        return env.strip()
+    return str(Path(__file__).resolve().parent / "fetchers.env")
+
+
+def _load_env_file() -> None:
+    global _env_mtime, _env_loaded_path, _env_file_values
+    path = _env_config_path()
+    if path != _env_loaded_path:
+        _env_loaded_path = path
+        _env_mtime = None
+    try:
+        mtime = os.stat(path).st_mtime
+    except OSError:
+        return
+    with _ENV_LOCK:
+        if _env_mtime is not None and mtime == _env_mtime:
+            return
+        parsed: dict[str, str] = {}
+        for raw in Path(path).read_text(encoding="utf-8").splitlines():
+            line = raw.strip()
+            if not line or line.startswith("#") or "=" not in line:
+                continue
+            key, value = line.split("=", 1)
+            key = key.strip()
+            value = value.strip()
+            if not key:
+                continue
+            if value and len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
+                value = value[1:-1]
+            parsed[key] = value
+        for key, value in parsed.items():
+            current = os.environ.get(key)
+            prev = _env_file_values.get(key)
+            if current is None or current == prev:
+                os.environ[key] = value
+        _env_file_values = parsed
+        _env_mtime = mtime
+
+
+def _refresh_env_settings() -> None:
+    global CSFLOAT_API_KEY, CSFLOAT_API_KEY_2
+    global FETCHERS_USER_AGENT, FETCHERS_USE_AIOHTTP, FETCHERS_REQUIRE_AIOHTTP, FETCHERS_USE_PROXIES
+    _load_env_file()
+    CSFLOAT_API_KEY = _first_non_empty(
+        os.environ.get("CSFLOAT_API_KEY"),
+        getattr(_ls, "CSFLOAT_API_KEY", None) if _ls else None,
+    )
+    CSFLOAT_API_KEY_2 = _first_non_empty(
+        os.environ.get("CSFLOAT_API_KEY_2"),
+        getattr(_ls, "CSFLOAT_API_KEY_2", None) if _ls else None,
+    )
+    FETCHERS_USER_AGENT = _first_non_empty(
+        os.environ.get("FETCHERS_USER_AGENT"),
+        DEFAULT_USER_AGENT,
+    ) or DEFAULT_USER_AGENT
+    FETCHERS_USE_AIOHTTP = _parse_bool(
+        os.environ.get("FETCHERS_USE_AIOHTTP"), True)
+    FETCHERS_REQUIRE_AIOHTTP = _parse_bool(
+        os.environ.get("FETCHERS_REQUIRE_AIOHTTP"), False)
+    FETCHERS_USE_PROXIES = _parse_bool(
+        os.environ.get("FETCHERS_USE_PROXIES"), False)
+
 
 def _runtime_config_path() -> str:
-    """Путь к JSON: env, иначе fetchers_runtime.json, иначе (legacy) fetcher_runtime.json."""
-    env = os.environ.get("FETCHERS_RUNTIME_CONFIG") or os.environ.get("FETCHER_RUNTIME_CONFIG")
-    if env:
-        return env
+    env = os.environ.get("FETCHERS_RUNTIME_CONFIG") or os.environ.get(
+        "FETCHER_RUNTIME_CONFIG")
+    if env and env.strip():
+        return env.strip()
     base = Path(__file__).resolve().parent
     p_new = base / "fetchers_runtime.json"
     p_old = base / "fetcher_runtime.json"
@@ -83,7 +226,6 @@ def _runtime_config_path() -> str:
 
 
 def _load_runtime_config() -> dict:
-    """Следующий вызов после сохранения JSON на диске подхватит новые значения."""
     global _runtime_mtime, _runtime_data, _runtime_warned_missing, _runtime_loaded_path
     path = _runtime_config_path()
     if path != _runtime_loaded_path:
@@ -97,8 +239,8 @@ def _load_runtime_config() -> dict:
             base = Path(__file__).resolve().parent
             print(
                 "  [fetchers] нет fetchers_runtime.json (или fetcher_runtime.json) — "
-                "тайминги из констант в fetchers.py "
-                f"(скопируй {base / 'fetchers_runtime.example.json'} → {base / 'fetchers_runtime.json'})",
+                "используются значения по умолчанию "
+                f"(пример: {base / 'fetchers_runtime.example.json'})",
                 flush=True,
             )
         return {}
@@ -106,17 +248,12 @@ def _load_runtime_config() -> dict:
         if _runtime_mtime is not None and mtime == _runtime_mtime:
             return _runtime_data
         try:
-            with open(path, encoding="utf-8") as f:
-                raw = json.load(f)
-            if not isinstance(raw, dict):
-                raw = {}
-            _runtime_data = raw
+            raw = json.loads(Path(path).read_text(encoding="utf-8"))
+            _runtime_data = raw if isinstance(raw, dict) else {}
             _runtime_mtime = mtime
         except json.JSONDecodeError as e:
             print(
-                f"  [fetchers] {path}: JSON битый — оставляем предыдущие значения ({e})",
-                flush=True,
-            )
+                f"  [fetchers] {path}: JSON битый — оставляем предыдущие значения ({e})", flush=True)
             _runtime_mtime = mtime
         return _runtime_data
 
@@ -129,68 +266,95 @@ def _runtime_float(key: str, default: float) -> float:
         return float(cfg[key])
     except (TypeError, ValueError):
         return default
-def _random_delay(base: float) -> None:
-    """Пауза в секундах: uniform(0.5×base … 1.5×base)."""
+
+
+def _runtime_int(key: str, default: int) -> int:
+    cfg = _load_runtime_config()
+    if key not in cfg:
+        return default
+    try:
+        return int(cfg[key])
+    except (TypeError, ValueError):
+        return default
+
+
+def _random_delay_seconds(base: float) -> float:
     lo = max(0.0, base * 0.5)
-    hi = base * 1.5
-    time.sleep(random.uniform(lo, hi))
+    hi = max(lo, base * 1.5)
+    return random.uniform(lo, hi)
 
 
 def _inter_request_delay(base_key: str, fallback: float) -> None:
-    """Пауза между предметами; base из fetchers_runtime.json если ключ задан."""
-    _random_delay(_runtime_float(base_key, fallback))
+    time.sleep(_random_delay_seconds(_runtime_float(base_key, fallback)))
 
 
-CSFLOAT_API_KEY = os.environ.get("CSFLOAT_API_KEY")
-CSFLOAT_API_KEY_2 = os.environ.get("CSFLOAT_API_KEY_2")
-try:
-    import local_secrets as _ls
-    _k1 = getattr(_ls, "CSFLOAT_API_KEY", None)
-    if _k1:
-        CSFLOAT_API_KEY = _k1
-    _k2 = getattr(_ls, "CSFLOAT_API_KEY_2", None)
-    if _k2:
-        CSFLOAT_API_KEY_2 = _k2
-except ImportError:
-    pass
+def _http_headers(extra: dict[str, str] | None = None) -> dict[str, str]:
+    headers = {"User-Agent": FETCHERS_USER_AGENT}
+    if extra:
+        headers.update(extra)
+    return headers
 
-_CSFLOAT_KEY_RR_LOCK = threading.Lock()
-_csfloat_key_rr_i = [0]
-# key index -> time.monotonic() когда ключ снова можно использовать (429/403)
-_key_cooldown_mono: dict[int, float] = {}
-# После get_csfloat_prices в том же потоке — какой ключ использовался (для лога, в т.ч. при MISS)
-_tls_cf_key_tag = threading.local()
+
+def _ensure_pandas() -> None:
+    if pd is None:
+        raise RuntimeError(
+            "pandas is required for fetch_all_prices(). Install it in the environment used for screening."
+        )
+
+
+def parse_steam_price(price_str: str | None) -> float | None:
+    if not price_str:
+        return None
+    cleaned = re.sub(r"[^\d,.]", "", price_str)
+    if not cleaned:
+        return None
+    if "," in cleaned and "." in cleaned:
+        if cleaned.index(".") < cleaned.index(","):
+            cleaned = cleaned.replace(".", "").replace(",", ".")
+        else:
+            cleaned = cleaned.replace(",", "")
+    elif "," in cleaned:
+        cleaned = cleaned.replace(",", ".")
+    try:
+        return float(cleaned)
+    except ValueError:
+        return None
 
 
 def _csfloat_api_keys() -> tuple[str, ...]:
+    _refresh_env_settings()
     out: list[str] = []
-    for raw in (CSFLOAT_API_KEY, CSFLOAT_API_KEY_2):
+    extras = _split_env_list(
+        _first_non_empty(
+            os.environ.get("CSFLOAT_API_KEYS"),
+            getattr(_ls, "CSFLOAT_API_KEYS", None) if _ls else None,
+        )
+    )
+    for raw in (CSFLOAT_API_KEY, CSFLOAT_API_KEY_2, *extras):
         if not raw:
             continue
-        s = str(raw).strip()
-        if s and s not in out:
-            out.append(s)
+        if raw not in out:
+            out.append(raw)
     return tuple(out)
 
 
 def _tag_for_explicit_key(api_key: str) -> str:
     keys = _csfloat_api_keys()
-    for j, k in enumerate(keys):
-        if k == api_key:
+    for j, key in enumerate(keys):
+        if key == api_key:
             return f"{j + 1}/{len(keys)}"
     return "fixed"
 
 
 def _explicit_key_index(api_key: str) -> int:
     keys = _csfloat_api_keys()
-    for j, k in enumerate(keys):
-        if k == api_key:
+    for j, key in enumerate(keys):
+        if key == api_key:
             return j
     return 0
 
 
 def _try_pick_key_index(keys: tuple[str, ...]) -> int | None:
-    """Следующий доступный ключ в порядке round-robin; None если все в cooldown."""
     mono = time.monotonic()
     n = len(keys)
     start = _csfloat_key_rr_i[0] % n
@@ -203,20 +367,19 @@ def _try_pick_key_index(keys: tuple[str, ...]) -> int | None:
 
 
 def _apply_csfloat_key_cooldown(key_index: int | None, err: str) -> None:
-    if key_index is None or err not in ("429", "403"):
+    if key_index is None or err not in {"429", "403"}:
         return
-    if err == "429":
-        sec = _runtime_float("KEY_COOLDOWN_429_SEC", KEY_COOLDOWN_429_SEC)
-    else:
-        sec = _runtime_float("KEY_COOLDOWN_403_SEC", KEY_COOLDOWN_403_SEC)
+    sec = (
+        _runtime_float("KEY_COOLDOWN_429_SEC", KEY_COOLDOWN_429_SEC)
+        if err == "429"
+        else _runtime_float("KEY_COOLDOWN_403_SEC", KEY_COOLDOWN_403_SEC)
+    )
     until = time.monotonic() + sec
     with _CSFLOAT_KEY_RR_LOCK:
-        prev = _key_cooldown_mono.get(key_index, 0.0)
-        _key_cooldown_mono[key_index] = max(prev, until)
+        _key_cooldown_mono[key_index] = max(
+            _key_cooldown_mono.get(key_index, 0.0), until)
     print(
-        f"  [CSFloat] COOLDOWN ключ {key_index + 1}: ~{sec:.0f}s ({err})",
-        flush=True,
-    )
+        f"  [CSFloat] COOLDOWN ключ {key_index + 1}: ~{sec:.0f}s ({err})", flush=True)
 
 
 def _api_msg_rate_limited(msg: str) -> bool:
@@ -225,14 +388,9 @@ def _api_msg_rate_limited(msg: str) -> bool:
 
 
 def _wait_pick_csfloat_key(api_key_explicit: str | None) -> tuple[str | None, str, int | None]:
-    """
-    Ключ для следующего запроса; если все в cooldown — блокируемся до освобождения.
-    (api_key, tag '1/2', key_index для cooldown).
-    """
     keys = _csfloat_api_keys()
     if not keys:
         return None, "", None
-
     if api_key_explicit is not None:
         ex = str(api_key_explicit).strip()
         if not ex:
@@ -242,13 +400,12 @@ def _wait_pick_csfloat_key(api_key_explicit: str | None) -> tuple[str | None, st
             with _CSFLOAT_KEY_RR_LOCK:
                 until = _key_cooldown_mono.get(key_idx, 0.0)
                 if time.monotonic() >= until:
-                    tag = _tag_for_explicit_key(ex)
-                    return ex, tag, key_idx
+                    return ex, _tag_for_explicit_key(ex), key_idx
                 wake = until
             wait = max(0.05, wake - time.monotonic())
-            print(f"  [CSFloat] COOLDOWN: ждём {wait:.0f}s (ключ {key_idx + 1})…", flush=True)
+            print(
+                f"  [CSFloat] COOLDOWN: ждём {wait:.0f}s (ключ {key_idx + 1})…", flush=True)
             time.sleep(wait)
-
     while True:
         with _CSFLOAT_KEY_RR_LOCK:
             if len(keys) == 1:
@@ -259,63 +416,34 @@ def _wait_pick_csfloat_key(api_key_explicit: str | None) -> tuple[str | None, st
                 picked = _try_pick_key_index(keys)
                 if picked is not None:
                     return keys[picked], f"{picked + 1}/{len(keys)}", picked
-                wake = min(_key_cooldown_mono.get(j, 0.0) for j in range(len(keys)))
-
+                wake = min(_key_cooldown_mono.get(j, 0.0)
+                           for j in range(len(keys)))
         wait = max(0.05, wake - time.monotonic())
-        print(f"  [CSFloat] COOLDOWN: все ключи в паузе, ждём {wait:.0f}s…", flush=True)
+        print(
+            f"  [CSFloat] COOLDOWN: все ключи в паузе, ждём {wait:.0f}s…", flush=True)
         time.sleep(wait)
 
 
-# ---------------------------------------------------------------------------
-#  Steam
-# ---------------------------------------------------------------------------
-def parse_steam_price(price_str: str | None) -> float | None:
-    if not price_str:
-        return None
-    cleaned = re.sub(r'[^\d,.]', '', price_str)
-    if not cleaned:
-        return None
-    if ',' in cleaned and '.' in cleaned:
-        if cleaned.index('.') < cleaned.index(','):
-            cleaned = cleaned.replace('.', '').replace(',', '.')
-        else:
-            cleaned = cleaned.replace(',', '')
-    elif ',' in cleaned:
-        cleaned = cleaned.replace(',', '.')
-    try:
-        return float(cleaned)
-    except ValueError:
-        return None
-
-
-_STEAM_SYM = {1: "$", 3: "€", 5: "₽"}
-
-FRANKFURTER_LATEST = "https://api.frankfurter.app/latest"
-ECB_DAILY_XML = "https://www.ecb.europa.eu/stats/eurofxref/eurofxref-daily.xml"
-
-
 def fetch_usd_to_eur_multiplier() -> tuple[float, str]:
-    """
-    Множитель: amount_eur = amount_usd * multiplier (сколько EUR за 1 USD).
-    Источник: Frankfurter (курсы ECB); при ошибке — парсинг ECB daily XML.
-    """
     err_ff: Exception | None = None
     try:
         r = requests.get(
             FRANKFURTER_LATEST,
             params={"from": "USD", "to": "EUR"},
-            timeout=20,
-            headers={"User-Agent": "Mozilla/5.0"},
+            timeout=_runtime_float("FX_TIMEOUT_SEC", FX_TIMEOUT_SEC),
+            headers=_http_headers(),
         )
         r.raise_for_status()
         data = r.json()
-        m = float(data["rates"]["EUR"])
-        day = data.get("date", "?")
-        return m, f"Frankfurter {day} (ECB)"
+        return float(data["rates"]["EUR"]), f"Frankfurter {data.get('date', '?')} (ECB)"
     except Exception as e:
         err_ff = e
     try:
-        r = requests.get(ECB_DAILY_XML, timeout=20, headers={"User-Agent": "Mozilla/5.0"})
+        r = requests.get(
+            ECB_DAILY_XML,
+            timeout=_runtime_float("FX_TIMEOUT_SEC", FX_TIMEOUT_SEC),
+            headers=_http_headers(),
+        )
         r.raise_for_status()
         root = ET.fromstring(r.content)
         usd_per_1_eur: float | None = None
@@ -325,28 +453,58 @@ def fetch_usd_to_eur_multiplier() -> tuple[float, str]:
                 break
         if usd_per_1_eur is None or usd_per_1_eur <= 0:
             raise ValueError("ECB XML: no USD rate")
-        eur_per_usd = 1.0 / usd_per_1_eur
-        return eur_per_usd, "ECB eurofxref-daily.xml (fallback)"
+        return 1.0 / usd_per_1_eur, "ECB eurofxref-daily.xml (fallback)"
     except Exception as e2:
         raise RuntimeError(
             f"USD→EUR: Frankfurter failed ({err_ff!r}); ECB fallback failed ({e2!r})"
         ) from e2
 
 
-def get_steam_price(market_hash_name: str, currency: int = STEAM_CURRENCY) -> float | None:
-    url = "https://steamcommunity.com/market/priceoverview/"
-    params = {"appid": 730, "currency": currency, "market_hash_name": market_hash_name}
+def get_steam_price(
+    market_hash_name: str,
+    currency: int = STEAM_CURRENCY,
+    proxy_pool: SyncRotationPool[ProxyEndpoint] | None = None,
+) -> float | None:
+    params = {"appid": 730, "currency": currency,
+              "market_hash_name": market_hash_name}
     net_n = 0
+    local_proxy_pool = proxy_pool
+    if local_proxy_pool is None:
+        proxies = _proxy_endpoints()
+        local_proxy_pool = SyncRotationPool(proxies) if proxies else None
     while True:
+        lease = local_proxy_pool.acquire() if local_proxy_pool is not None else None
+        proxy = lease.item if lease is not None else None
         try:
-            r = requests.get(url, params=params, timeout=15)
+            r = requests.get(
+                STEAM_PRICEOVERVIEW_URL,
+                params=params,
+                timeout=_runtime_float("HTTP_TIMEOUT_SEC", HTTP_TIMEOUT_SEC),
+                headers=_http_headers(),
+                proxies=proxy.requests_proxies if proxy is not None else None,
+            )
+            if r.status_code in {429, 403} and lease is not None and local_proxy_pool is not None:
+                wait_sec = _proxy_cooldown_seconds(r.status_code)
+                print(
+                    f"  [Steam] {market_hash_name}: HTTP {r.status_code} — другой IP / пауза ~{wait_sec:.0f}s",
+                    flush=True,
+                )
+                local_proxy_pool.cooldown(lease.index, wait_sec)
+                continue
             if r.status_code == 429:
-                w = _runtime_float("STEAM_429_RETRY_WAIT_SEC", STEAM_429_RETRY_WAIT_SEC)
+                wait_sec = (
+                    _proxy_cooldown_seconds("429")
+                    if lease is not None
+                    else _runtime_float("STEAM_429_RETRY_WAIT_SEC", STEAM_429_RETRY_WAIT_SEC)
+                )
                 print(
-                    f"  [Steam] {market_hash_name}: HTTP 429 — пауза ~{w:.0f}s (до успеха)",
+                    f"  [Steam] {market_hash_name}: HTTP 429 — пауза ~{wait_sec:.0f}s (до успеха)",
                     flush=True,
                 )
-                time.sleep(w)
+                if lease is not None and local_proxy_pool is not None:
+                    local_proxy_pool.cooldown(lease.index, wait_sec)
+                else:
+                    time.sleep(wait_sec)
                 continue
             r.raise_for_status()
             data = r.json()
@@ -358,63 +516,92 @@ def get_steam_price(market_hash_name: str, currency: int = STEAM_CURRENCY) -> fl
         except (requests.exceptions.Timeout, requests.exceptions.ConnectionError) as e:
             net_n += 1
             print(
-                f"  [Steam] {market_hash_name}: сеть — повтор #{net_n} (до успеха): {e}",
-                flush=True,
-            )
+                f"  [Steam] {market_hash_name}: сеть — повтор #{net_n} (до успеха): {e}", flush=True)
+            if lease is not None and local_proxy_pool is not None:
+                local_proxy_pool.cooldown(
+                    lease.index, _proxy_cooldown_seconds("net"))
             time.sleep(
                 random.uniform(
                     _runtime_float("STEAM_NET_SLEEP_MIN", 3.0),
                     _runtime_float("STEAM_NET_SLEEP_MAX", 12.0),
                 )
             )
-            continue
         except Exception as e:
             print(f"  [Steam] {market_hash_name}: {e}")
             return None
 
 
-# ---------------------------------------------------------------------------
-#  CSFloat
-# ---------------------------------------------------------------------------
-def get_csfloat_prices(market_hash_name: str, api_key: str | None = None) -> dict | None:
-    """
-    Returns dict: ask, predicted, base, quantity — в USD (API CSFloat, центы/100).
-
-    If api_key is None: CSFLOAT_API_KEY + CSFLOAT_API_KEY_2 — round-robin по ключам не в cooldown;
-    при HTTP 429/403 ключ уходит в паузу, запрос повторяется с другим ключом или после ожидания.
-    Паузы/cooldown можно крутить через fetchers_runtime.json без перезапуска.
-
-    Pass api_key explicitly to pin a single key (при 429 ждём cooldown только этого ключа).
-    """
-    url = "https://csfloat.com/api/v1/listings"
+def get_csfloat_prices(
+    market_hash_name: str,
+    api_key: str | None = None,
+    identity_pool: SyncRotationPool[_CSFloatIdentity] | None = None,
+) -> dict | None:
+    _refresh_env_settings()
     params = {
         "market_hash_name": market_hash_name,
         "sort_by": "lowest_price",
         "limit": 3,
         "type": "buy_now",
     }
+    local_identity_pool = identity_pool
+    if local_identity_pool is None and FETCHERS_USE_PROXIES:
+        keys = (str(api_key).strip(),) if api_key is not None and str(
+            api_key).strip() else _csfloat_api_keys()
+        identities = _build_csfloat_identities(keys, _proxy_endpoints())
+        local_identity_pool = SyncRotationPool(
+            identities) if identities else None
     while True:
-        k, key_tag, key_idx = _wait_pick_csfloat_key(api_key)
-        if not k:
+        lease: RotationLease[_CSFloatIdentity] | None = None
+        identity: _CSFloatIdentity | None = None
+        if local_identity_pool is not None:
+            lease = local_identity_pool.acquire()
+            identity = lease.item if lease is not None else None
+            key = identity.key if identity is not None else None
+            key_tag = identity.label if identity is not None else ""
+            key_idx = identity.key_index if identity is not None else None
+        else:
+            key, key_tag, key_idx = _wait_pick_csfloat_key(api_key)
+        if not key:
             print(f"  [CSFloat] {market_hash_name}: нет API ключа")
             return None
         _tls_cf_key_tag.label = key_tag
-        headers = {"User-Agent": "Mozilla/5.0", "Authorization": k}
         try:
-            r = requests.get(url, params=params, headers=headers, timeout=15)
+            r = requests.get(
+                CSFLOAT_LISTINGS_URL,
+                params=params,
+                headers=_http_headers({"Authorization": key}),
+                timeout=_runtime_float("HTTP_TIMEOUT_SEC", HTTP_TIMEOUT_SEC),
+                proxies=(
+                    identity.proxy.requests_proxies
+                    if identity is not None and identity.proxy is not None
+                    else None
+                ),
+            )
             if r.status_code == 429:
-                print(f"  [CSFloat] {market_hash_name}: HTTP 429 — другой ключ / пауза", flush=True)
-                _apply_csfloat_key_cooldown(key_idx, "429")
+                print(
+                    f"  [CSFloat] {market_hash_name}: HTTP 429 — другой ключ / пауза", flush=True)
+                if lease is not None and local_identity_pool is not None:
+                    local_identity_pool.cooldown(
+                        lease.index,
+                        _csfloat_identity_cooldown_seconds(identity, "429"),
+                    )
+                else:
+                    _apply_csfloat_key_cooldown(key_idx, "429")
                 continue
             if r.status_code == 403:
-                print(f"  [CSFloat] {market_hash_name}: HTTP 403 — другой ключ / пауза", flush=True)
-                _apply_csfloat_key_cooldown(key_idx, "403")
+                print(
+                    f"  [CSFloat] {market_hash_name}: HTTP 403 — другой ключ / пауза", flush=True)
+                if lease is not None and local_identity_pool is not None:
+                    local_identity_pool.cooldown(
+                        lease.index,
+                        _csfloat_identity_cooldown_seconds(identity, "403"),
+                    )
+                else:
+                    _apply_csfloat_key_cooldown(key_idx, "403")
                 continue
             if r.status_code >= 500:
                 print(
-                    f"  [CSFloat] {market_hash_name}: HTTP {r.status_code} — пауза и повтор…",
-                    flush=True,
-                )
+                    f"  [CSFloat] {market_hash_name}: HTTP {r.status_code} — пауза и повтор…", flush=True)
                 time.sleep(
                     random.uniform(
                         _runtime_float("CSFLOAT_5XX_SLEEP_MIN", 5.0),
@@ -427,8 +614,16 @@ def get_csfloat_prices(market_hash_name: str, api_key: str | None = None) -> dic
             if isinstance(data, dict) and ("error" in data or "message" in data):
                 msg = str(data.get("error") or data.get("message") or "")
                 if _api_msg_rate_limited(msg):
-                    print(f"  [CSFloat] {market_hash_name}: rate limit в теле ответа — cooldown", flush=True)
-                    _apply_csfloat_key_cooldown(key_idx, "429")
+                    print(
+                        f"  [CSFloat] {market_hash_name}: rate limit в теле ответа — cooldown", flush=True)
+                    if lease is not None and local_identity_pool is not None:
+                        local_identity_pool.cooldown(
+                            lease.index,
+                            _csfloat_identity_cooldown_seconds(
+                                identity, "429"),
+                        )
+                    else:
+                        _apply_csfloat_key_cooldown(key_idx, "429")
                     continue
                 print(f"  [CSFloat] {market_hash_name}: {msg}")
                 return None
@@ -436,7 +631,8 @@ def get_csfloat_prices(market_hash_name: str, api_key: str | None = None) -> dic
             if not listings:
                 print(f"  [CSFloat] {market_hash_name}: no listings")
                 return None
-            ask_prices = [l["price"] / 100 for l in listings if "price" in l]
+            ask_prices = [listing["price"] /
+                          100 for listing in listings if "price" in listing]
             if not ask_prices:
                 return None
             ref = listings[0].get("reference", {})
@@ -450,25 +646,41 @@ def get_csfloat_prices(market_hash_name: str, api_key: str | None = None) -> dic
                 "_key": key_tag,
             }
         except requests.HTTPError as e:
-            resp = getattr(e, "response", None)
-            code = resp.status_code if resp is not None else None
+            code = getattr(getattr(e, "response", None), "status_code", None)
             if code == 429:
-                _apply_csfloat_key_cooldown(key_idx, "429")
+                if lease is not None and local_identity_pool is not None:
+                    local_identity_pool.cooldown(
+                        lease.index,
+                        _csfloat_identity_cooldown_seconds(identity, "429"),
+                    )
+                else:
+                    _apply_csfloat_key_cooldown(key_idx, "429")
                 continue
             if code == 403:
-                _apply_csfloat_key_cooldown(key_idx, "403")
+                if lease is not None and local_identity_pool is not None:
+                    local_identity_pool.cooldown(
+                        lease.index,
+                        _csfloat_identity_cooldown_seconds(identity, "403"),
+                    )
+                else:
+                    _apply_csfloat_key_cooldown(key_idx, "403")
                 continue
             print(f"  [CSFloat] {market_hash_name}: {e}")
             return None
         except (requests.exceptions.Timeout, requests.exceptions.ConnectionError) as e:
-            print(f"  [CSFloat] {market_hash_name}: сеть — повтор: {e}", flush=True)
+            print(
+                f"  [CSFloat] {market_hash_name}: сеть — повтор: {e}", flush=True)
+            if lease is not None and local_identity_pool is not None:
+                local_identity_pool.cooldown(
+                    lease.index,
+                    _csfloat_identity_cooldown_seconds(identity, "net"),
+                )
             time.sleep(
                 random.uniform(
                     _runtime_float("CSFLOAT_NET_SLEEP_MIN", 3.0),
                     _runtime_float("CSFLOAT_NET_SLEEP_MAX", 10.0),
                 )
             )
-            continue
         except Exception as e:
             print(f"  [CSFloat] {market_hash_name}: {e}")
             return None
@@ -479,121 +691,676 @@ def _csfloat_key_suffix() -> str:
     return f", key={tag}" if tag else ""
 
 
-# ---------------------------------------------------------------------------
-#  Batch fetcher
-# ---------------------------------------------------------------------------
-def fetch_all_prices(
-    items: list[str],
-    steam_delay: float = STEAM_DELAY,
-    float_delay: float = FLOAT_DELAY,
-    float_workers: int = FLOAT_MAX_WORKERS,
+class _CSFloatIdentity:
+    def __init__(
+        self,
+        *,
+        key: str,
+        key_tag: str,
+        key_index: int,
+        proxy: ProxyEndpoint | None,
+    ) -> None:
+        self.key = key
+        self.key_tag = key_tag
+        self.key_index = key_index
+        self.proxy = proxy
+
+    @property
+    def label(self) -> str:
+        if self.proxy is None:
+            return self.key_tag
+        return f"{self.key_tag}, ip={self.proxy.label}"
+
+
+def _proxy_endpoints() -> tuple[ProxyEndpoint, ...]:
+    _refresh_env_settings()
+    if not FETCHERS_USE_PROXIES:
+        return ()
+    global _warned_proxy_load_failed
+    try:
+        endpoints = load_proxy_endpoints_from_env(http_get=requests.get)
+    except Exception as e:
+        if not _warned_proxy_load_failed:
+            print(
+                f"  [fetchers] proxy loading failed: {e}. Continuing without proxies.", flush=True)
+            _warned_proxy_load_failed = True
+        return ()
+    if not endpoints and not _warned_proxy_load_failed:
+        print(
+            "  [fetchers] FETCHERS_USE_PROXIES=true, but no proxies are configured. "
+            "Set FETCHERS_PROXY_LIST, FETCHERS_PROXY_FILE, or WEBSHARE_API_KEY.",
+            flush=True,
+        )
+        _warned_proxy_load_failed = True
+    return endpoints
+
+
+def _build_csfloat_identities(
+    keys: tuple[str, ...],
+    proxies: tuple[ProxyEndpoint, ...],
+) -> tuple[_CSFloatIdentity, ...]:
+    identities: list[_CSFloatIdentity] = []
+    if proxies:
+        # CSFloat dislikes the same API key moving across many IPs. Bind each
+        # key to one proxy; extra proxies are still available to Steam.
+        for key_idx, (key, proxy) in enumerate(zip(keys, proxies)):
+            identities.append(
+                _CSFloatIdentity(
+                    key=key,
+                    key_tag=f"{key_idx + 1}/{len(keys)}",
+                    key_index=key_idx,
+                    proxy=proxy,
+                )
+            )
+        return tuple(identities)
+    for key_idx, key in enumerate(keys):
+        identities.append(
+            _CSFloatIdentity(
+                key=key,
+                key_tag=f"{key_idx + 1}/{len(keys)}",
+                key_index=key_idx,
+                proxy=None,
+            )
+        )
+    return tuple(identities)
+
+
+def _proxy_cooldown_seconds(status: str | int) -> float:
+    if str(status) == "429":
+        return _runtime_float("PROXY_COOLDOWN_429_SEC", PROXY_COOLDOWN_429_SEC)
+    if str(status) == "403":
+        return _runtime_float("PROXY_COOLDOWN_403_SEC", PROXY_COOLDOWN_403_SEC)
+    return _runtime_float("PROXY_ERROR_COOLDOWN_SEC", PROXY_ERROR_COOLDOWN_SEC)
+
+
+def _csfloat_identity_cooldown_seconds(identity: _CSFloatIdentity | None, status: str | int) -> float:
+    if identity is not None and identity.proxy is None:
+        if str(status) == "429":
+            return _runtime_float("KEY_COOLDOWN_429_SEC", KEY_COOLDOWN_429_SEC)
+        if str(status) == "403":
+            return _runtime_float("KEY_COOLDOWN_403_SEC", KEY_COOLDOWN_403_SEC)
+        return 0.0
+    return _proxy_cooldown_seconds(status)
+
+
+class _AsyncStartLimiter:
+    def __init__(self, runtime_key: str, fallback: float) -> None:
+        self.runtime_key = runtime_key
+        self.fallback = fallback
+        self._lock = asyncio.Lock()
+        self._next_at = 0.0
+
+    async def wait_turn(self) -> None:
+        base = _runtime_float(self.runtime_key, self.fallback)
+        delay = _random_delay_seconds(base)
+        delay = 0.5
+        loop = asyncio.get_running_loop()
+        async with self._lock:
+            now = loop.time()
+            start_at = max(now, self._next_at)
+            self._next_at = start_at + delay
+        sleep_for = start_at - loop.time()
+        print(f"[limiter] delay={delay}, sleep_for={sleep_for}")
+        if sleep_for > 0:
+            await asyncio.sleep(sleep_for)
+
+
+class _AsyncCSFloatKeyPool:
+    def __init__(self, keys: tuple[str, ...]) -> None:
+        self.keys = keys
+        self._cooldowns: dict[int, float] = {}
+        self._rr_index = 0
+        self._lock = asyncio.Lock()
+
+    async def acquire(self, explicit_key: str | None = None) -> tuple[str | None, str, int | None]:
+        if not self.keys:
+            return None, "", None
+        if explicit_key is not None:
+            text = str(explicit_key).strip()
+            if not text:
+                return None, "", None
+            idx = self._explicit_key_index(text)
+            while True:
+                async with self._lock:
+                    now = asyncio.get_running_loop().time()
+                    until = self._cooldowns.get(idx, 0.0)
+                    if now >= until:
+                        return text, self._tag_for_key(text), idx
+                    wake = until
+                wait = max(0.05, wake - asyncio.get_running_loop().time())
+                print(
+                    f"  [CSFloat] COOLDOWN: ждём {wait:.0f}s (ключ {idx + 1})…", flush=True)
+                await asyncio.sleep(wait)
+        while True:
+            async with self._lock:
+                now = asyncio.get_running_loop().time()
+                picked = self._try_pick_key_index(now)
+                if picked is not None:
+                    return self.keys[picked], f"{picked + 1}/{len(self.keys)}", picked
+                wake = min(self._cooldowns.get(j, 0.0)
+                           for j in range(len(self.keys)))
+            wait = max(0.05, wake - asyncio.get_running_loop().time())
+            print(
+                f"  [CSFloat] COOLDOWN: все ключи в паузе, ждём {wait:.0f}s…", flush=True)
+            await asyncio.sleep(wait)
+
+    async def cooldown(self, key_index: int | None, err: str) -> None:
+        if key_index is None or err not in {"429", "403"}:
+            return
+        sec = (
+            _runtime_float("KEY_COOLDOWN_429_SEC", KEY_COOLDOWN_429_SEC)
+            if err == "429"
+            else _runtime_float("KEY_COOLDOWN_403_SEC", KEY_COOLDOWN_403_SEC)
+        )
+        until = asyncio.get_running_loop().time() + sec
+        async with self._lock:
+            self._cooldowns[key_index] = max(
+                self._cooldowns.get(key_index, 0.0), until)
+        print(
+            f"  [CSFloat] COOLDOWN ключ {key_index + 1}: ~{sec:.0f}s ({err})", flush=True)
+
+    def _explicit_key_index(self, api_key: str) -> int:
+        for j, key in enumerate(self.keys):
+            if key == api_key:
+                return j
+        return 0
+
+    def _tag_for_key(self, api_key: str) -> str:
+        for j, key in enumerate(self.keys):
+            if key == api_key:
+                return f"{j + 1}/{len(self.keys)}"
+        return "fixed"
+
+    def _try_pick_key_index(self, now: float) -> int | None:
+        n = len(self.keys)
+        start = self._rr_index % n
+        for step in range(n):
+            idx = (start + step) % n
+            if now >= self._cooldowns.get(idx, 0.0):
+                self._rr_index = idx + 1
+                return idx
+        return None
+
+
+class _AsyncSessionPool:
+    def __init__(self) -> None:
+        self._sessions: dict[str, "aiohttp.ClientSession"] = {}
+
+    async def __aenter__(self) -> "_AsyncSessionPool":
+        return self
+
+    async def __aexit__(self, exc_type, exc, tb) -> None:
+        for session in self._sessions.values():
+            await session.close()
+
+    def for_proxy(self, proxy: ProxyEndpoint | None) -> "aiohttp.ClientSession":
+        key = proxy.url if proxy is not None else "__direct__"
+        if key not in self._sessions:
+            kwargs = {"connector": aiohttp.TCPConnector(
+                limit=0, ttl_dns_cache=300)}
+            dummy_cookie_jar = getattr(aiohttp, "DummyCookieJar", None)
+            if dummy_cookie_jar is not None:
+                kwargs["cookie_jar"] = dummy_cookie_jar()
+            self._sessions[key] = aiohttp.ClientSession(**kwargs)
+        return self._sessions[key]
+
+
+def _async_session_for_proxy(session_or_pool: object, proxy: ProxyEndpoint | None) -> object:
+    for_proxy = getattr(session_or_pool, "for_proxy", None)
+    if callable(for_proxy):
+        return for_proxy(proxy)
+    return session_or_pool
+
+
+async def _async_json_request(
+    session: "aiohttp.ClientSession",
+    url: str,
     *,
-    steam_currency: int | None = None,
-    steam_fetch_eur_also: bool | None = None,
-    prices_in_eur: bool | None = None,
-) -> pd.DataFrame:
-    pie = PRICES_IN_EUR if prices_in_eur is None else prices_in_eur
-    usd_eur: float | None = None
-    fx_src = ""
+    params: dict[str, object] | None = None,
+    headers: dict[str, str] | None = None,
+    proxy: str | None = None,
+    timeout_sec: float,
+) -> tuple[int, object | None, str]:
+    async with session.get(
+        url,
+        params=params,
+        headers=headers,
+        proxy=proxy,
+        timeout=aiohttp.ClientTimeout(total=timeout_sec),
+    ) as response:
+        text = await response.text()
+        try:
+            data = json.loads(text)
+        except json.JSONDecodeError:
+            data = None
+        return response.status, data, text
+
+
+async def _async_fetch_usd_to_eur_multiplier(session: "aiohttp.ClientSession") -> tuple[float, str]:
+    err_ff: Exception | None = None
+    timeout_sec = _runtime_float("FX_TIMEOUT_SEC", FX_TIMEOUT_SEC)
+    try:
+        status, data, _ = await _async_json_request(
+            session,
+            FRANKFURTER_LATEST,
+            params={"from": "USD", "to": "EUR"},
+            headers=_http_headers(),
+            timeout_sec=timeout_sec,
+        )
+        if status >= 400 or not isinstance(data, dict):
+            raise RuntimeError(f"Frankfurter HTTP {status}")
+        return float(data["rates"]["EUR"]), f"Frankfurter {data.get('date', '?')} (ECB)"
+    except Exception as e:
+        err_ff = e
+    try:
+        async with session.get(
+            ECB_DAILY_XML,
+            headers=_http_headers(),
+            timeout=aiohttp.ClientTimeout(total=timeout_sec),
+        ) as response:
+            response.raise_for_status()
+            raw = await response.read()
+        root = ET.fromstring(raw)
+        usd_per_1_eur: float | None = None
+        for elem in root.iter():
+            if elem.attrib.get("currency") == "USD":
+                usd_per_1_eur = float(elem.attrib["rate"])
+                break
+        if usd_per_1_eur is None or usd_per_1_eur <= 0:
+            raise ValueError("ECB XML: no USD rate")
+        return 1.0 / usd_per_1_eur, "ECB eurofxref-daily.xml (fallback)"
+    except Exception as e2:
+        raise RuntimeError(
+            f"USD→EUR: Frankfurter failed ({err_ff!r}); ECB fallback failed ({e2!r})"
+        ) from e2
 
+
+async def _async_get_steam_price(
+    session: object,
+    limiter: _AsyncStartLimiter,
+    semaphore: asyncio.Semaphore,
+    proxy_pool: AsyncRotationPool[ProxyEndpoint] | None,
+    market_hash_name: str,
+    currency: int,
+) -> float | None:
+    params = {"appid": 730, "currency": currency,
+              "market_hash_name": market_hash_name}
+    net_n = 0
+    needs_limiter_turn = True
+    while True:
+        if needs_limiter_turn:
+            await limiter.wait_turn()
+        needs_limiter_turn = True
+        lease = await proxy_pool.acquire() if proxy_pool is not None else None
+        proxy = lease.item if lease is not None else None
+        try:
+            async with semaphore:
+                status, data, _ = await _async_json_request(
+                    _async_session_for_proxy(session, proxy),
+                    STEAM_PRICEOVERVIEW_URL,
+                    params=params,
+                    headers=_http_headers(),
+                    proxy=proxy.url if proxy is not None else None,
+                    timeout_sec=_runtime_float(
+                        "HTTP_TIMEOUT_SEC", HTTP_TIMEOUT_SEC),
+                )
+        except (aiohttp.ClientConnectionError, asyncio.TimeoutError) as e:
+            net_n += 1
+            print(
+                f"  [Steam] {market_hash_name}: сеть — повтор #{net_n} (до успеха): {e}", flush=True)
+            if lease is not None and proxy_pool is not None:
+                await proxy_pool.cooldown(lease.index, _proxy_cooldown_seconds("net"))
+            await asyncio.sleep(
+                random.uniform(
+                    _runtime_float("STEAM_NET_SLEEP_MIN", 3.0),
+                    _runtime_float("STEAM_NET_SLEEP_MAX", 12.0),
+                )
+            )
+            needs_limiter_turn = False
+            continue
+        except Exception as e:
+            print(f"  [Steam] {market_hash_name}: {e}")
+            return None
+        if status in {429, 403} and lease is not None and proxy_pool is not None:
+            wait_sec = _proxy_cooldown_seconds(status)
+            print(
+                f"  [Steam] {market_hash_name}: HTTP {status} — другой IP / пауза ~{wait_sec:.0f}s", flush=True)
+            await proxy_pool.cooldown(lease.index, wait_sec)
+            needs_limiter_turn = False
+            continue
+        if status == 429:
+            wait_sec = _runtime_float(
+                "STEAM_429_RETRY_WAIT_SEC", STEAM_429_RETRY_WAIT_SEC)
+            print(
+                f"  [Steam] {market_hash_name}: HTTP 429 — пауза ~{wait_sec:.0f}s (до успеха)", flush=True)
+            await asyncio.sleep(wait_sec)
+            continue
+        if status >= 400:
+            print(f"  [Steam] {market_hash_name}: HTTP {status}")
+            return None
+        if not isinstance(data, dict) or not data.get("success"):
+            return None
+        return parse_steam_price(data.get("lowest_price")) or parse_steam_price(data.get("median_price"))
+
+
+async def _async_get_csfloat_prices(
+    session: object,
+    limiter: _AsyncStartLimiter,
+    semaphore: asyncio.Semaphore,
+    identity_pool: AsyncRotationPool[_CSFloatIdentity],
+    market_hash_name: str,
+    api_key: str | None = None,
+) -> dict | None:
+    local_identity_pool = identity_pool
+    if api_key is not None:
+        text = str(api_key).strip()
+        identities = _build_csfloat_identities(
+            (text,), _proxy_endpoints()) if text else ()
+        local_identity_pool = AsyncRotationPool(identities)
+    params = {
+        "market_hash_name": market_hash_name,
+        "sort_by": "lowest_price",
+        "limit": 3,
+        "type": "buy_now",
+    }
+    while True:
+        lease = await local_identity_pool.acquire()
+        identity = lease.item if lease is not None else None
+        if identity is None or not identity.key:
+            print(f"  [CSFloat] {market_hash_name}: нет API ключа")
+            return None
+        key = identity.key
+        await limiter.wait_turn()
+        try:
+            async with semaphore:
+                status, data, _ = await _async_json_request(
+                    _async_session_for_proxy(session, identity.proxy),
+                    CSFLOAT_LISTINGS_URL,
+                    params=params,
+                    headers=_http_headers({"Authorization": key}),
+                    proxy=identity.proxy.url if identity.proxy is not None else None,
+                    timeout_sec=_runtime_float(
+                        "HTTP_TIMEOUT_SEC", HTTP_TIMEOUT_SEC),
+                )
+        except (aiohttp.ClientConnectionError, asyncio.TimeoutError) as e:
+            print(
+                f"  [CSFloat] {market_hash_name}: сеть — повтор: {e}", flush=True)
+            await local_identity_pool.cooldown(
+                lease.index if lease is not None else None,
+                _csfloat_identity_cooldown_seconds(identity, "net"),
+            )
+            await asyncio.sleep(
+                random.uniform(
+                    _runtime_float("CSFLOAT_NET_SLEEP_MIN", 3.0),
+                    _runtime_float("CSFLOAT_NET_SLEEP_MAX", 10.0),
+                )
+            )
+            continue
+        except Exception as e:
+            print(f"  [CSFloat] {market_hash_name}: {e}")
+            return None
+        if status == 429:
+            print(
+                f"  [CSFloat] {market_hash_name}: HTTP 429 — другой ключ / пауза", flush=True)
+            await local_identity_pool.cooldown(
+                lease.index if lease is not None else None,
+                _csfloat_identity_cooldown_seconds(identity, "429"),
+            )
+            continue
+        if status == 403:
+            print(
+                f"  [CSFloat] {market_hash_name}: HTTP 403 — другой ключ / пауза", flush=True)
+            await local_identity_pool.cooldown(
+                lease.index if lease is not None else None,
+                _csfloat_identity_cooldown_seconds(identity, "403"),
+            )
+            continue
+        if status >= 500:
+            print(
+                f"  [CSFloat] {market_hash_name}: HTTP {status} — пауза и повтор…", flush=True)
+            await asyncio.sleep(
+                random.uniform(
+                    _runtime_float("CSFLOAT_5XX_SLEEP_MIN", 5.0),
+                    _runtime_float("CSFLOAT_5XX_SLEEP_MAX", 15.0),
+                )
+            )
+            continue
+        if status >= 400:
+            print(f"  [CSFloat] {market_hash_name}: HTTP {status}")
+            return None
+        if isinstance(data, dict) and ("error" in data or "message" in data):
+            msg = str(data.get("error") or data.get("message") or "")
+            if _api_msg_rate_limited(msg):
+                print(
+                    f"  [CSFloat] {market_hash_name}: rate limit в теле ответа — cooldown", flush=True)
+                await local_identity_pool.cooldown(
+                    lease.index if lease is not None else None,
+                    _csfloat_identity_cooldown_seconds(identity, "429"),
+                )
+                continue
+            print(f"  [CSFloat] {market_hash_name}: {msg}")
+            return None
+        listings = data if isinstance(data, list) else data.get(
+            "data", []) if isinstance(data, dict) else []
+        if not listings:
+            print(f"  [CSFloat] {market_hash_name}: no listings")
+            return None
+        ask_prices = [listing["price"] /
+                      100 for listing in listings if "price" in listing]
+        if not ask_prices:
+            return None
+        ref = listings[0].get("reference", {})
+        predicted = ref.get("predicted_price")
+        base = ref.get("base_price")
+        return {
+            "ask": ask_prices[0],
+            "predicted": predicted / 100 if predicted else None,
+            "base": base / 100 if base else None,
+            "quantity": ref.get("quantity"),
+            "_key": identity.label,
+        }
+
+
+def _prepare_mode(
+    *,
+    steam_currency: int | None,
+    steam_fetch_eur_also: bool | None,
+    prices_in_eur: bool | None,
+) -> tuple[bool, int, bool, bool, bool]:
+    pie = PRICES_IN_EUR if prices_in_eur is None else prices_in_eur
     if pie:
-        usd_eur, fx_src = fetch_usd_to_eur_multiplier()
         sc = 3
         fetch_eur = False
-        print(
-            f"PRICES_IN_EUR: Steam EUR + Float USD×{usd_eur:.6f} (€ per $1; EUR = USD×this) — {fx_src}\n"
-        )
     else:
         sc = STEAM_CURRENCY if steam_currency is None else steam_currency
         fetch_eur = STEAM_FETCH_EUR_ALSO if steam_fetch_eur_also is None else steam_fetch_eur_also
+    want_eur_column = (not pie) and fetch_eur and sc == 1
+    want_usd_column = (not pie) and fetch_eur and sc == 3
+    return pie, sc, fetch_eur, want_eur_column, want_usd_column
 
-    steam_prices: dict[str, float | None] = {}
-    steam_prices_alt: dict[str, float | None] = {}  # EUR if primary USD, USD if primary EUR
-    float_data: dict[str, dict | None] = {}
-    lock = threading.Lock()
-    total = len(items)
-    nk = len(_csfloat_api_keys())
+
+def _print_mode_notes(
+    *,
+    pie: bool,
+    sc: int,
+    fetch_eur: bool,
+    want_eur_column: bool,
+    want_usd_column: bool,
+    nk: int,
+    usd_eur: float | None,
+    fx_src: str,
+) -> None:
     if nk > 1:
         print(f"CSFloat: {nk} API keys — round-robin per request\n")
-
-    sym = _STEAM_SYM.get(sc, "")
-    want_eur_column = (not pie) and fetch_eur and sc == 1
-    want_usd_column = (not pie) and fetch_eur and sc == 3
-    if fetch_eur and sc not in (1, 3):
-        print("Note: STEAM_FETCH_EUR_ALSO only adds EUR/USD pair when primary is USD (1) or EUR (3).\n")
-    if want_eur_column or want_usd_column:
+    if pie and usd_eur is not None:
         print(
-            "Note: extra Steam column for UI cross-check; spread_% still uses primary steam_ask vs Float USD.\n"
+            f"PRICES_IN_EUR: Steam EUR + Float USD×{usd_eur:.6f} (€ per $1; EUR = USD×this) — {fx_src}\n"
         )
+    if fetch_eur and sc not in (1, 3):
+        print("Note: STEAM_FETCH_EUR_ALSO works only for USD (1) or EUR (3).\n")
+    if want_eur_column or want_usd_column:
+        print("Note: extra Steam column is for cross-check; spread_% still uses primary steam_ask.\n")
     if (not pie) and sc != 1:
+        print("Note: steam_ask is not USD — spread_% vs CSFloat may mix currencies.\n")
+
+
+def _build_rows(
+    *,
+    items: list[str],
+    steam_prices: dict[str, float | None],
+    steam_prices_alt: dict[str, float | None],
+    float_data: dict[str, dict | None],
+    pie: bool,
+    usd_eur: float | None,
+    want_eur_column: bool,
+    want_usd_column: bool,
+) -> list[dict[str, object]]:
+    rows: list[dict[str, object]] = []
+    for name in items:
+        steam_price = steam_prices.get(name)
+        fd = float_data.get(name)
+        if not steam_price or not fd or not fd["ask"] or not fd.get("predicted"):
+            continue
+        if pie and usd_eur is not None:
+            float_ask = fd["ask"] * usd_eur
+            float_pred = fd["predicted"] * usd_eur
+            float_base = (fd["base"] * usd_eur) if fd.get("base") else None
+            row = {
+                "item": name,
+                "steam_ask": round(steam_price, 2),
+                "float_ask": round(float_ask, 2),
+                "float_pred": round(float_pred, 2),
+                "float_base": round(float_base, 2) if float_base is not None else None,
+                "float_qty": fd.get("quantity"),
+                "spread_ask%": round((steam_price - float_ask) / steam_price * 100, 2),
+                "spread_pred%": round((steam_price - float_pred) / steam_price * 100, 2),
+                "fx_usd_to_eur": round(usd_eur, 6),
+            }
+        else:
+            row = {
+                "item": name,
+                "steam_ask": round(steam_price, 2),
+                "float_ask": round(fd["ask"], 2),
+                "float_pred": round(fd["predicted"], 2),
+                "float_base": round(fd["base"], 2) if fd.get("base") else None,
+                "float_qty": fd.get("quantity"),
+                "spread_ask%": round((steam_price - fd["ask"]) / steam_price * 100, 2),
+                "spread_pred%": round((steam_price - fd["predicted"]) / steam_price * 100, 2),
+            }
+        alt = steam_prices_alt.get(name)
+        if want_eur_column:
+            row["steam_ask_eur"] = round(alt, 2) if alt is not None else None
+        elif want_usd_column:
+            row["steam_ask_usd"] = round(alt, 2) if alt is not None else None
+        rows.append(row)
+    return rows
+
+
+def _finalize_df(rows: list[dict[str, object]]) -> pd.DataFrame:
+    df = pd.DataFrame(rows)
+    if not df.empty:
+        df = df.sort_values(
+            "spread_pred%", ascending=False).reset_index(drop=True)
+    return df
+
+
+def _fetch_all_prices_sync(
+    items: list[str],
+    steam_delay: float,
+    float_delay: float,
+    float_workers: int,
+    *,
+    steam_currency: int | None,
+    steam_fetch_eur_also: bool | None,
+    prices_in_eur: bool | None,
+) -> pd.DataFrame:
+    pie, sc, fetch_eur, want_eur_column, want_usd_column = _prepare_mode(
+        steam_currency=steam_currency,
+        steam_fetch_eur_also=steam_fetch_eur_also,
+        prices_in_eur=prices_in_eur,
+    )
+    usd_eur: float | None = None
+    fx_src = ""
+    if pie:
+        usd_eur, fx_src = fetch_usd_to_eur_multiplier()
+    _print_mode_notes(
+        pie=pie,
+        sc=sc,
+        fetch_eur=fetch_eur,
+        want_eur_column=want_eur_column,
+        want_usd_column=want_usd_column,
+        nk=len(_csfloat_api_keys()),
+        usd_eur=usd_eur,
+        fx_src=fx_src,
+    )
+
+    steam_prices: dict[str, float | None] = {}
+    steam_prices_alt: dict[str, float | None] = {}
+    float_data: dict[str, dict | None] = {}
+    lock = threading.Lock()
+    total = len(items)
+    sym = _STEAM_SYM.get(sc, "")
+    keys = _csfloat_api_keys()
+    proxies = _proxy_endpoints()
+    steam_proxy_pool = SyncRotationPool(proxies) if proxies else None
+    float_identity_pool = SyncRotationPool(
+        _build_csfloat_identities(keys, proxies)) if proxies else None
+    if proxies:
         print(
-            "Note: steam_ask is not USD — spread_% vs CSFloat (USD) mixes currencies unless you convert.\n"
+            f"Proxy mode: {len(proxies)} IPs for Steam; "
+            f"{len(float_identity_pool.items) if float_identity_pool is not None else 0} CSFloat key/IP identities\n"
         )
 
-    def steam_worker():
+    def steam_worker() -> None:
         for i, name in enumerate(items):
-            price = get_steam_price(name, currency=sc)
-            eur_p: float | None = None
-            usd_p: float | None = None
+            price = get_steam_price(
+                name, currency=sc, proxy_pool=steam_proxy_pool)
+            alt: float | None = None
             if want_eur_column:
-                eur_p = get_steam_price(name, currency=3)
+                alt = get_steam_price(
+                    name, currency=3, proxy_pool=steam_proxy_pool)
             elif want_usd_column:
-                usd_p = get_steam_price(name, currency=1)
+                alt = get_steam_price(
+                    name, currency=1, proxy_pool=steam_proxy_pool)
             with lock:
                 steam_prices[name] = price
-                if want_eur_column:
-                    steam_prices_alt[name] = eur_p
-                elif want_usd_column:
-                    steam_prices_alt[name] = usd_p
-                else:
-                    steam_prices_alt[name] = None
-                tag = f"{sym}{price:.2f}" if price else "MISS"
-                if eur_p is not None:
-                    tag += f"  (€{eur_p:.2f})"
-                if usd_p is not None:
-                    tag += f"  (${usd_p:.2f})"
-                print(f"  ☁ Steam  [{i+1}/{total}] {name}: {tag}")
+                steam_prices_alt[name] = alt
+                tag = f"{sym}{price:.2f}" if price is not None else "MISS"
+                if want_eur_column and alt is not None:
+                    tag += f"  (€{alt:.2f})"
+                if want_usd_column and alt is not None:
+                    tag += f"  (${alt:.2f})"
+                print(f"  ☁ Steam  [{i + 1}/{total}] {name}: {tag}")
             if i < total - 1:
                 _inter_request_delay("STEAM_DELAY", steam_delay)
 
-    def float_fetch_one(pair):
+    def float_fetch_one(pair: tuple[int, str]) -> None:
         i, name = pair
-        fd = get_csfloat_prices(name)
+        fd = get_csfloat_prices(name, identity_pool=float_identity_pool)
         ks = _csfloat_key_suffix()
         with lock:
             float_data[name] = fd
             if fd and fd.get("predicted") is not None:
                 if pie and usd_eur is not None:
-                    ae = fd["ask"] * usd_eur
-                    pe = fd["predicted"] * usd_eur
                     print(
-                        f"  🔷 Float  [{i+1}/{total}] {name}: ask=€{ae:.2f} (${fd['ask']:.2f})  "
-                        f"pred=€{pe:.2f} (${fd['predicted']:.2f}){ks}"
+                        f"  🔷 Float  [{i + 1}/{total}] {name}: ask=€{fd['ask'] * usd_eur:.2f} (${fd['ask']:.2f})  "
+                        f"pred=€{fd['predicted'] * usd_eur:.2f} (${fd['predicted']:.2f}){ks}"
                     )
                 else:
                     print(
-                        f"  🔷 Float  [{i+1}/{total}] {name}: ask=${fd['ask']:.2f}  "
+                        f"  🔷 Float  [{i + 1}/{total}] {name}: ask=${fd['ask']:.2f}  "
                         f"pred=${fd['predicted']:.2f}{ks}"
                     )
             elif fd:
-                if pie and usd_eur is not None:
-                    ae = fd["ask"] * usd_eur
-                    print(
-                        f"  🔷 Float  [{i+1}/{total}] {name}: ask=€{ae:.2f} (${fd['ask']:.2f})  "
-                        f"pred=n/a{ks}"
-                    )
-                else:
-                    print(
-                        f"  🔷 Float  [{i+1}/{total}] {name}: ask=${fd['ask']:.2f}  "
-                        f"pred=n/a{ks}"
-                    )
+                print(
+                    f"  🔷 Float  [{i + 1}/{total}] {name}: ask=${fd['ask']:.2f}  pred=n/a{ks}")
             else:
-                print(f"  🔷 Float  [{i+1}/{total}] {name}: MISS{ks}")
+                print(f"  🔷 Float  [{i + 1}/{total}] {name}: MISS{ks}")
         _inter_request_delay("FLOAT_DELAY", float_delay)
 
-    def float_worker_parallel():
-        with ThreadPoolExecutor(max_workers=max(1, float_workers)) as pool:
-            list(pool.map(float_fetch_one, enumerate(items)))
+    def float_worker_parallel() -> None:
+        with ThreadPoolExecutor(max_workers=max(1, float_workers)) as inner_pool:
+            list(inner_pool.map(float_fetch_one, enumerate(items)))
 
     t0 = time.time()
     with ThreadPoolExecutor(max_workers=2) as pool:
@@ -601,51 +1368,260 @@ def fetch_all_prices(
         fut_f = pool.submit(float_worker_parallel)
         fut_s.result()
         fut_f.result()
+    rows = _build_rows(
+        items=items,
+        steam_prices=steam_prices,
+        steam_prices_alt=steam_prices_alt,
+        float_data=float_data,
+        pie=pie,
+        usd_eur=usd_eur,
+        want_eur_column=want_eur_column,
+        want_usd_column=want_usd_column,
+    )
+    df = _finalize_df(rows)
     elapsed = time.time() - t0
+    tail = f"  ({len(rows)}/{len(items)} items with both prices)"
+    if pie:
+        tail += " — все цены и спреды в EUR"
+    print(f"\n⏱ Done in {elapsed:.0f}s{tail}")
+    return df
 
-    rows = []
-    for name in items:
-        s = steam_prices.get(name)
-        fd = float_data.get(name)
-        if s and fd and fd["ask"] and fd.get("predicted"):
-            if pie and usd_eur is not None:
-                f_ask = fd["ask"] * usd_eur
-                f_pred = fd["predicted"] * usd_eur
-                f_base = (fd["base"] * usd_eur) if fd.get("base") else None
-                row = {
-                    "item": name,
-                    "steam_ask": round(s, 2),
-                    "float_ask": round(f_ask, 2),
-                    "float_pred": round(f_pred, 2),
-                    "float_base": round(f_base, 2) if f_base is not None else None,
-                    "float_qty": fd.get("quantity"),
-                    "spread_ask%": round((s - f_ask) / s * 100, 2),
-                    "spread_pred%": round((s - f_pred) / s * 100, 2),
-                    "fx_usd_to_eur": round(usd_eur, 6),
-                }
-            else:
-                row = {
-                    "item": name,
-                    "steam_ask": round(s, 2),
-                    "float_ask": round(fd["ask"], 2),
-                    "float_pred": round(fd["predicted"], 2),
-                    "float_base": round(fd["base"], 2) if fd.get("base") else None,
-                    "float_qty": fd.get("quantity"),
-                    "spread_ask%": round((s - fd["ask"]) / s * 100, 2),
-                    "spread_pred%": round((s - fd["predicted"]) / s * 100, 2),
-                }
-            alt = steam_prices_alt.get(name)
+
+async def _fetch_all_prices_async(
+    items: list[str],
+    steam_delay: float,
+    float_delay: float,
+    float_workers: int,
+    *,
+    steam_currency: int | None,
+    steam_fetch_eur_also: bool | None,
+    prices_in_eur: bool | None,
+    steam_concurrency: int | None,
+    float_concurrency: int | None,
+) -> pd.DataFrame:
+    pie, sc, fetch_eur, want_eur_column, want_usd_column = _prepare_mode(
+        steam_currency=steam_currency,
+        steam_fetch_eur_also=steam_fetch_eur_also,
+        prices_in_eur=prices_in_eur,
+    )
+    resolved_steam_concurrency = max(
+        1,
+        steam_concurrency
+        if steam_concurrency is not None
+        else _runtime_int("STEAM_CONCURRENCY", STEAM_MAX_CONCURRENCY),
+    )
+    resolved_float_concurrency = max(
+        1,
+        float_concurrency
+        if float_concurrency is not None
+        else _runtime_int(
+            "FLOAT_CONCURRENCY",
+            float_workers if float_workers != FLOAT_MAX_WORKERS else max(
+                2, FLOAT_MAX_WORKERS),
+        ),
+    )
+    steam_prices: dict[str, float | None] = {}
+    steam_prices_alt: dict[str, float | None] = {}
+    float_data: dict[str, dict | None] = {}
+    total = len(items)
+    sym = _STEAM_SYM.get(sc, "")
+    keys = _csfloat_api_keys()
+    proxies = _proxy_endpoints()
+    steam_proxy_pool = AsyncRotationPool(proxies) if proxies else None
+    float_identity_pool = AsyncRotationPool(
+        _build_csfloat_identities(keys, proxies))
+    steam_limiter = _AsyncStartLimiter("STEAM_DELAY", steam_delay)
+    float_limiter = _AsyncStartLimiter("FLOAT_DELAY", float_delay)
+    steam_sem = asyncio.Semaphore(resolved_steam_concurrency)
+    float_sem = asyncio.Semaphore(resolved_float_concurrency)
+
+    t0 = time.time()
+    async with _AsyncSessionPool() as sessions:
+        usd_eur: float | None = None
+        fx_src = ""
+        if pie:
+            usd_eur, fx_src = await _async_fetch_usd_to_eur_multiplier(sessions.for_proxy(None))
+        _print_mode_notes(
+            pie=pie,
+            sc=sc,
+            fetch_eur=fetch_eur,
+            want_eur_column=want_eur_column,
+            want_usd_column=want_usd_column,
+            nk=len(keys),
+            usd_eur=usd_eur,
+            fx_src=fx_src,
+        )
+        print(
+            f"Async mode: Steam concurrency={resolved_steam_concurrency}, "
+            f"CSFloat concurrency={resolved_float_concurrency}\n"
+        )
+        if proxies:
+            print(
+                f"Proxy mode: {len(proxies)} IPs for Steam; "
+                f"{len(float_identity_pool.items)} CSFloat key/IP identities\n"
+            )
+
+        async def steam_task(i: int, name: str) -> None:
+            price = await _async_get_steam_price(
+                sessions,
+                steam_limiter,
+                steam_sem,
+                steam_proxy_pool,
+                name,
+                sc,
+            )
+            alt: float | None = None
             if want_eur_column:
-                row["steam_ask_eur"] = round(alt, 2) if alt is not None else None
+                alt = await _async_get_steam_price(
+                    sessions,
+                    steam_limiter,
+                    steam_sem,
+                    steam_proxy_pool,
+                    name,
+                    3,
+                )
             elif want_usd_column:
-                row["steam_ask_usd"] = round(alt, 2) if alt is not None else None
-            rows.append(row)  # fd["_key"] в CSV не попадает
-
-    df = pd.DataFrame(rows)
-    if not df.empty:
-        df = df.sort_values("spread_pred%", ascending=False).reset_index(drop=True)
-    tail = f"  ({len(rows)}/{total} items with both prices)"
+                alt = await _async_get_steam_price(
+                    sessions,
+                    steam_limiter,
+                    steam_sem,
+                    steam_proxy_pool,
+                    name,
+                    1,
+                )
+            steam_prices[name] = price
+            steam_prices_alt[name] = alt
+            tag = f"{sym}{price:.2f}" if price is not None else "MISS"
+            if want_eur_column and alt is not None:
+                tag += f"  (€{alt:.2f})"
+            if want_usd_column and alt is not None:
+                tag += f"  (${alt:.2f})"
+            print(f"  ☁ Steam  [{i + 1}/{total}] {name}: {tag}")
+
+        async def float_task(i: int, name: str) -> None:
+            fd = await _async_get_csfloat_prices(
+                sessions,
+                float_limiter,
+                float_sem,
+                float_identity_pool,
+                name,
+            )
+            float_data[name] = fd
+            ks = f", key={fd.get('_key')}" if fd and fd.get("_key") else ""
+            if fd and fd.get("predicted") is not None:
+                if pie and usd_eur is not None:
+                    print(
+                        f"  🔷 Float  [{i + 1}/{total}] {name}: ask=€{fd['ask'] * usd_eur:.2f} (${fd['ask']:.2f})  "
+                        f"pred=€{fd['predicted'] * usd_eur:.2f} (${fd['predicted']:.2f}){ks}"
+                    )
+                else:
+                    print(
+                        f"  🔷 Float  [{i + 1}/{total}] {name}: ask=${fd['ask']:.2f}  "
+                        f"pred=${fd['predicted']:.2f}{ks}"
+                    )
+            elif fd:
+                print(
+                    f"  🔷 Float  [{i + 1}/{total}] {name}: ask=${fd['ask']:.2f}  pred=n/a{ks}")
+            else:
+                print(f"  🔷 Float  [{i + 1}/{total}] {name}: MISS")
+
+        tasks = [asyncio.create_task(steam_task(i, name))
+                 for i, name in enumerate(items)]
+        tasks.extend(asyncio.create_task(float_task(i, name))
+                     for i, name in enumerate(items))
+        await asyncio.gather(*tasks)
+
+    rows = _build_rows(
+        items=items,
+        steam_prices=steam_prices,
+        steam_prices_alt=steam_prices_alt,
+        float_data=float_data,
+        pie=pie,
+        usd_eur=usd_eur,
+        want_eur_column=want_eur_column,
+        want_usd_column=want_usd_column,
+    )
+    df = _finalize_df(rows)
+    elapsed = time.time() - t0
+    tail = f"  ({len(rows)}/{len(items)} items with both prices)"
     if pie:
         tail += " — все цены и спреды в EUR"
     print(f"\n⏱ Done in {elapsed:.0f}s{tail}")
     return df
+
+
+def _run_coro_sync(coro: object) -> object:
+    try:
+        asyncio.get_running_loop()
+    except RuntimeError:
+        return asyncio.run(coro)
+
+    result: dict[str, object] = {}
+    error: dict[str, BaseException] = {}
+
+    def runner() -> None:
+        try:
+            result["value"] = asyncio.run(coro)
+        except BaseException as exc:  # pragma: no cover - passthrough from background thread
+            error["value"] = exc
+
+    thread = threading.Thread(target=runner, daemon=True)
+    thread.start()
+    thread.join()
+    if "value" in error:
+        raise error["value"]
+    return result.get("value")
+
+
+def fetch_all_prices(
+    items: list[str],
+    steam_delay: float = STEAM_DELAY,
+    float_delay: float = FLOAT_DELAY,
+    float_workers: int = FLOAT_MAX_WORKERS,
+    *,
+    steam_currency: int | None = None,
+    steam_fetch_eur_also: bool | None = None,
+    prices_in_eur: bool | None = None,
+    steam_concurrency: int | None = None,
+    float_concurrency: int | None = None,
+    use_async: bool | None = None,
+) -> pd.DataFrame:
+    _refresh_env_settings()
+    _ensure_pandas()
+    resolved_use_async = FETCHERS_USE_AIOHTTP if use_async is None else use_async
+    if resolved_use_async and aiohttp is None:
+        global _warned_no_aiohttp
+        msg = "aiohttp не установлен; async path недоступен. Установите `aiohttp`, чтобы ускорить batch-fetching."
+        if FETCHERS_REQUIRE_AIOHTTP:
+            raise RuntimeError(msg)
+        if not _warned_no_aiohttp:
+            print(
+                f"  [fetchers] {msg} Переключаюсь на requests/threading fallback.\n", flush=True)
+            _warned_no_aiohttp = True
+        resolved_use_async = False
+    if resolved_use_async:
+        return _run_coro_sync(
+            _fetch_all_prices_async(
+                items,
+                steam_delay,
+                float_delay,
+                float_workers,
+                steam_currency=steam_currency,
+                steam_fetch_eur_also=steam_fetch_eur_also,
+                prices_in_eur=prices_in_eur,
+                steam_concurrency=steam_concurrency,
+                float_concurrency=float_concurrency,
+            )
+        )
+    return _fetch_all_prices_sync(
+        items,
+        steam_delay,
+        float_delay,
+        float_workers,
+        steam_currency=steam_currency,
+        steam_fetch_eur_also=steam_fetch_eur_also,
+        prices_in_eur=prices_in_eur,
+    )
+
+
+_refresh_env_settings()
diff --git a/base_screening_and_anal/fetchers_runtime.example.json b/base_screening_and_anal/fetchers_runtime.example.json
new file mode 100644
index 0000000..e87011d
--- /dev/null
+++ b/base_screening_and_anal/fetchers_runtime.example.json
@@ -0,0 +1,39 @@
+{
+  "__READ_ME__": "Пример runtime-конфига для fetchers.py. Скопируй в fetcher_runtime.json или fetchers_runtime.json и правь числа без изменения кода.",
+  "__STEAM_DELAY__": "база (сек) между стартами Steam-запросов; фактический интервал 0.5×…1.5×",
+  "STEAM_DELAY": 4.0,
+  "__FLOAT_DELAY__": "база (сек) между стартами CSFloat-запросов; фактический интервал 0.5×…1.5×",
+  "FLOAT_DELAY": 3.0,
+  "__STEAM_CONCURRENCY__": "максимум одновременных in-flight Steam-запросов в async-режиме",
+  "STEAM_CONCURRENCY": 4,
+  "__FLOAT_CONCURRENCY__": "максимум одновременных in-flight CSFloat-запросов в async-режиме",
+  "FLOAT_CONCURRENCY": 2,
+  "__HTTP_TIMEOUT_SEC__": "общий timeout для Steam/CSFloat HTTP-запросов",
+  "HTTP_TIMEOUT_SEC": 15.0,
+  "__FX_TIMEOUT_SEC__": "timeout для запроса курса USD->EUR",
+  "FX_TIMEOUT_SEC": 20.0,
+  "__KEY_COOLDOWN_429_SEC__": "после 429 на ключе CSFloat — пауза только этого ключа (сек)",
+  "KEY_COOLDOWN_429_SEC": 900.0,
+  "__KEY_COOLDOWN_403_SEC__": "после 403 на ключе CSFloat — пауза только этого ключа (сек)",
+  "KEY_COOLDOWN_403_SEC": 900.0,
+  "__STEAM_429_RETRY_WAIT_SEC__": "пауза перед повтором Steam-запроса после HTTP 429",
+  "STEAM_429_RETRY_WAIT_SEC": 120.0,
+  "__PROXY_COOLDOWN_429_SEC__": "если запрос через proxy получил 429 — пауза только этого IP или CSFloat key/IP пары",
+  "PROXY_COOLDOWN_429_SEC": 900.0,
+  "__PROXY_COOLDOWN_403_SEC__": "если запрос через proxy получил 403 — пауза только этого IP или CSFloat key/IP пары",
+  "PROXY_COOLDOWN_403_SEC": 900.0,
+  "__PROXY_ERROR_COOLDOWN_SEC__": "пауза proxy/IP или key/IP пары после сетевой ошибки",
+  "PROXY_ERROR_COOLDOWN_SEC": 60.0,
+  "__STEAM_NET_SLEEP_MIN__": "нижняя граница паузы при сетевой ошибке Steam",
+  "STEAM_NET_SLEEP_MIN": 3.0,
+  "__STEAM_NET_SLEEP_MAX__": "верхняя граница паузы при сетевой ошибке Steam",
+  "STEAM_NET_SLEEP_MAX": 12.0,
+  "__CSFLOAT_5XX_SLEEP_MIN__": "нижняя граница паузы перед повтором при ответе CSFloat 5xx",
+  "CSFLOAT_5XX_SLEEP_MIN": 5.0,
+  "__CSFLOAT_5XX_SLEEP_MAX__": "верхняя граница той же паузы",
+  "CSFLOAT_5XX_SLEEP_MAX": 15.0,
+  "__CSFLOAT_NET_SLEEP_MIN__": "нижняя граница паузы при сетевой ошибке CSFloat",
+  "CSFLOAT_NET_SLEEP_MIN": 3.0,
+  "__CSFLOAT_NET_SLEEP_MAX__": "верхняя граница той же паузы",
+  "CSFLOAT_NET_SLEEP_MAX": 10.0
+}
diff --git a/base_screening_and_anal/proxy_rotation.py b/base_screening_and_anal/proxy_rotation.py
new file mode 100644
index 0000000..a1960ea
--- /dev/null
+++ b/base_screening_and_anal/proxy_rotation.py
@@ -0,0 +1,245 @@
+from __future__ import annotations
+
+import asyncio
+import os
+import threading
+import time
+from dataclasses import dataclass
+from pathlib import Path
+from typing import Callable, Generic, TypeVar
+
+
+T = TypeVar("T")
+WEBSHARE_PROXY_CONFIG_URL = "https://proxy.webshare.io/api/v3/proxy/config"
+WEBSHARE_PROXY_DOWNLOAD_URL = "https://proxy.webshare.io/api/v2/proxy/list/download"
+
+_CACHE_LOCK = threading.Lock()
+_cache_signature: tuple[object, ...] | None = None
+_cache_endpoints: tuple["ProxyEndpoint", ...] = ()
+
+
+@dataclass(frozen=True)
+class ProxyEndpoint:
+    url: str
+    label: str
+
+    @property
+    def requests_proxies(self) -> dict[str, str]:
+        return {"http": self.url, "https": self.url}
+
+
+@dataclass(frozen=True)
+class RotationLease(Generic[T]):
+    item: T
+    index: int
+
+
+class SyncRotationPool(Generic[T]):
+    def __init__(self, items: tuple[T, ...] | list[T]) -> None:
+        self.items = tuple(items)
+        self._cooldowns: dict[int, float] = {}
+        self._rr_index = 0
+        self._lock = threading.Lock()
+
+    def acquire(self) -> RotationLease[T] | None:
+        if not self.items:
+            return None
+        while True:
+            with self._lock:
+                now = time.monotonic()
+                picked = self._try_pick_index(now)
+                if picked is not None:
+                    return RotationLease(self.items[picked], picked)
+                wake = min(self._cooldowns.get(i, 0.0) for i in range(len(self.items)))
+            time.sleep(max(0.05, wake - time.monotonic()))
+
+    def cooldown(self, index: int | None, seconds: float) -> None:
+        if index is None or seconds <= 0:
+            return
+        until = time.monotonic() + seconds
+        with self._lock:
+            self._cooldowns[index] = max(self._cooldowns.get(index, 0.0), until)
+
+    def _try_pick_index(self, now: float) -> int | None:
+        n = len(self.items)
+        start = self._rr_index % n
+        for step in range(n):
+            idx = (start + step) % n
+            if now >= self._cooldowns.get(idx, 0.0):
+                self._rr_index = idx + 1
+                return idx
+        return None
+
+
+class AsyncRotationPool(Generic[T]):
+    def __init__(self, items: tuple[T, ...] | list[T]) -> None:
+        self.items = tuple(items)
+        self._cooldowns: dict[int, float] = {}
+        self._rr_index = 0
+        self._lock = asyncio.Lock()
+
+    async def acquire(self) -> RotationLease[T] | None:
+        if not self.items:
+            return None
+        while True:
+            async with self._lock:
+                loop = asyncio.get_running_loop()
+                now = loop.time()
+                picked = self._try_pick_index(now)
+                if picked is not None:
+                    return RotationLease(self.items[picked], picked)
+                wake = min(self._cooldowns.get(i, 0.0) for i in range(len(self.items)))
+            await asyncio.sleep(max(0.05, wake - asyncio.get_running_loop().time()))
+
+    async def cooldown(self, index: int | None, seconds: float) -> None:
+        if index is None or seconds <= 0:
+            return
+        until = asyncio.get_running_loop().time() + seconds
+        async with self._lock:
+            self._cooldowns[index] = max(self._cooldowns.get(index, 0.0), until)
+
+    def _try_pick_index(self, now: float) -> int | None:
+        n = len(self.items)
+        start = self._rr_index % n
+        for step in range(n):
+            idx = (start + step) % n
+            if now >= self._cooldowns.get(idx, 0.0):
+                self._rr_index = idx + 1
+                return idx
+        return None
+
+
+def normalize_proxy_url(raw: str) -> str:
+    text = raw.strip()
+    if not text:
+        raise ValueError("empty proxy")
+    if "://" not in text:
+        text = f"http://{text}"
+    return text.rstrip("/")
+
+
+def parse_proxy_entries(text: str) -> tuple[ProxyEndpoint, ...]:
+    endpoints: list[ProxyEndpoint] = []
+    for raw in text.replace("\r\n", "\n").replace(",", "\n").splitlines():
+        line = raw.strip()
+        if not line:
+            continue
+        endpoints.append(_endpoint_from_entry(line, len(endpoints) + 1))
+    return tuple(endpoints)
+
+
+def fetch_webshare_proxies(
+    *,
+    api_key: str,
+    plan_id: str | int | None,
+    http_get: Callable[..., object],
+) -> tuple[ProxyEndpoint, ...]:
+    if not api_key:
+        return ()
+    params = {"plan_id": plan_id} if plan_id else None
+    response = http_get(
+        WEBSHARE_PROXY_CONFIG_URL,
+        params=params,
+        headers={"Authorization": f"Token {api_key}"},
+    )
+    _raise_for_status(response)
+    token = _json(response)["proxy_list_download_token"]
+    response = http_get(f"{WEBSHARE_PROXY_DOWNLOAD_URL}/{token}/-/any/username/direct/-/")
+    _raise_for_status(response)
+    return parse_proxy_entries(_text(response))
+
+
+def load_proxy_endpoints_from_env(
+    *,
+    http_get: Callable[..., object],
+    force_refresh: bool = False,
+) -> tuple[ProxyEndpoint, ...]:
+    static_text = os.environ.get("FETCHERS_PROXY_LIST", "")
+    file_path = os.environ.get("FETCHERS_PROXY_FILE", "")
+    webshare_key = os.environ.get("WEBSHARE_API_KEY", "")
+    webshare_plan_id = os.environ.get("WEBSHARE_PLAN_ID", "")
+    file_mtime: float | None = None
+    if file_path:
+        try:
+            file_mtime = Path(file_path).stat().st_mtime
+        except OSError:
+            file_mtime = None
+    signature = (static_text, file_path, file_mtime, webshare_key, webshare_plan_id)
+    global _cache_signature, _cache_endpoints
+    with _CACHE_LOCK:
+        if not force_refresh and signature == _cache_signature:
+            return _cache_endpoints
+    endpoints = _load_uncached(
+        static_text=static_text,
+        file_path=file_path,
+        webshare_key=webshare_key,
+        webshare_plan_id=webshare_plan_id,
+        http_get=http_get,
+    )
+    with _CACHE_LOCK:
+        _cache_signature = signature
+        _cache_endpoints = endpoints
+    return endpoints
+
+
+def clear_proxy_cache() -> None:
+    global _cache_signature, _cache_endpoints
+    with _CACHE_LOCK:
+        _cache_signature = None
+        _cache_endpoints = ()
+
+
+def _load_uncached(
+    *,
+    static_text: str,
+    file_path: str,
+    webshare_key: str,
+    webshare_plan_id: str,
+    http_get: Callable[..., object],
+) -> tuple[ProxyEndpoint, ...]:
+    if static_text.strip():
+        return parse_proxy_entries(static_text)
+    if file_path.strip():
+        return parse_proxy_entries(Path(file_path).read_text(encoding="utf-8"))
+    if webshare_key.strip():
+        return fetch_webshare_proxies(
+            api_key=webshare_key.strip(),
+            plan_id=webshare_plan_id.strip() or None,
+            http_get=http_get,
+        )
+    return ()
+
+
+def _endpoint_from_entry(entry: str, ordinal: int) -> ProxyEndpoint:
+    parts = entry.split(":")
+    if "://" not in entry and len(parts) == 4:
+        addr, port, username, password = parts
+        url = normalize_proxy_url(f"{username}:{password}@{addr}:{port}")
+        label = f"{ordinal}:{addr}:{port}"
+        return ProxyEndpoint(url=url, label=label)
+    url = normalize_proxy_url(entry)
+    label = f"{ordinal}:{url.rsplit('@', 1)[-1].replace('http://', '').replace('https://', '')}"
+    return ProxyEndpoint(url=url, label=label)
+
+
+def _raise_for_status(response: object) -> None:
+    raise_for_status = getattr(response, "raise_for_status", None)
+    if callable(raise_for_status):
+        raise_for_status()
+
+
+def _json(response: object) -> dict:
+    data = response.json()
+    if not isinstance(data, dict):
+        raise ValueError("Webshare response was not a JSON object")
+    return data
+
+
+def _text(response: object) -> str:
+    text = getattr(response, "text", None)
+    if isinstance(text, str):
+        return text
+    content = getattr(response, "content", b"")
+    if isinstance(content, bytes):
+        return content.decode("utf-8")
+    return str(content)
diff --git a/optimization_experiments/fetch_csfloat.py b/optimization_experiments/fetch_csfloat.py
new file mode 100644
index 0000000..491710b
--- /dev/null
+++ b/optimization_experiments/fetch_csfloat.py
@@ -0,0 +1,16 @@
+import requests
+import os
+
+API_KEY_CSFLOAT = os.getenv('API_KEY_CSFLOAT')
+
+url = "https://csfloat.com/api/v1/listings"
+
+
+headers = {
+    "Authorization": API_KEY_CSFLOAT
+}
+
+response = requests.get(url, headers=headers)
+
+with open('response.txt', 'w') as out:
+    out.write(response.text)
diff --git a/optimization_experiments/response.txt b/optimization_experiments/response.txt
new file mode 100644
index 0000000..9723408
--- /dev/null
+++ b/optimization_experiments/response.txt
@@ -0,0 +1 @@
+{"data":[{"id":"921281424596796604","created_at":"2025-12-17T06:03:28.205292Z","type":"buy_now","price":5394598,"state":"listed","seller":{"away":false,"flags":48,"obfuscated_id":"13440210935028223131","online":false,"stall_public":false,"statistics":{"median_trade_time":760,"total_avoided_trades":0,"total_failed_trades":0,"total_trades":217,"total_verified_trades":217}},"reference":{"base_price":5788333,"predicted_price":5788333,"quantity":6,"last_updated":"2026-04-19T16:07:50.188806Z"},"item":{"asset_id":"14350871212","def_index":1209,"sticker_index":74,"icon_url":"i0CoZ81Ui0m-9KwlBY1L_18myuGuq1wfhWSaZgMttyVfPaERSR0Wqmu7LAocGJai0ki7VeTHjM-sJnCW8Vli_YTxuAm2FVLjm5fz8ixk5_2iZ-o-I6PDX2HFxbsmtORsG3jgxEQm6mWHm9r9In_EbVV0DZciELULsRO-jJS5YC3mluwy","rarity":4,"market_hash_name":"Sticker | Reason Gaming (Holo) | Katowice 2014","tradable":0,"inspect_link":"steam://rungame/730/76561202255233023/+csgo_econ_action_preview%200010ACD583BB3518B9092804300062040800104AE9CF1F22","is_commodity":true,"type":"sticker","rarity_name":"Remarkable","type_name":"Sticker","item_name":"Reason Gaming (Holo) | Katowice 2014","serialized_inspect":"steam://rungame/730/76561202255233023/+csgo_econ_action_preview%200010ACD583BB3518B9092804300062040800104AE9CF1F22","gs_sig":"008256ae34803dedb2c8"},"is_seller":false,"min_offer_price":4963031,"max_offer_discount":800,"is_watchlisted":false,"watchers":122},{"id":"962154682048972331","created_at":"2026-04-09T00:59:12.171021Z","type":"auction","price":145481,"description":"better knucles than ft +fast del","state":"listed","seller":{"avatar":"https://avatars.steamstatic.com/6aff0cd427bb747e573a09bf632ecba253b3721d_full.jpg","away":false,"flags":48,"online":false,"stall_public":true,"statistics":{"median_trade_time":8320,"total_avoided_trades":1,"total_failed_trades":0,"total_trades":5740,"total_verified_trades":5740},"steam_id":"76561198010728916","username":"Salut"},"reference":{"base_price":397172,"float_factor":1.02404,"predicted_price":406718,"quantity":65,"last_updated":"2026-04-19T13:04:43.089691Z"},"item":{"asset_id":"50694512290","def_index":5030,"paint_index":10038,"paint_seed":169,"float_value":0.3844107389450073,"icon_url":"i0CoZ81Ui0m-9KwlBY1L_18myuGuq1wfhWSaZgMttyVfPaERSR0Wqmu7LAocGIGz3UqlXOLrxM-vMGmW8VNxu5Tk5UvzWCL2kpn2-DFk_OKherB0H_eBC2Ke_uNztOh8QmexzEwm5W3UnompICqQaFJxApt5EeZc4EO4kYayZuPitlHfjopNyy79kGoXufl0mJ2_","is_stattrak":false,"is_souvenir":false,"rarity":6,"quality":3,"market_hash_name":"★ Sport Gloves | Hedge Maze (Well-Worn)","tradable":0,"cs2_screenshot_id":"131811100789893184","cs2_screenshot_at":"2026-04-08T02:08:08.889674Z","is_commodity":false,"type":"skin","rarity_name":"Covert","type_name":"Skin","item_name":"★ Sport Gloves | Hedge Maze","wear_name":"Well-Worn","description":"The green and white gloves were manufactured by Icarus Athletics.\\n\\n\u003ci\u003eOnly cowards fear flying close to the sun\u003c/i\u003e","serialized_inspect":"steam://rungame/730/76561202255233023/+csgo_econ_action_preview%200010A2BD83EDBC0118A62720B64E2806300338FCA293F60340A9016C6C3A7B","gs_sig":"e349a87fceb3ed7cff44"},"is_seller":false,"min_offer_price":133843,"max_offer_discount":800,"is_watchlisted":false,"watchers":322,"auction_details":{"reserve_price":116,"top_bid":{"id":"963124037322672268","created_at":"2026-04-11T17:11:04.477346Z","price":145481,"contract_id":"962154682048972331","state":"active","obfuscated_buyer_id":"12822152401513019910"},"expires_at":"2026-04-23T00:59:12.170102Z","min_next_bid":147981}},{"id":"965052949275475988","created_at":"2026-04-17T00:55:52.924771Z","type":"auction","price":79599,"state":"listed","seller":{"away":false,"flags":48,"obfuscated_id":"9601504859486934255","online":false,"stall_public":false,"statistics":{"median_trade_time":81,"total_avoided_trades":0,"total_failed_trades":0,"total_trades":95,"total_verified_trades":95}},"reference":{"base_price":310800,"float_factor":1.04516,"predicted_price":324836,"quantity":84,"last_updated":"2026-04-19T12:58:04.285268Z"},"item":{"asset_id":"50881986909","def_index":523,"paint_index":415,"paint_seed":652,"float_value":0.008384629152715206,"icon_url":"i0CoZ81Ui0m-9KwlBY1L_18myuGuq1wfhWSaZgMttyVfPaERSR0Wqmu7LAocGIGz3UqlXOLrxM-vMGmW8VNxu5Dx60noTyL6kJ_m-B1M5vahf6lsK_WBMWad_vxjsvhWQiihlxEiuieAnrD1KCzPKhgjDJt0TOZYsEWxm9C1ZOzqtgfW3oITxS_3jntJ6y5t4-YFA6YlrvaCkUifZtYs94Eq","is_stattrak":false,"is_souvenir":false,"rarity":6,"quality":3,"market_hash_name":"★ Talon Knife | Doppler (Factory New)","tradable":0,"inspect_link":"steam://rungame/730/76561202255233023/+csgo_econ_action_preview%200010DD82B6C6BD01188B04209F032806300338AFBFA5E003408C05A3573074","cs2_screenshot_id":"4360419515832947755","cs2_screenshot_at":"2026-04-17T00:56:22.655111Z","is_commodity":false,"type":"skin","rarity_name":"Covert","type_name":"Skin","item_name":"★ Talon Knife | Doppler","wear_name":"Factory New","phase":"Ruby","description":"It has been painted with black and silver metallic paints using a marbleizing medium, then candy coated.\\n\\n\u003ci\u003eGetting lost in its color can prove fatal\u003c/i\u003e","serialized_inspect":"steam://rungame/730/76561202255233023/+csgo_econ_action_preview%200010DD82B6C6BD01188B04209F032806300338AFBFA5E003408C05A3573074","gs_sig":"a89248ea37dc0eafc6ec"},"is_seller":false,"min_offer_price":77610,"max_offer_discount":250,"is_watchlisted":false,"watchers":411,"auction_details":{"reserve_price":3,"top_bid":{"id":"965979862521219411","created_at":"2026-04-19T14:19:06.263326Z","price":79599,"contract_id":"965052949275475988","state":"active","obfuscated_buyer_id":"832816080242942741"},"expires_at":"2026-04-24T00:55:52.921493Z","min_next_bid":80599}},{"id":"965492592689154220","created_at":"2026-04-18T06:02:52.082623Z","type":"auction","price":31813,"state":"listed","seller":{"away":false,"flags":48,"obfuscated_id":"3217506944058370380","online":false,"stall_public":false,"statistics":{"median_trade_time":30,"total_avoided_trades":1,"total_failed_trades":1,"total_trades":1236,"total_verified_trades":1235}},"reference":{"base_price":250741,"float_factor":1.03523,"predicted_price":259576,"quantity":107,"last_updated":"2026-04-19T18:04:02.247009Z"},"item":{"asset_id":"48142836754","def_index":5030,"paint_index":10037,"paint_seed":250,"float_value":0.6401206254959106,"icon_url":"i0CoZ81Ui0m-9KwlBY1L_18myuGuq1wfhWSaZgMttyVfPaERSR0Wqmu7LAocGIGz3UqlXOLrxM-vMGmW8VNxu5Tk5UvzWCL2kpn2-DFk_OKherB0H-CGHHecxNF-teB_Vme1k0915jzQy9_4di6RP1B1W8YiTeMMsUXtxNO1M-rjtQTXi91Bni75kGoXuRHZuJI2","is_stattrak":false,"is_souvenir":false,"rarity":6,"quality":3,"market_hash_name":"★ Sport Gloves | Pandora's Box (Battle-Scarred)","tradable":0,"inspect_link":"steam://rungame/730/76561202255233023/+csgo_econ_action_preview%20001092C8A5ACB30118A62720B54E2806300338F2BD8FF90340FA01196FCB68","cs2_screenshot_id":"8372701346125914909","cs2_screenshot_at":"2026-04-12T15:10:24.176941Z","is_commodity":false,"type":"skin","rarity_name":"Covert","type_name":"Skin","item_name":"★ Sport Gloves | Pandora's Box","wear_name":"Battle-Scarred","description":"The black and purple gloves have a subtle pattern printed on the palms.\\n\\n\u003ci\u003eA must have for any demolitions expert with sweaty palms\u003c/i\u003e","serialized_inspect":"steam://rungame/730/76561202255233023/+csgo_econ_action_preview%20001092C8A5ACB30118A62720B54E2806300338F2BD8FF90340FA01196FCB68","gs_sig":"aa177049c68671b9561d"},"is_seller":false,"min_offer_price":29268,"max_offer_discount":800,"is_watchlisted":false,"watchers":131,"auction_details":{"reserve_price":100,"top_bid":{"id":"966029641376731013","created_at":"2026-04-19T17:36:54.467586Z","price":31813,"contract_id":"965492592689154220","state":"active","obfuscated_buyer_id":"14660243704851851366"},"expires_at":"2026-04-21T06:02:52.081604Z","min_next_bid":32313}},{"id":"965322120173322723","created_at":"2026-04-17T18:44:13.105089Z","type":"auction","price":96000,"description":"Almost max red right hand","state":"listed","seller":{"away":false,"flags":48,"obfuscated_id":"16683707585592862340","online":false,"stall_public":false,"statistics":{"median_trade_time":76,"total_avoided_trades":0,"total_failed_trades":0,"total_trades":81,"total_verified_trades":81}},"reference":{"base_price":301906,"float_factor":1.03848,"predicted_price":313523,"quantity":424,"last_updated":"2026-04-19T12:46:14.208759Z"},"item":{"asset_id":"50956827342","def_index":5034,"paint_index":10033,"paint_seed":970,"float_value":0.14778155088424683,"icon_url":"i0CoZ81Ui0m-9KwlBY1L_18myuGuq1wfhWSaZgMttyVfPaERSR0Wqmu7LAocGIGz3UqlXOLrxM-vMGmW8VNxu5Tk71ruQBH4jYLf-i5U-fe9V7d9JfOaD2uZ0vpJu-hkQCe8qhkusjCKlIvqHjnCOml8U8UoAfkItBLswdbuNbjr5FHdjNkUzSv73C1K5y46tu4EUvAg-6bU3FrBMOE4_9BdcyhkRns5","is_stattrak":false,"is_souvenir":false,"rarity":6,"quality":3,"market_hash_name":"★ Specialist Gloves | Crimson Kimono (Minimal Wear)","tradable":0,"inspect_link":"steam://rungame/730/76561202255233023/+csgo_econ_action_preview%200010CEF58DEABD0118AA2720B14E28063003388CA8DDF00340CA07DC68F416","cs2_screenshot_id":"37356231785516319","cs2_screenshot_at":"2026-04-16T17:13:40.332645Z","is_commodity":false,"type":"skin","rarity_name":"Covert","type_name":"Skin","item_name":"★ Specialist Gloves | Crimson Kimono","wear_name":"Minimal Wear","description":"This pair of black gloves has been accented with a stark red diamond pattern.\\n\\n\u003ci\u003eStart seeing red\u003c/i\u003e","serialized_inspect":"steam://rungame/730/76561202255233023/+csgo_econ_action_preview%200010CEF58DEABD0118AA2720B14E28063003388CA8DDF00340CA07DC68F416","gs_sig":"36710c802223194de44b"},"is_seller":false,"min_offer_price":91200,"max_offer_discount":500,"is_watchlisted":false,"watchers":225,"auction_details":{"reserve_price":100,"top_bid":{"id":"965789873581721296","created_at":"2026-04-19T01:44:09.370416Z","price":96000,"contract_id":"965322120173322723","state":"active","obfuscated_buyer_id":"2184953921413456601"},"expires_at":"2026-04-20T18:45:28.266094Z","min_next_bid":97000}},{"id":"963837834752558721","created_at":"2026-04-13T16:27:27.046837Z","type":"auction","price":96210,"state":"listed","seller":{"avatar":"https://avatars.steamstatic.com/b58709b049e0acb992c37a6219627171bdd0cf85_full.jpg","away":false,"flags":48,"online":false,"stall_public":true,"statistics":{"median_trade_time":2129,"total_avoided_trades":0,"total_failed_trades":1,"total_trades":61,"total_verified_trades":60},"steam_id":"76561198394632884","username":"Rabbe"},"reference":{"base_price":270385,"float_factor":1.1523,"predicted_price":311565,"quantity":117,"last_updated":"2026-04-19T16:31:14.863051Z"},"item":{"asset_id":"50434720035","def_index":5030,"paint_index":10038,"paint_seed":672,"float_value":0.5432136654853821,"icon_url":"i0CoZ81Ui0m-9KwlBY1L_18myuGuq1wfhWSaZgMttyVfPaERSR0Wqmu7LAocGIGz3UqlXOLrxM-vMGmW8VNxu5Tk5UvzWCL2kpn2-DFk_OKherB0H_eBC2Ke_uZzsfdwASjqkU1y4z7Rzdj9Ii2UP1UmWcB1QLRb5hDultzkZu3jtQLfiY0Qny_gznQezxOogAo","is_stattrak":false,"is_souvenir":false,"rarity":6,"quality":3,"market_hash_name":"★ Sport Gloves | Hedge Maze (Battle-Scarred)","tradable":0,"cs2_screenshot_id":"1239885709193868404","cs2_screenshot_at":"2026-04-08T12:26:59.70628Z","is_commodity":false,"type":"skin","rarity_name":"Covert","type_name":"Skin","item_name":"★ Sport Gloves | Hedge Maze","wear_name":"Battle-Scarred","description":"The green and white gloves were manufactured by Icarus Athletics.\\n\\n\u003ci\u003eOnly cowards fear flying close to the sun\u003c/i\u003e","serialized_inspect":"steam://rungame/730/76561202255233023/+csgo_econ_action_preview%200010A38293F1BB0118A62720B64E28063003388DA0ACF80340A0059D88793E","gs_sig":"5b6673635877b37329f9"},"is_seller":false,"min_offer_price":88514,"max_offer_discount":800,"is_watchlisted":false,"watchers":247,"auction_details":{"reserve_price":15,"top_bid":{"id":"965889030954814524","created_at":"2026-04-19T08:18:10.330178Z","price":96210,"contract_id":"963837834752558721","state":"active","obfuscated_buyer_id":"10231313308307990954"},"expires_at":"2026-04-20T16:27:27.045855Z","min_next_bid":97210}},{"id":"965604861859205106","created_at":"2026-04-18T13:28:59.138231Z","type":"auction","price":47800,"description":"full mango, good luck","state":"listed","seller":{"avatar":"https://avatars.steamstatic.com/bb8650c5ce736fcad11376b019765ed1a53bc279_full.jpg","away":false,"flags":48,"online":false,"stall_public":true,"statistics":{"median_trade_time":202,"total_avoided_trades":1,"total_failed_trades":0,"total_trades":332,"total_verified_trades":332},"steam_id":"76561198083765817","username":"sm9ke"},"reference":{"base_price":241325,"float_factor":1.04527,"predicted_price":252249,"quantity":1147,"last_updated":"2026-04-19T13:29:10.995061Z"},"item":{"asset_id":"50810664214","def_index":515,"paint_index":38,"paint_seed":578,"float_value":0.018230373039841652,"icon_url":"i0CoZ81Ui0m-9KwlBY1L_18myuGuq1wfhWSaZgMttyVfPaERSR0Wqmu7LAocGIGz3UqlXOLrxM-vMGmW8VNxu5Dx60noTyL6kJ_m-B1Z-ua6bbZrLOmsD2avx-9ytd5lRi67gVNwsDvSwtqqc3iXZg4kCZYjReYLtRbum9XgYuvm5wbWjtgUzCn3iSsf8G81tFEeH9rw","is_stattrak":false,"is_souvenir":false,"rarity":6,"quality":3,"market_hash_name":"★ Butterfly Knife | Fade (Factory New)","tradable":0,"cs2_screenshot_id":"4630565135705352922","cs2_screenshot_at":"2026-04-16T13:55:06.873426Z","is_commodity":false,"type":"skin","rarity_name":"Covert","type_name":"Skin","item_name":"★ Butterfly Knife | Fade","wear_name":"Factory New","description":"It has been painted by airbrushing transparent paints that fade together over a chrome base coat.\\n\\n\u003ci\u003eThis isn't just a weapon, it's a conversation piece - Imogen, Arms Dealer In Training\u003c/i\u003e","collection":"The Breakout Collection","fade":{"seed":578,"percentage":80.89932,"rank":960,"type":"fade"},"serialized_inspect":"steam://rungame/730/76561202255233023/+csgo_econ_action_preview%20001096EAB4A4BD0118830420262806300338DDAFD5E40340C204E32B6170","gs_sig":"9db3539e03309dc7e847"},"is_seller":false,"min_offer_price":46605,"max_offer_discount":250,"is_watchlisted":false,"watchers":199,"auction_details":{"reserve_price":100,"top_bid":{"id":"965960740269851256","created_at":"2026-04-19T13:03:07.163321Z","price":47800,"contract_id":"965604861859205106","state":"active","obfuscated_buyer_id":"3976737331531646089"},"expires_at":"2026-04-25T13:28:59.137189Z","min_next_bid":48300}},{"id":"964426557630318134","created_at":"2026-04-15T07:26:49.5185Z","type":"buy_now","price":2195100,"state":"listed","seller":{"away":false,"flags":48,"obfuscated_id":"11971544751259628748","online":false,"stall_public":false,"statistics":{"median_trade_time":0,"total_avoided_trades":0,"total_failed_trades":0,"total_trades":0,"total_verified_trades":0}},"reference":{"base_price":2387295,"predicted_price":2387295,"quantity":7,"last_updated":"2026-04-19T13:29:11.071327Z"},"item":{"asset_id":"3606313546","def_index":1209,"sticker_index":62,"icon_url":"i0CoZ81Ui0m-9KwlBY1L_18myuGuq1wfhWSaZgMttyVfPaERSR0Wqmu7LAocGJai0ki7VeTHjM-sJnCW8Vli_YTxuAm2FVL9mprjwipU4_3gbfU1c_bAXDKTwu8u4bhvG3qwxk1x4WXRyYuteXrDPFUnWJtwEbYJsQ74zIN29ZviPw","rarity":4,"market_hash_name":"Sticker | Team LDLC.com (Holo) | Katowice 2014","tradable":0,"inspect_link":"steam://rungame/730/76561202255233023/+csgo_econ_action_preview%200010CAF4CFB70D18B9092804300062040800103EE1F667E8","is_commodity":true,"type":"sticker","rarity_name":"Remarkable","type_name":"Sticker","item_name":"Team LDLC.com (Holo) | Katowice 2014","serialized_inspect":"steam://rungame/730/76561202255233023/+csgo_econ_action_preview%200010CAF4CFB70D18B9092804300062040800103EE1F667E8","gs_sig":"250559556c423d63ab8d"},"is_seller":false,"min_offer_price":2019492,"max_offer_discount":800,"is_watchlisted":false,"watchers":10},{"id":"965932745379416828","created_at":"2026-04-19T11:11:52.661067Z","type":"auction","price":24514,"state":"listed","seller":{"avatar":"https://avatars.steamstatic.com/955acfa7e1262ca35e6edfaccd258f4355ef7ed3_full.jpg","away":false,"flags":48,"online":false,"stall_public":true,"statistics":{"median_trade_time":78,"total_avoided_trades":0,"total_failed_trades":1,"total_trades":185,"total_verified_trades":184},"steam_id":"76561198798664114","username":"son."},"reference":{"base_price":205899,"float_factor":1.02981,"predicted_price":212038,"quantity":254,"last_updated":"2026-04-19T17:12:03.28159Z"},"item":{"asset_id":"51007453476","def_index":507,"paint_index":419,"paint_seed":721,"float_value":0.026702551171183586,"icon_url":"i0CoZ81Ui0m-9KwlBY1L_18myuGuq1wfhWSaZgMttyVfPaERSR0Wqmu7LAocGIGz3UqlXOLrxM-vMGmW8VNxu5Dx60noTyL6kJ_m-B1Q7uCvZaZkNM-SA1iUzv5mvOR7cDm7lA4i4QKJk4jxNWWXawUgA8dxRLEO40KwkobnMbnj5QKL348Qmy-sji5K7i466uxUUKQn5OSJ2KBZjkQR","is_stattrak":false,"is_souvenir":false,"rarity":6,"quality":3,"market_hash_name":"★ Karambit | Doppler (Factory New)","tradable":0,"cs2_screenshot_id":"2680335486288489890","cs2_screenshot_at":"2026-04-19T11:17:33.352096Z","is_commodity":false,"type":"skin","rarity_name":"Covert","type_name":"Skin","item_name":"★ Karambit | Doppler","wear_name":"Factory New","phase":"Phase 2","description":"It has been painted with black and silver metallic paints using a marbleizing medium, then candy coated.\\n\\n\u003ci\u003eGetting lost in its color can prove fatal\u003c/i\u003e","serialized_inspect":"steam://rungame/730/76561202255233023/+csgo_econ_action_preview%200010A4F29F82BE0118FB0320A3032806300338CFFEEAE60340D105E8B9DC76","gs_sig":"05fb73935ba15c4decc0"},"is_seller":false,"min_offer_price":22553,"max_offer_discount":800,"is_watchlisted":false,"watchers":85,"auction_details":{"reserve_price":100,"top_bid":{"id":"965990027987388319","created_at":"2026-04-19T14:59:29.899511Z","price":24514,"contract_id":"965932745379416828","state":"active","obfuscated_buyer_id":"11309817208122094198"},"expires_at":"2026-04-22T11:11:52.642507Z","min_next_bid":24764}},{"id":"767385397780153432","created_at":"2024-10-18T13:55:36.16206Z","type":"buy_now","price":2200049,"state":"listed","seller":{"away":false,"flags":48,"obfuscated_id":"4581459902900626601","online":false,"stall_public":false,"statistics":{"median_trade_time":732,"total_avoided_trades":3,"total_failed_trades":0,"total_trades":724,"total_verified_trades":724}},"reference":{"base_price":2387295,"predicted_price":2387295,"quantity":7,"last_updated":"2026-04-19T14:27:00.888904Z"},"item":{"asset_id":"38241303497","def_index":1209,"sticker_index":62,"icon_url":"-9a81dlWLwJ2UUGcVs_nsVtzdOEdtWwKGZZLQHTxDZ7I56KU0Zwwo4NUX4oFJZEHLbXQ9QVcJY8gulRYQV_bRvCiwMbQVg8kdFAYur6pKDho3P_HPzgTtI-wx9LelPT1a-qIkD8C65Yh3LuZod_x3AzlrxE_ZDv6JNLEcQUgIQaH6buXiJw","rarity":4,"market_hash_name":"Sticker | Team LDLC.com (Holo) | Katowice 2014","tradable":0,"inspect_link":"steam://rungame/730/76561202255233023/+csgo_econ_action_preview%200010C9F7EFBA8E0118B9092804300062040800103E13CA4380","is_commodity":true,"type":"sticker","rarity_name":"Remarkable","type_name":"Sticker","item_name":"Team LDLC.com (Holo) | Katowice 2014","serialized_inspect":"steam://rungame/730/76561202255233023/+csgo_econ_action_preview%200010C9F7EFBA8E0118B9092804300062040800103E13CA4380","gs_sig":"5b7af3eb3539d0c57398"},"is_seller":false,"min_offer_price":1760040,"max_offer_discount":2000,"is_watchlisted":false,"watchers":101},{"id":"892058898528339330","created_at":"2025-09-27T14:43:35.062817Z","type":"buy_now","price":1900000,"state":"listed","seller":{"avatar":"https://avatars.steamstatic.com/ce5ca412a9937418b1cc1e34879e45d6bb87b74f_full.jpg","away":false,"flags":48,"online":false,"stall_public":true,"statistics":{"median_trade_time":454,"total_avoided_trades":4,"total_failed_trades":5,"total_trades":1580,"total_verified_trades":1575},"steam_id":"76561198930819998","username":"!Haruno [H] 100 knife for trade"},"reference":{"base_price":1900000,"float_factor":1.09276,"predicted_price":2076242,"quantity":1,"last_updated":"2026-04-19T18:13:20.686959Z"},"item":{"asset_id":"46447565383","def_index":515,"paint_index":617,"paint_seed":534,"float_value":0.007043651770800352,"icon_url":"i0CoZ81Ui0m-9KwlBY1L_18myuGuq1wfhWSaZgMttyVfPaERSR0Wqmu7LAocGIGz3UqlXOLrxM-vMGmW8VNxu5Dx60noTyL6kJ_m-B1Z-ua6bbZrLOmsD2qvw-J3s-p5SiihmSIqsi-HlorwOy7DAVRPVssnHaMUuhe9xIHlMuvqtgPf2IoTyC383Sod7CY-sr4DVfZ2qKPU3g-TNuE-545DeqjFvb87vg","d_param":"16584730610025818129","is_stattrak":true,"is_souvenir":false,"rarity":6,"quality":3,"market_hash_name":"★ StatTrak™ Butterfly Knife | Doppler (Factory New)","low_rank":3,"high_rank":18,"tradable":0,"inspect_link":"steam://rungame/730/76561202255233023/+csgo_econ_action_preview%20S76561198930819998A46447565383D16584730610025818129","cs2_screenshot_id":"412515973809904657","cs2_screenshot_at":"2025-09-27T14:44:06.264026Z","is_commodity":false,"type":"skin","rarity_name":"Covert","type_name":"Skin","item_name":"★ Butterfly Knife | Doppler","wear_name":"Factory New","phase":"Black Pearl","description":"It has been painted with black and silver metallic paints using a marbleizing medium, then candy coated.\\n\\n\u003ci\u003eGetting lost in its color can prove fatal\u003c/i\u003e","badges":["silver_lowest_float"],"serialized_inspect":"steam://rungame/730/76561202255233023/+csgo_econ_action_preview%200010C7B4F683AD0118830420E9042806300338EF9C9BDF03409604480050B90AE654431E","gs_sig":"9e1f0863ad552e570438"},"is_seller":false,"min_offer_price":1520000,"max_offer_discount":2000,"is_watchlisted":false,"watchers":136},{"id":"965549271657087376","created_at":"2026-04-18T09:48:05.401198Z","type":"buy_now","price":4350000,"state":"listed","seller":{"avatar":"https://avatars.steamstatic.com/534f5720b73a81d10bec850eddbceadcbe407124_full.jpg","away":false,"flags":48,"online":false,"stall_public":true,"statistics":{"median_trade_time":984,"total_avoided_trades":2,"total_failed_trades":0,"total_trades":452,"total_verified_trades":452},"steam_id":"76561198336906701","username":"Mo"},"reference":{"base_price":4504775,"float_factor":1.00312,"predicted_price":4518818,"quantity":14,"last_updated":"2026-04-19T15:49:15.335791Z"},"item":{"asset_id":"47325864972","def_index":9,"paint_index":344,"paint_seed":332,"float_value":0.2604863941669464,"icon_url":"i0CoZ81Ui0m-9KwlBY1L_18myuGuq1wfhWSaZgMttyVfPaERSR0Wqmu7LAocGIGz3UqlXOLrxM-vMGmW8VNxu5Dx60noTyLwiYbf_jdk4veqYaF7IfysCnWRxuF4j-B-Xxa-kBkupjDLw96pcX6TZg5yCZJ5TbNZtxjtwNS2NemztgDbidoQyH-sjCga6no-6_FCD_QEyQmfGQ","is_stattrak":false,"is_souvenir":true,"rarity":6,"quality":12,"market_hash_name":"Souvenir AWP | Dragon Lore (Field-Tested)","stickers":[{"stickerId":1018,"slot":0,"icon_url":"https://steamcdn-a.akamaihd.net/apps/730/icons/econ/stickers/columbus2016/clg_gold_large.7b951db05b579718f279c2186640356c838d8d1b.png","name":"Sticker | Counter Logic Gaming (Gold) | MLG Columbus 2016"},{"stickerId":1089,"slot":1,"icon_url":"https://steamcdn-a.akamaihd.net/apps/730/icons/econ/stickers/columbus2016/sig_tarik_gold_large.f18df03aae62a974f9fe0e871df0334a1145f49b.png","name":"Sticker | tarik (Gold) | MLG Columbus 2016"},{"stickerId":1074,"slot":2,"icon_url":"https://steamcdn-a.akamaihd.net/apps/730/icons/econ/stickers/columbus2016/mlg_gold_large.205f8ecc5a9c43eda7dc7319508abd022b1fe164.png","name":"Sticker | MLG (Gold) | MLG Columbus 2016"},{"stickerId":1022,"slot":3,"icon_url":"https://steamcdn-a.akamaihd.net/apps/730/icons/econ/stickers/columbus2016/gamb_gold_large.a8c960bb15a7654d452a4899bffb2270a48ba35f.png","name":"Sticker | Gambit Gaming (Gold) | MLG Columbus 2016"}],"low_rank":71,"high_rank":46,"tradable":0,"cs2_screenshot_id":"7850983493680634050","cs2_screenshot_at":"2026-04-18T09:54:48.831322Z","is_commodity":false,"type":"skin","rarity_name":"Covert","type_name":"Skin","item_name":"AWP | Dragon Lore","wear_name":"Field-Tested","description":"It has been custom painted with a knotwork dragon.\\n\\n\u003ci\u003e200 keys could never unlock its secrets\u003c/i\u003e","collection":"The Cobblestone Collection","serialized_inspect":"steam://rungame/730/76561202255233023/+csgo_econ_action_preview%2000108CC8DDA6B001180920D8022806300C38F9BC95F40340CC02620A080010FA071D00000000620A080110C1081D00000000620A080210B2081D00000000620A080310FE071D0000000061F81858","gs_sig":"00f6d9d7e747094dab56"},"is_seller":false,"min_offer_price":4002000,"max_offer_discount":800,"is_watchlisted":false,"watchers":34},{"id":"965462412838963416","created_at":"2026-04-18T04:02:56.645219Z","type":"auction","price":56000,"state":"listed","seller":{"away":false,"flags":48,"obfuscated_id":"9601504859486934255","online":false,"stall_public":false,"statistics":{"median_trade_time":81,"total_avoided_trades":0,"total_failed_trades":0,"total_trades":95,"total_verified_trades":95}},"reference":{"base_price":205899,"float_factor":1.03058,"predicted_price":212195,"quantity":254,"last_updated":"2026-04-19T16:04:11.383036Z"},"item":{"asset_id":"50881986916","def_index":507,"paint_index":419,"paint_seed":287,"float_value":0.028539983555674553,"icon_url":"i0CoZ81Ui0m-9KwlBY1L_18myuGuq1wfhWSaZgMttyVfPaERSR0Wqmu7LAocGIGz3UqlXOLrxM-vMGmW8VNxu5Dx60noTyL6kJ_m-B1Q7uCvZaZkNM-SA1iUzv5mvOR7cDm7lA4i4QKJk4jxNWWXawUgA8dxRLEO40KwkobnMbnj5QKL348Qmy-sji5K7i466uxUUKQn5OSJ2KBZjkQR","is_stattrak":false,"is_souvenir":false,"rarity":6,"quality":3,"market_hash_name":"★ Karambit | Doppler (Factory New)","tradable":0,"inspect_link":"steam://rungame/730/76561202255233023/+csgo_econ_action_preview%200010E482B6C6BD0118FB0320A3032806300338AF99A7E703409F02B3E3C9CF","cs2_screenshot_id":"8836247345622067021","cs2_screenshot_at":"2026-04-18T04:03:20.88786Z","is_commodity":false,"type":"skin","rarity_name":"Covert","type_name":"Skin","item_name":"★ Karambit | Doppler","wear_name":"Factory New","phase":"Phase 2","description":"It has been painted with black and silver metallic paints using a marbleizing medium, then candy coated.\\n\\n\u003ci\u003eGetting lost in its color can prove fatal\u003c/i\u003e","serialized_inspect":"steam://rungame/730/76561202255233023/+csgo_econ_action_preview%200010E482B6C6BD0118FB0320A3032806300338AF99A7E703409F02B3E3C9CF","gs_sig":"144394ca43dc6b4ae545"},"is_seller":false,"min_offer_price":54600,"max_offer_discount":250,"is_watchlisted":false,"watchers":216,"auction_details":{"reserve_price":3,"top_bid":{"id":"965737820666855527","created_at":"2026-04-18T22:17:18.988697Z","price":56000,"contract_id":"965462412838963416","state":"active","obfuscated_buyer_id":"3415376811004057132"},"expires_at":"2026-04-25T04:02:56.641158Z","min_next_bid":57000}},{"id":"965708872276903554","created_at":"2026-04-18T10:01:25.70712Z","type":"buy_now","price":1082254,"state":"listed","seller":{"avatar":"https://avatars.steamstatic.com/978931ff2d774c665a91b9fa83c8a6a8666dca91_full.jpg","away":false,"flags":48,"online":false,"stall_public":true,"statistics":{"median_trade_time":0,"total_avoided_trades":0,"total_failed_trades":0,"total_trades":0,"total_verified_trades":0},"steam_id":"76561198868865913","username":"Nina Vanilla"},"reference":{"base_price":1233190,"predicted_price":1233190,"quantity":9,"last_updated":"2026-04-19T14:22:40.94772Z"},"item":{"asset_id":"50939836794","def_index":5030,"paint_index":1410,"paint_seed":429,"float_value":0.0633581206202507,"icon_url":"i0CoZ81Ui0m-9KwlBY1L_18myuGuq1wfhWSaZgMttyVfPaERSR0Wqmu7LAocGIGz3UqlXOLrxM-vMGmW8VNxu5Tk5UvzWCL2kpn2-DFk6P6hfqFSM-CcHHOv1et1uN5uXSi3nBgppwKHiIb-KT_4Ml93UtZuTOcLtUW8lNDvZL634FfYi4pCyiX5iXka6Htr4uhQVqt3_vfRiAzDZap9v8fuC2Vr0A","is_stattrak":false,"is_souvenir":false,"rarity":6,"quality":3,"market_hash_name":"★ Sport Gloves | Ultra Violent (Factory New)","low_rank":1,"high_rank":584,"tradable":0,"cs2_screenshot_id":"6698810959043905561","cs2_screenshot_at":"2026-04-18T09:49:44.507296Z","is_commodity":false,"type":"skin","rarity_name":"Covert","type_name":"Skin","item_name":"★ Sport Gloves | Ultra Violent","wear_name":"Factory New","collection":"The Dead Hand Collection","badges":["gold_lowest_float"],"serialized_inspect":"steam://rungame/730/76561202255233023/+csgo_econ_action_preview%200010FAF280E2BD0118A62720820B2806300338E78387EC0340AD03C2DD586D","gs_sig":"60a3b7c1158e7f5c0f90"},"is_seller":false,"min_offer_price":1028142,"max_offer_discount":500,"is_watchlisted":false,"watchers":15},{"id":"964522255851851101","created_at":"2026-04-15T13:47:05.752545Z","type":"auction","price":94999,"state":"listed","seller":{"avatar":"https://avatars.steamstatic.com/c3279edcb7f36377a6d60e107b64a486f4025790_full.jpg","away":false,"flags":48,"online":false,"stall_public":true,"statistics":{"median_trade_time":234,"total_avoided_trades":0,"total_failed_trades":0,"total_trades":398,"total_verified_trades":398},"steam_id":"76561198103528338","username":"sageybeara"},"reference":{"base_price":250000,"float_factor":0.965216,"predicted_price":241304,"quantity":1,"last_updated":"2026-04-19T13:50:06.568501Z"},"item":{"asset_id":"48167803677","def_index":8,"paint_index":33,"paint_seed":444,"float_value":0.07909934967756271,"icon_url":"i0CoZ81Ui0m-9KwlBY1L_18myuGuq1wfhWSaZgMttyVfPaERSR0Wqmu7LAocGIGz3UqlXOLrxM-vMGmW8VNxu5Dx60noTyLwi5Hf_Cxk_feqV6hkJ_iHQDCVkuxz5bY_H3znlhtz5jzTztigeXLBbwRyD8ckTOZbt0G8wNOyZuL8p1uJa1KD__k","d_param":"5497888313059334212","is_stattrak":false,"is_souvenir":false,"rarity":3,"quality":4,"market_hash_name":"AUG | Hot Rod (Minimal Wear)","high_rank":14,"tradable":0,"inspect_link":"steam://rungame/730/76561202255233023/+csgo_econ_action_preview%20S76561198103528338A48167803677D5497888313059334212","cs2_screenshot_id":"6357823146782937862","cs2_screenshot_at":"2025-12-10T09:42:50.042714Z","is_commodity":false,"type":"skin","rarity_name":"Mil-Spec Grade","type_name":"Skin","item_name":"AUG | Hot Rod","wear_name":"Minimal Wear","description":"It has been painted with a chrome base coat and candied in transparent red anodized effect paint.\\n\\n\u003ci\u003eAutomatic. Systematic. Hydromatic.\u003c/i\u003e","collection":"The Assault Collection","serialized_inspect":"steam://rungame/730/76561202255233023/+csgo_econ_action_preview%2000109DB699B8B301180820212803300438D7FD87ED0340BC0361C39191","gs_sig":"3bc0753915e6a93d43e3"},"is_seller":false,"min_offer_price":93100,"max_offer_discount":200,"is_watchlisted":false,"watchers":0,"auction_details":{"reserve_price":94999,"expires_at":"2026-04-29T13:47:05.751446Z","min_next_bid":94999}},{"id":"963786927717353282","created_at":"2026-04-13T13:05:09.863317Z","type":"auction","price":71000,"state":"listed","seller":{"avatar":"https://avatars.steamstatic.com/2f3bc08f161fe4b0ef02ef8f35aa919d86bd2290_full.jpg","away":false,"flags":48,"online":false,"stall_public":true,"statistics":{"median_trade_time":97,"total_avoided_trades":1,"total_failed_trades":1,"total_trades":19,"total_verified_trades":18},"steam_id":"76561198385018515","username":"Parzival"},"reference":{"base_price":210370,"float_factor":1.02819,"predicted_price":216300,"quantity":2,"last_updated":"2026-04-19T13:09:38.059294Z"},"item":{"asset_id":"48285302132","def_index":500,"paint_index":568,"paint_seed":512,"float_value":0.01998562179505825,"icon_url":"i0CoZ81Ui0m-9KwlBY1L_18myuGuq1wfhWSaZgMttyVfPaERSR0Wqmu7LAocGIGz3UqlXOLrxM-vMGmW8VNxu5Dx60noTyLzn4_v8ydP0POjV6FgJeKSAmOvzO9ksu1sRjO2kSIrujqNjsGsJCnFaVUpDpt4EeQLtxjrl9PhMujjtAXf3YNFxSuoii1K7ihi5LwGT-N7rXo8KYhp","d_param":"10090392900949110636","is_stattrak":true,"is_souvenir":false,"rarity":6,"quality":3,"market_hash_name":"★ StatTrak™ Bayonet | Gamma Doppler (Factory New)","low_rank":42,"high_rank":48,"tradable":0,"inspect_link":"steam://rungame/730/76561202255233023/+csgo_econ_action_preview%20S76561198385018515A48285302132D10090392900949110636","cs2_screenshot_id":"4195038580951732684","cs2_screenshot_at":"2025-12-16T09:25:35.104104Z","is_commodity":false,"type":"skin","rarity_name":"Covert","type_name":"Skin","item_name":"★ Bayonet | Gamma Doppler","wear_name":"Factory New","phase":"Emerald","description":"It has been painted with black and silver metallic paints using a marbleizing medium, then candy coated.","serialized_inspect":"steam://rungame/730/76561202255233023/+csgo_econ_action_preview%200010F4FA9CF0B30118F40320B8042806300338E3F18EE503408004480050B90AEBEDB19E","gs_sig":"e02b4aa2d0292a358ebc"},"is_seller":false,"min_offer_price":65320,"max_offer_discount":800,"is_watchlisted":false,"watchers":60,"auction_details":{"reserve_price":70000,"top_bid":{"id":"965049747649988454","created_at":"2026-04-17T00:43:09.597284Z","price":71000,"contract_id":"963786927717353282","state":"active","obfuscated_buyer_id":"832816080242942741"},"expires_at":"2026-04-20T13:05:09.862213Z","min_next_bid":72000}},{"id":"965911140926359035","created_at":"2026-04-19T09:46:01.758836Z","type":"auction","price":150000,"state":"listed","seller":{"away":false,"flags":48,"obfuscated_id":"10753341275265725988","online":false,"stall_public":false,"statistics":{"median_trade_time":958,"total_avoided_trades":0,"total_failed_trades":0,"total_trades":84,"total_verified_trades":84}},"reference":{"base_price":296510,"float_factor":0.946133,"predicted_price":280538,"quantity":54,"last_updated":"2026-04-19T15:45:54.127533Z"},"item":{"asset_id":"49191763126","def_index":5030,"paint_index":10045,"paint_seed":973,"float_value":0.0680403932929039,"icon_url":"i0CoZ81Ui0m-9KwlBY1L_18myuGuq1wfhWSaZgMttyVfPaERSR0Wqmu7LAocGIGz3UqlXOLrxM-vMGmW8VNxu5Tk5UvzWCL2kpn2-DFk_OKherB0H-CcB3Sfz9Fwou5ucCu_gBgYpDWMjorGLSLANkI-W5R4E7JZtxbskNWxZeLi4QPejdgTmSn62iwbvyw957kDAqog_fXWjBaBb-Pahe96zA","is_stattrak":false,"is_souvenir":false,"rarity":6,"quality":3,"market_hash_name":"★ Sport Gloves | Amphibious (Factory New)","tradable":0,"inspect_link":"steam://rungame/730/76561202255233023/+csgo_econ_action_preview%200010B6F9BAA0B70118A62720BD4E2806300338C3B1ADEC0340CD078FCD1C32","cs2_screenshot_id":"984287745719330724","cs2_screenshot_at":"2026-04-06T05:31:27.8331Z","is_commodity":false,"type":"skin","rarity_name":"Covert","type_name":"Skin","item_name":"★ Sport Gloves | Amphibious","wear_name":"Factory New","description":"These synthetic blue and white gloves are quick drying and breathable.","serialized_inspect":"steam://rungame/730/76561202255233023/+csgo_econ_action_preview%200010B6F9BAA0B70118A62720BD4E2806300338C3B1ADEC0340CD078FCD1C32","gs_sig":"693b3bacae3540c2673e"},"is_seller":false,"min_offer_price":138000,"max_offer_discount":800,"is_watchlisted":false,"watchers":16,"auction_details":{"reserve_price":150000,"top_bid":{"id":"965993881873286702","created_at":"2026-04-19T15:14:48.737822Z","price":150000,"contract_id":"965911140926359035","state":"active","obfuscated_buyer_id":"1830900595314735380"},"expires_at":"2026-04-26T09:46:01.757889Z","min_next_bid":152500}},{"id":"965852631471883914","created_at":"2026-04-19T05:53:32.017959Z","type":"auction","price":15494,"state":"listed","seller":{"away":false,"flags":48,"obfuscated_id":"9601504859486934255","online":false,"stall_public":false,"statistics":{"median_trade_time":81,"total_avoided_trades":0,"total_failed_trades":0,"total_trades":95,"total_verified_trades":95}},"reference":{"base_price":136964,"float_factor":1.03153,"predicted_price":141282,"quantity":314,"last_updated":"2026-04-19T17:53:29.536417Z"},"item":{"asset_id":"50881986912","def_index":508,"paint_index":419,"paint_seed":352,"float_value":0.013894040137529373,"icon_url":"i0CoZ81Ui0m-9KwlBY1L_18myuGuq1wfhWSaZgMttyVfPaERSR0Wqmu7LAocGIGz3UqlXOLrxM-vMGmW8VNxu5Dx60noTyL6kJ_m-B1Wts2sab1iLvWHMWad_up5oPFlSjuMhRUmoDjXpYPwJiPTcFR0D8Z3F-Nb4xS6x4DjNe2x5A3eiNpMzyr6jCpPvHk95O0GAKpz-fbJz1aWGfxjapk","is_stattrak":false,"is_souvenir":false,"rarity":6,"quality":3,"market_hash_name":"★ M9 Bayonet | Doppler (Factory New)","tradable":0,"inspect_link":"steam://rungame/730/76561202255233023/+csgo_econ_action_preview%200010E082B6C6BD0118FC0320A3032806300338D4C78EE30340E002EF51A9A3","cs2_screenshot_id":"1536859237404167126","cs2_screenshot_at":"2026-04-19T05:53:45.554662Z","is_commodity":false,"type":"skin","rarity_name":"Covert","type_name":"Skin","item_name":"★ M9 Bayonet | Doppler","wear_name":"Factory New","phase":"Phase 2","description":"It has been painted with black and silver metallic paints using a marbleizing medium, then candy coated.\\n\\n\u003ci\u003eGetting lost in its color can prove fatal\u003c/i\u003e","serialized_inspect":"steam://rungame/730/76561202255233023/+csgo_econ_action_preview%200010E082B6C6BD0118FC0320A3032806300338D4C78EE30340E002EF51A9A3","gs_sig":"1ff0377dddec4ef33e96"},"is_seller":false,"min_offer_price":15107,"max_offer_discount":250,"is_watchlisted":false,"watchers":121,"auction_details":{"reserve_price":3,"top_bid":{"id":"966026892706713214","created_at":"2026-04-19T17:25:59.133905Z","price":15494,"contract_id":"965852631471883914","state":"active","obfuscated_buyer_id":"17980641539138566981"},"expires_at":"2026-04-26T05:53:32.014854Z","min_next_bid":15744}},{"id":"965870874710376863","created_at":"2026-04-19T07:06:01.544554Z","type":"buy_now","price":250000,"description":"#2 lowest float","state":"listed","seller":{"away":false,"flags":48,"obfuscated_id":"7863700861020087061","online":true,"stall_public":false,"statistics":{"median_trade_time":48,"total_avoided_trades":0,"total_failed_trades":2,"total_trades":357,"total_verified_trades":355}},"reference":{"base_price":374481,"predicted_price":374481,"quantity":3,"last_updated":"2026-04-19T13:05:01.15538Z"},"item":{"asset_id":"50998250787","def_index":5031,"paint_index":1401,"paint_seed":68,"float_value":0.06231057643890381,"icon_url":"i0CoZ81Ui0m-9KwlBY1L_18myuGuq1wfhWSaZgMttyVfPaERSR0Wqmu7LAocGIGz3UqlXOLrxM-vMGmW8VNxu5T441rsfhr9kYDl7h1c4_24bZtpMvmFC3Wvxfx3t-5ncDqwlBEijC-AnrD1KCzPKhgkCZdwTeIL4ES5wdXjPrm251Pdi98QzST3jy0d6nxp4e5QAKsk_q3RkUifZohUdPsK","is_stattrak":false,"is_souvenir":false,"rarity":6,"quality":3,"market_hash_name":"★ Driver Gloves | Dragon Fists (Factory New)","low_rank":2,"high_rank":334,"tradable":0,"inspect_link":"steam://rungame/730/76561202255233023/+csgo_econ_action_preview%200010A39AEEFDBD0118A72720F90A2806300338E0F2FCEB034044902254B8","cs2_screenshot_id":"207931843651550011","cs2_screenshot_at":"2026-04-19T07:08:38.319776Z","is_commodity":false,"type":"skin","rarity_name":"Covert","type_name":"Skin","item_name":"★ Driver Gloves | Dragon Fists","wear_name":"Factory New","collection":"The Dead Hand Collection","badges":["silver_lowest_float"],"serialized_inspect":"steam://rungame/730/76561202255233023/+csgo_econ_action_preview%200010A39AEEFDBD0118A72720F90A2806300338E0F2FCEB034044902254B8","gs_sig":"c4e1597b2cdb5d6fee7f"},"is_seller":false,"min_offer_price":230000,"max_offer_discount":800,"is_watchlisted":false,"watchers":0},{"id":"965920965655660905","created_at":"2026-04-19T10:25:04.156521Z","type":"auction","price":30000,"state":"listed","seller":{"away":false,"flags":48,"obfuscated_id":"14649906676470393670","online":false,"stall_public":false,"statistics":{"median_trade_time":874,"total_avoided_trades":0,"total_failed_trades":0,"total_trades":33,"total_verified_trades":33}},"reference":{"base_price":111531,"float_factor":1.28005,"predicted_price":142765,"quantity":955,"last_updated":"2026-04-19T16:24:32.768177Z"},"item":{"asset_id":"48986113587","def_index":507,"paint_index":413,"paint_seed":614,"float_value":0.030756544321775436,"icon_url":"i0CoZ81Ui0m-9KwlBY1L_18myuGuq1wfhWSaZgMttyVfPaERSR0Wqmu7LAocGIGz3UqlXOLrxM-vMGmW8VNxu5Dx60noTyL6kJ_m-B1Q7uCvZaZkNM-SA1idwPx0vORWSSi3kCIrujqNjsGveH2RaVRxX5ohEe4Juhawm4fiM-ji4APf2YMXmSz_hyoduytv4uhWT-N7rfLHGBJ4","d_param":"12289802220415947893","is_stattrak":false,"is_souvenir":false,"rarity":6,"quality":3,"market_hash_name":"★ Karambit | Marble Fade (Factory New)","tradable":0,"inspect_link":"steam://rungame/730/76561202255233023/+csgo_econ_action_preview%200010B38CB3BEB60118FB03209D032806300338A6EAEFE70340E604BA408463","cs2_screenshot_id":"1659923146574864014","cs2_screenshot_at":"2026-02-23T12:25:41.921029Z","is_commodity":false,"type":"skin","rarity_name":"Covert","type_name":"Skin","item_name":"★ Karambit | Marble Fade","wear_name":"Factory New","description":"It has been painted with black and silver metallic paints using a marbleizing medium, then candy coated in three colors.\\n\\n\u003ci\u003eThe blade is made of many colors, but soon it all looks red\u003c/i\u003e","serialized_inspect":"steam://rungame/730/76561202255233023/+csgo_econ_action_preview%200010B38CB3BEB60118FB03209D032806300338A6EAEFE70340E604BA408463","gs_sig":"5e4332ed3e30e4562741"},"is_seller":false,"min_offer_price":27600,"max_offer_discount":800,"is_watchlisted":false,"watchers":39,"auction_details":{"reserve_price":1000,"top_bid":{"id":"966002726607653351","created_at":"2026-04-19T15:49:57.486473Z","price":30000,"contract_id":"965920965655660905","state":"active","obfuscated_buyer_id":"346908614555456269"},"expires_at":"2026-04-26T10:25:04.155441Z","min_next_bid":30500}},{"id":"965896373956382592","created_at":"2026-04-19T08:47:21.038088Z","type":"auction","price":17079,"state":"listed","seller":{"away":false,"flags":48,"obfuscated_id":"18037921134658856894","online":false,"stall_public":false,"statistics":{"median_trade_time":70,"total_avoided_trades":0,"total_failed_trades":0,"total_trades":33,"total_verified_trades":33}},"reference":{"base_price":111775,"float_factor":1.14114,"predicted_price":127551,"quantity":326,"last_updated":"2026-04-19T14:47:00.151099Z"},"item":{"asset_id":"50855090837","def_index":508,"paint_index":421,"paint_seed":525,"float_value":0.0006726901629008353,"icon_url":"i0CoZ81Ui0m-9KwlBY1L_18myuGuq1wfhWSaZgMttyVfPaERSR0Wqmu7LAocGIGz3UqlXOLrxM-vMGmW8VNxu5Dx60noTyL6kJ_m-B1Wts2sab1iLvWHMWad_up5oPFlSjuMhRUmoDjRpYPwJiPTcAAnC8R2FLQD4BG6w4LuZunhswLXjIpGzS7333xPv3ls5e9RUPYkrPbJz1aWcLZcvps","is_stattrak":false,"is_souvenir":false,"rarity":6,"quality":3,"market_hash_name":"★ M9 Bayonet | Doppler (Factory New)","tradable":0,"inspect_link":"steam://rungame/730/76561202255233023/+csgo_econ_action_preview%20001095B5CCB9BD0118FC0320A5032806300338F9AEC1D103408D0462D2C5EE","cs2_screenshot_id":"4309895834619057748","cs2_screenshot_at":"2026-04-12T17:11:29.430281Z","is_commodity":false,"type":"skin","rarity_name":"Covert","type_name":"Skin","item_name":"★ M9 Bayonet | Doppler","wear_name":"Factory New","phase":"Phase 4","description":"It has been painted with black and silver metallic paints using a marbleizing medium, then candy coated.\\n\\n\u003ci\u003eGetting lost in its color can prove fatal\u003c/i\u003e","serialized_inspect":"steam://rungame/730/76561202255233023/+csgo_econ_action_preview%20001095B5CCB9BD0118FC0320A5032806300338F9AEC1D103408D0462D2C5EE","gs_sig":"afb19a86fc56718fc3ac"},"is_seller":false,"min_offer_price":15713,"max_offer_discount":800,"is_watchlisted":false,"watchers":85,"auction_details":{"reserve_price":1000,"top_bid":{"id":"966013112794875644","created_at":"2026-04-19T16:31:13.746642Z","price":17079,"contract_id":"965896373956382592","state":"active","obfuscated_buyer_id":"10169789585804508922"},"expires_at":"2026-04-26T08:47:21.037106Z","min_next_bid":17329}},{"id":"965121225040987282","created_at":"2026-04-17T05:27:11.135138Z","type":"auction","price":41550,"description":"Money for my fresh born child \u003c3","state":"listed","seller":{"avatar":"https://avatars.steamstatic.com/a810764542afbbea6944d791c246962835b8abd4_full.jpg","away":false,"flags":48,"online":false,"stall_public":true,"statistics":{"median_trade_time":188,"total_avoided_trades":0,"total_failed_trades":0,"total_trades":7,"total_verified_trades":7},"steam_id":"76561198983431790","username":"パスカル"},"reference":{"base_price":146498,"float_factor":1.027,"predicted_price":150453,"quantity":905,"last_updated":"2026-04-19T17:25:41.753969Z"},"item":{"asset_id":"48925627908","def_index":515,"paint_index":413,"paint_seed":14,"float_value":0.0577206015586853,"icon_url":"i0CoZ81Ui0m-9KwlBY1L_18myuGuq1wfhWSaZgMttyVfPaERSR0Wqmu7LAocGIGz3UqlXOLrxM-vMGmW8VNxu5Dx60noTyL6kJ_m-B1Z-ua6bbZrLOmsD2qvzO9ksu1scC-ykRgYvzSCkpu3JCrBPVMkCZIiFLUC40S-l9DkZerg4Qfc3Y9DzCuo3SlK6ydv5e9UA71lpPNwsjHPzA","d_param":"16863208565673074833","is_stattrak":false,"is_souvenir":false,"rarity":6,"quality":3,"market_hash_name":"★ Butterfly Knife | Marble Fade (Factory New)","tradable":0,"inspect_link":"steam://rungame/730/76561202255233023/+csgo_econ_action_preview%20S76561198983431790A48925627908D16863208565673074833","cs2_screenshot_id":"8451625337750444479","cs2_screenshot_at":"2026-03-08T05:16:34.158877Z","is_commodity":false,"type":"skin","rarity_name":"Covert","type_name":"Skin","item_name":"★ Butterfly Knife | Marble Fade","wear_name":"Factory New","description":"It has been painted with black and silver metallic paints using a marbleizing medium, then candy coated in three colors.\\n\\n\u003ci\u003eThe blade is made of many colors, but soon it all looks red\u003c/i\u003e","serialized_inspect":"steam://rungame/730/76561202255233023/+csgo_econ_action_preview%20001084ACC7A1B601188304209D032806300338F0D8B1EB03400EC6412BB8","gs_sig":"7dbed526af1506e54ad9"},"is_seller":false,"min_offer_price":38226,"max_offer_discount":800,"is_watchlisted":false,"watchers":234,"auction_details":{"reserve_price":1575,"top_bid":{"id":"965910825556642468","created_at":"2026-04-19T09:44:46.568326Z","price":41550,"contract_id":"965121225040987282","state":"active","obfuscated_buyer_id":"9847439498595906450"},"expires_at":"2026-04-24T05:27:11.134185Z","min_next_bid":42050}},{"id":"963787264587075171","created_at":"2026-04-13T13:06:30.179618Z","type":"auction","price":75000,"state":"listed","seller":{"avatar":"https://avatars.steamstatic.com/2f3bc08f161fe4b0ef02ef8f35aa919d86bd2290_full.jpg","away":false,"flags":48,"online":false,"stall_public":true,"statistics":{"median_trade_time":97,"total_avoided_trades":1,"total_failed_trades":1,"total_trades":19,"total_verified_trades":18},"steam_id":"76561198385018515","username":"Parzival"},"reference":{"base_price":152720,"float_factor":1.20043,"predicted_price":183330,"quantity":140,"last_updated":"2026-04-19T13:11:26.597476Z"},"item":{"asset_id":"48692262937","def_index":9,"paint_index":163,"paint_seed":13,"float_value":0.007316755596548319,"icon_url":"i0CoZ81Ui0m-9KwlBY1L_18myuGuq1wfhWSaZgMttyVfPaERSR0Wqmu7LAocGIGz3UqlXOLrxM-vMGmW8VNxu5Dx60noTyLwiYbf-jFk5vyqbbRoLvSWMWaH0dF6ueZhW2e1zElxtmzQmIv8J3qQalRzW5t0RrYOsBCwlte2Mbmw5AbXiYlAnnn4kGoXuYBQOb0Q","d_param":"166332110658484745","is_stattrak":false,"is_souvenir":false,"rarity":6,"quality":4,"market_hash_name":"AWP | CMYK (Factory New)","low_rank":74,"tradable":0,"inspect_link":"steam://rungame/730/76561202255233023/+csgo_econ_action_preview%20S76561198385018515A48692262937D166332110658484745","cs2_screenshot_id":"2010556806506006473","cs2_screenshot_at":"2026-01-06T08:23:44.480924Z","is_commodity":false,"type":"skin","rarity_name":"Covert","type_name":"Skin","item_name":"AWP | CMYK","wear_name":"Factory New","description":"It has been custom painted with a multicolored abstract design over a white base.\\n\\n\u003ci\u003eI knew you'd return; I just didn't expect it to be so soon... – Booth, Arms Dealer\u003c/i\u003e","collection":"The Graphic Design Collection","serialized_inspect":"steam://rungame/730/76561202255233023/+csgo_econ_action_preview%20001099F0A3B2B501180920A3012806300438E582BFDF03400D663B20DB","gs_sig":"a9be7873a2cb9829bbde"},"is_seller":false,"min_offer_price":69000,"max_offer_discount":800,"is_watchlisted":false,"watchers":69,"auction_details":{"reserve_price":75000,"top_bid":{"id":"963816516007102775","created_at":"2026-04-13T15:02:44.261762Z","price":75000,"contract_id":"963787264587075171","state":"active","obfuscated_buyer_id":"4616041202084841324"},"expires_at":"2026-04-20T13:06:30.17828Z","min_next_bid":76000}},{"id":"965501313838353876","created_at":"2026-04-18T06:37:31.366831Z","type":"auction","price":89000,"description":"tier 4 red low float BS","state":"listed","seller":{"avatar":"https://avatars.steamstatic.com/a355b9de04524279d9e0240c516585f66bb2ab60_full.jpg","away":false,"flags":48,"online":false,"stall_public":true,"statistics":{"median_trade_time":81,"total_avoided_trades":0,"total_failed_trades":0,"total_trades":21,"total_verified_trades":21},"steam_id":"76561198287490933","username":"howardshortman1953@virgilio.it"},"reference":{"base_price":136896,"float_factor":1.25559,"predicted_price":171885,"quantity":172,"last_updated":"2026-04-19T12:39:40.370105Z"},"item":{"asset_id":"49503301731","def_index":5034,"paint_index":10033,"paint_seed":742,"float_value":0.46194544434547424,"icon_url":"i0CoZ81Ui0m-9KwlBY1L_18myuGuq1wfhWSaZgMttyVfPaERSR0Wqmu7LAocGIGz3UqlXOLrxM-vMGmW8VNxu5Tk71ruQBH4jYLf-i5U-fe9V7d9JfOaD2uZ0vpJu-hkQCe8qhkusjCKlIvqHjnCOml4X8M2DPlf5Ea-wNOzYe3q51fdioxByir3jihPuCdi5roKAqEs-vDV2wGUMuU4_9Bdc5NnmXOG","d_param":"5063040617120715868","is_stattrak":false,"is_souvenir":false,"rarity":6,"quality":3,"market_hash_name":"★ Specialist Gloves | Crimson Kimono (Battle-Scarred)","tradable":0,"inspect_link":"steam://rungame/730/76561202255233023/+csgo_econ_action_preview%20S76561198287490933A49503301731D5063040617120715868","cs2_screenshot_id":"4820046463648244654","cs2_screenshot_at":"2026-02-16T03:00:19.47097Z","is_commodity":false,"type":"skin","rarity_name":"Covert","type_name":"Skin","item_name":"★ Specialist Gloves | Crimson Kimono","wear_name":"Battle-Scarred","description":"This pair of black gloves has been accented with a stark red diamond pattern.\\n\\n\u003ci\u003eStart seeing red\u003c/i\u003e","serialized_inspect":"steam://rungame/730/76561202255233023/+csgo_econ_action_preview%200010E3E081B5B80118AA2720B14E28063003389D88B2F70340E60555B72F65","gs_sig":"69f12c93b0f565570eec"},"is_seller":false,"min_offer_price":81880,"max_offer_discount":800,"is_watchlisted":false,"watchers":158,"auction_details":{"reserve_price":1000,"top_bid":{"id":"965978774468431458","created_at":"2026-04-19T14:14:46.851599Z","price":89000,"contract_id":"965501313838353876","state":"active","obfuscated_buyer_id":"5446655292007500103"},"expires_at":"2026-04-21T06:37:31.365765Z","min_next_bid":90000}},{"id":"965138336006144298","created_at":"2026-04-17T06:35:10.707615Z","type":"auction","price":22300,"state":"listed","seller":{"avatar":"https://avatars.steamstatic.com/a405df8d3c8b0248f4877591ccb2776ef96d4f9c_full.jpg","away":false,"flags":48,"online":false,"stall_public":true,"statistics":{"median_trade_time":72,"total_avoided_trades":0,"total_failed_trades":2,"total_trades":289,"total_verified_trades":287},"steam_id":"76561197968177851","username":"lowkurkenuienlychungus67tuah"},"reference":{"base_price":107234,"float_factor":0.971647,"predicted_price":104194,"quantity":23,"last_updated":"2026-04-19T12:39:40.494768Z"},"item":{"asset_id":"50214407944","def_index":34,"paint_index":39,"paint_seed":933,"float_value":0.06583807617425919,"icon_url":"i0CoZ81Ui0m-9KwlBY1L_18myuGuq1wfhWSaZgMttyVfPaERSR0Wqmu7LAocGIGz3UqlXOLrxM-vMGmW8VNxu5Dx60noTyL8js_f7i1k9veiZKt6H_yaCW-Ej-tztbQ5Hy2wxklw5TiDnt_4eC_GOFR1XJdzQ-AMskXswNbvNuvq4wPAy9USwXKj73o","is_stattrak":false,"is_souvenir":false,"rarity":4,"quality":4,"market_hash_name":"MP9 | Bulldozer (Factory New)","tradable":0,"cs2_screenshot_id":"2161759433650030372","cs2_screenshot_at":"2026-03-22T20:45:04.663506Z","is_commodity":false,"type":"skin","rarity_name":"Restricted","type_name":"Skin","item_name":"MP9 | Bulldozer","wear_name":"Factory New","description":"It has individual parts spray-painted solid colors in a production line yellow color scheme.\\n\\n\u003ci\u003eThis bone crusher is a devastator\u003c/i\u003e","collection":"The Assault Collection","serialized_inspect":"steam://rungame/730/76561202255233023/+csgo_econ_action_preview%200010889E8C88BB011822202728043004389DAC9BEC0340A5072F909B5C","gs_sig":"8ed3f141d2de2b16dcc7"},"is_seller":false,"min_offer_price":21743,"max_offer_discount":250,"is_watchlisted":false,"watchers":125,"auction_details":{"reserve_price":3,"top_bid":{"id":"966036859278985756","created_at":"2026-04-19T18:05:35.349175Z","price":22300,"contract_id":"965138336006144298","state":"active","obfuscated_buyer_id":"11547509428280073767"},"expires_at":"2026-04-20T06:35:10.706631Z","min_next_bid":22550}},{"id":"965511438636548938","created_at":"2026-04-18T07:17:45.306814Z","type":"auction","price":39362,"state":"listed","seller":{"avatar":"https://avatars.steamstatic.com/1dcb05e25ff58c3dba5d0bed5ccdeca9b735a973_full.jpg","away":false,"flags":48,"online":false,"stall_public":true,"statistics":{"median_trade_time":73,"total_avoided_trades":0,"total_failed_trades":2,"total_trades":267,"total_verified_trades":265},"steam_id":"76561199073723073","username":"Amantes sunt amentes"},"reference":{"base_price":117991,"float_factor":0.996169,"predicted_price":117539,"quantity":209,"last_updated":"2026-04-19T13:18:10.470595Z"},"item":{"asset_id":"50996434003","def_index":515,"paint_index":12,"paint_seed":301,"float_value":0.1453544944524765,"icon_url":"i0CoZ81Ui0m-9KwlBY1L_18myuGuq1wfhWSaZgMttyVfPaERSR0Wqmu7LAocGIGz3UqlXOLrxM-vMGmW8VNxu5Dx60noTyL6kJ_m-B1Z-ua6bbZrLOmsBn6v1ut0o95lRi67gVN04WmDzNz_cX_CalAiW8FxR7MI4xKxmtPlYe7ksgzeiN5BziT83y4f8G81tOxPsLb-","is_stattrak":false,"is_souvenir":false,"rarity":6,"quality":3,"market_hash_name":"★ Butterfly Knife | Crimson Web (Minimal Wear)","tradable":0,"cs2_screenshot_id":"4469790590493668823","cs2_screenshot_at":"2026-04-18T09:52:02.063687Z","is_commodity":false,"type":"skin","rarity_name":"Covert","type_name":"Skin","item_name":"★ Butterfly Knife | Crimson Web","wear_name":"Minimal Wear","description":"It has been painted using a spider web-patterned hydrographic over a red base coat and finished with a semi-gloss topcoat.\\n\\n\u003ci\u003eBe careful where you walk, you never know where the web is spread\u003c/i\u003e","collection":"The Breakout Collection","serialized_inspect":"steam://rungame/730/76561202255233023/+csgo_econ_action_preview%200010D3A8FFFCBD01188304200C2806300338CFAFD3F00340AD02FAD9B0E8","gs_sig":"0e955bd1e73e795b9be7"},"is_seller":false,"min_offer_price":36214,"max_offer_discount":800,"is_watchlisted":false,"watchers":222,"auction_details":{"reserve_price":100,"top_bid":{"id":"965943571050005899","created_at":"2026-04-19T11:54:53.70239Z","price":39362,"contract_id":"965511438636548938","state":"active","obfuscated_buyer_id":"2294898175285793744"},"expires_at":"2026-04-21T07:17:45.305597Z","min_next_bid":39862}},{"id":"965952843280420107","created_at":"2026-04-19T12:31:44.374314Z","type":"auction","price":11669,"state":"listed","seller":{"away":false,"flags":48,"obfuscated_id":"7016975988695471452","online":false,"stall_public":false,"statistics":{"median_trade_time":280,"total_avoided_trades":0,"total_failed_trades":0,"total_trades":24,"total_verified_trades":24}},"reference":{"base_price":62767,"float_factor":1.4164358,"predicted_price":88905,"quantity":1638,"last_updated":"2026-04-19T12:30:32.308771Z"},"item":{"asset_id":"49989725851","def_index":5030,"paint_index":10076,"paint_seed":268,"float_value":0.1693044751882553,"icon_url":"i0CoZ81Ui0m-9KwlBY1L_18myuGuq1wfhWSaZgMttyVfPaERSR0Wqmu7LAocGIGz3UqlXOLrxM-vMGmW8VNxu5Tk5UvzWCL2kpn2-DFk_OKherB0H_qSCXKR09F7teVgWiT9k08l5WrVnNeuI3qRaAEmCZJ0FuRYsRDsm9LnMryw71HfiooUmSn9hzQJsHg51Ex1iQ","is_stattrak":false,"is_souvenir":false,"rarity":6,"quality":3,"market_hash_name":"★ Sport Gloves | Nocts (Field-Tested)","tradable":0,"inspect_link":"steam://rungame/730/76561202255233023/+csgo_econ_action_preview%2000109BDDFA9CBA0118A62720DC4E2806300338A7BCB5F103408C0299CAB160","cs2_screenshot_id":"5261808946370301813","cs2_screenshot_at":"2026-04-14T09:38:29.384992Z","is_commodity":false,"type":"skin","rarity_name":"Covert","type_name":"Skin","item_name":"★ Sport Gloves | Nocts","wear_name":"Field-Tested","serialized_inspect":"steam://rungame/730/76561202255233023/+csgo_econ_action_preview%2000109BDDFA9CBA0118A62720DC4E2806300338A7BCB5F103408C0299CAB160","gs_sig":"2e3c0dcb3336ef7e6f57"},"is_seller":false,"min_offer_price":10736,"max_offer_discount":800,"is_watchlisted":false,"watchers":43,"auction_details":{"reserve_price":71,"top_bid":{"id":"966034947909487844","created_at":"2026-04-19T17:57:59.643619Z","price":11669,"contract_id":"965952843280420107","state":"active","obfuscated_buyer_id":"5349492294637731042"},"expires_at":"2026-04-26T12:31:44.37315Z","min_next_bid":11919}},{"id":"963457496767400585","created_at":"2026-04-12T15:16:07.404165Z","type":"auction","price":98532,"description":"#9 + FBP","state":"listed","seller":{"away":false,"flags":48,"obfuscated_id":"3217506944058370380","online":false,"stall_public":false,"statistics":{"median_trade_time":30,"total_avoided_trades":1,"total_failed_trades":1,"total_trades":1236,"total_verified_trades":1235}},"reference":{"base_price":139118,"float_factor":1.22989,"predicted_price":171099,"quantity":331,"last_updated":"2026-04-19T15:21:27.933964Z"},"item":{"asset_id":"48295537754","def_index":507,"paint_index":418,"paint_seed":478,"float_value":0.0002486228768248111,"icon_url":"i0CoZ81Ui0m-9KwlBY1L_18myuGuq1wfhWSaZgMttyVfPaERSR0Wqmu7LAocGIGz3UqlXOLrxM-vMGmW8VNxu5Dx60noTyL6kJ_m-B1Q7uCvZaZkNM-SA1iUzv5mvOR7cDm7lA4i4gKJk4jxNWXFb1cpDJR2FOFbsBTql9bjYbzq7gPZiN1MxH7_2ytNuCdpte1UB_Ui5OSJ2GbkVqni","d_param":"16917466892719714357","is_stattrak":false,"is_souvenir":false,"rarity":6,"quality":3,"market_hash_name":"★ Karambit | Doppler (Factory New)","low_rank":9,"tradable":0,"inspect_link":"steam://rungame/730/76561202255233023/+csgo_econ_action_preview%200010DAD88DF5B30118FB0320A203280630033899B389CC0340DE0382F04CA5","cs2_screenshot_id":"4671860791752735381","cs2_screenshot_at":"2026-01-13T18:05:24.999246Z","is_commodity":false,"type":"skin","rarity_name":"Covert","type_name":"Skin","item_name":"★ Karambit | Doppler","wear_name":"Factory New","phase":"Phase 1","description":"It has been painted with black and silver metallic paints using a marbleizing medium, then candy coated.\\n\\n\u003ci\u003eGetting lost in its color can prove fatal\u003c/i\u003e","serialized_inspect":"steam://rungame/730/76561202255233023/+csgo_econ_action_preview%200010DAD88DF5B30118FB0320A203280630033899B389CC0340DE0382F04CA5","gs_sig":"aa62ba51d7e9868f4118"},"is_seller":false,"min_offer_price":90650,"max_offer_discount":800,"is_watchlisted":false,"watchers":364,"auction_details":{"reserve_price":100,"top_bid":{"id":"965562924368266644","created_at":"2026-04-18T10:42:20.461411Z","price":98532,"contract_id":"963457496767400585","state":"active","obfuscated_buyer_id":"13814816895319396199"},"expires_at":"2026-04-26T15:16:07.403118Z","min_next_bid":99532}},{"id":"902296043457219566","created_at":"2025-10-25T20:42:20.61096Z","type":"buy_now","price":3202381,"state":"listed","seller":{"away":false,"flags":48,"obfuscated_id":"14914544996039851507","online":false,"stall_public":false,"statistics":{"median_trade_time":17969,"total_avoided_trades":9,"total_failed_trades":0,"total_trades":213,"total_verified_trades":213}},"reference":{"base_price":3274587,"predicted_price":3274587,"quantity":7,"last_updated":"2026-04-19T17:29:39.3999Z"},"item":{"asset_id":"1532853751","def_index":4014,"icon_url":"i0CoZ81Ui0m-9KwlBY1L_18myuGuq1wfhWSaZgMttyVfPaERSR0Wqmu7LAocGJKz2lu_XsnXwtmkJjSU91dh8bjn_lDkShjjoYbh_ilk5PO6OvQ8dM_DXynCkLkv6LJrSSrilkRw4GzSw9-qIHmSPFNxWJR2TeIMt0HsltXgYrzq-UWA3Meo50Y4","rarity":1,"market_hash_name":"EMS Katowice 2014 Challengers","tradable":0,"is_commodity":true,"type":"container","rarity_name":"Base Grade","type_name":"Container","item_name":"EMS Katowice 2014 Challengers"},"is_seller":false,"is_watchlisted":false,"watchers":265},{"id":"964425445636440955","created_at":"2026-04-15T07:22:24.39878Z","type":"auction","price":20250,"state":"listed","seller":{"avatar":"https://avatars.steamstatic.com/b903ac5b4b595f059a2a4a41a2fab0760b959e4e_full.jpg","away":false,"flags":48,"online":false,"stall_public":true,"statistics":{"median_trade_time":34,"total_avoided_trades":0,"total_failed_trades":2,"total_trades":121,"total_verified_trades":119},"steam_id":"76561198220000039","username":"Ubiquitin"},"reference":{"base_price":92441,"float_factor":0.992121,"predicted_price":91713,"quantity":194,"last_updated":"2026-04-19T13:24:53.597798Z"},"item":{"asset_id":"48627754124","def_index":9,"paint_index":662,"paint_seed":340,"float_value":0.05035252124071121,"icon_url":"i0CoZ81Ui0m-9KwlBY1L_18myuGuq1wfhWSaZgMttyVfPaERSR0Wqmu7LAocGIGz3UqlXOLrxM-vMGmW8VNxu5Dx60noTyLwiYbf_jdk7uW-V6xsLv6KD1icyOl-pK9vGCqwkx524G_WnNmsInyXOAVyXJJ0TbNb5EOxxIflYbzj4gDdiNlC02yg2XaKgrAq","is_stattrak":false,"is_souvenir":false,"rarity":6,"quality":4,"market_hash_name":"AWP | Oni Taiji (Factory New)","stickers":[{"stickerId":7339,"slot":2,"wear":0.5537907,"offset_x":-0.07144129,"offset_y":-0.06964964,"rotation":90,"icon_url":"https://community.akamai.steamstatic.com/economy/image/i0CoZ81Ui0m-9KwlBY1L_18myuGuq1wfhWSaZgMttyVfPaERSR0Wqmu7LAocGJai0ki7VeTHjMmxPSnHtwI6_4j91V7rSAnlm4Su-ScKvKr-MPU-cPPHCzKTlrcjsbZsSnDkwE5_t2iEztv6InmUaFIhW4wwG7CZyGA3GA","name":"Sticker | KOI (Glitter) | Copenhagen 2024","reference":{"price":87,"quantity":459,"updated_at":"2026-04-18T03:50:59.012254Z"}},{"stickerId":8576,"slot":0,"wear":0.6,"offset_x":-0.35419807,"offset_y":-0.016873747,"rotation":9,"icon_url":"https://community.akamai.steamstatic.com/economy/image/i0CoZ81Ui0m-9KwlBY1L_18myuGuq1wfhWSaZgMttyVfPaERSR0Wqmu7LAocGJai0ki7VeTHjMu0JinHtwM6-obi42bvThH-0JPkpXoJ6_OsPPU-eabCXz_Aw-sk5rZtG3vhwx9w5GvSydysc3iVbwI-Sswn4vZ9DSg","name":"Sticker | Natus Vincere (Holo) | Austin 2025","reference":{"price":281,"quantity":615,"updated_at":"2026-04-18T00:49:30.223657Z"}}],"tradable":0,"cs2_screenshot_id":"7108354874390217909","cs2_screenshot_at":"2026-04-03T23:02:22.650982Z","is_commodity":false,"type":"skin","rarity_name":"Covert","type_name":"Skin","item_name":"AWP | Oni Taiji","wear_name":"Factory New","description":"It has been hand painted with colorful samurai and Oni imagery.\\n\\n\u003ci\u003eFace your demons\u003c/i\u003e","collection":"The Operation Hydra Collection","serialized_inspect":"steam://rungame/730/76561202255233023/+csgo_econ_action_preview%2000108CC9C293B50118092096052806300438F2FCB8EA0340D4026219080210AB391D3AC50D3F2D0000B4423DD04F92BD4578A48EBD621908001080431D9A99193F2D000010413D7359B5BE45D03A8ABCB168241C","gs_sig":"ce6539c73695d8477b9f"},"is_seller":false,"is_watchlisted":false,"watchers":111,"auction_details":{"reserve_price":100,"top_bid":{"id":"965930158307541489","created_at":"2026-04-19T11:01:35.855336Z","price":20250,"contract_id":"964425445636440955","state":"active","obfuscated_buyer_id":"11099198960927085086"},"expires_at":"2026-04-22T07:22:24.397789Z","min_next_bid":20500}},{"id":"964981537202373290","created_at":"2026-04-16T20:12:06.959917Z","type":"auction","price":21750,"state":"listed","seller":{"away":false,"flags":48,"obfuscated_id":"8810268866015226197","online":false,"stall_public":false,"statistics":{"median_trade_time":97,"total_avoided_trades":0,"total_failed_trades":0,"total_trades":54,"total_verified_trades":54}},"reference":{"base_price":86939,"float_factor":1,"predicted_price":86939,"quantity":17,"last_updated":"2026-04-19T14:14:19.323198Z"},"item":{"asset_id":"50959610741","def_index":515,"paint_index":44,"paint_seed":78,"float_value":0.8339350819587708,"icon_url":"i0CoZ81Ui0m-9KwlBY1L_18myuGuq1wfhWSaZgMttyVfPaERSR0Wqmu7LAocGIGz3UqlXOLrxM-vMGmW8VNxu5Dx60noTyL6kJ_m-B1Z-ua6bbZrLOmsD3avzud6teVWRyyygwRpsGiEyt2uIy6UbgEpWJR1E7ED5BC7kdHnM-y2tlOLi9lHyC2t2CtN5jErvbgVadjSoA","is_stattrak":true,"is_souvenir":false,"rarity":6,"quality":3,"market_hash_name":"★ StatTrak™ Butterfly Knife | Case Hardened (Battle-Scarred)","tradable":0,"inspect_link":"steam://rungame/730/76561202255233023/+csgo_econ_action_preview%200010F5E6B7EBBD01188304202C2806300338C5F9D5FA03404E480050B90A86D62D40","cs2_screenshot_id":"8902778107267851162","cs2_screenshot_at":"2026-04-09T09:49:46.006551Z","is_commodity":false,"type":"skin","rarity_name":"Covert","type_name":"Skin","item_name":"★ Butterfly Knife | Case Hardened","wear_name":"Battle-Scarred","description":"It has been color case-hardened through the application of wood charcoal at high temperatures.\\n\\n\u003ci\u003eA little color never hurt anyone\u003c/i\u003e","collection":"The Breakout Collection","badges":["blue_gem_3"],"blue_gem":{"backside_blue":41.27,"backside_purple":17.87,"backside_gold":40.86,"playside_blue":40.75,"playside_purple":17.72,"playside_gold":41.52},"serialized_inspect":"steam://rungame/730/76561202255233023/+csgo_econ_action_preview%200010F5E6B7EBBD01188304202C2806300338C5F9D5FA03404E480050B90A86D62D40","gs_sig":"042027eaf8c3511434c2"},"is_seller":false,"min_offer_price":20663,"max_offer_discount":500,"is_watchlisted":false,"watchers":129,"auction_details":{"reserve_price":3,"top_bid":{"id":"966039101943972129","created_at":"2026-04-19T18:14:30.042224Z","price":21750,"contract_id":"964981537202373290","state":"active","obfuscated_buyer_id":"10085049620171732098"},"expires_at":"2026-04-23T20:12:06.958881Z","min_next_bid":22000}},{"id":"915898775795532560","created_at":"2025-12-02T09:34:44.726653Z","type":"buy_now","price":899900,"state":"listed","seller":{"avatar":"https://avatars.steamstatic.com/099d2e7fd7f637fbd4c9825b939a792349cdda30_full.jpg","away":false,"flags":48,"online":false,"stall_public":true,"statistics":{"median_trade_time":10340,"total_avoided_trades":0,"total_failed_trades":0,"total_trades":1,"total_verified_trades":1},"steam_id":"76561198255550086","username":"Mayƒlower"},"reference":{"base_price":807662,"float_factor":1.18855,"predicted_price":959946,"quantity":68,"last_updated":"2026-04-19T16:36:45.758272Z"},"item":{"asset_id":"48023369563","def_index":5030,"paint_index":10048,"paint_seed":528,"float_value":0.06014237552881241,"icon_url":"i0CoZ81Ui0m-9KwlBY1L_18myuGuq1wfhWSaZgMttyVfPaERSR0Wqmu7LAocGIGz3UqlXOLrxM-vMGmW8VNxu5Tk5UvzWCL2kpn2-DFk_OKherB0H_KfG2Kv0ed4u95lRi67gVNx4T-Bw434IHyVb1QlAsd1FOUDthG4xNznMu3m4QXXg90Wzn_33C1I8G81tLaDi_rK","d_param":"16900752358352416048","is_stattrak":false,"is_souvenir":false,"rarity":6,"quality":3,"market_hash_name":"★ Sport Gloves | Vice (Factory New)","low_rank":3,"tradable":0,"inspect_link":"steam://rungame/730/76561202255233023/+csgo_econ_action_preview%20S76561198255550086A48023369563D16900752358352416048","cs2_screenshot_id":"2251284810886805975","cs2_screenshot_at":"2025-12-02T09:36:02.557899Z","is_commodity":false,"type":"skin","rarity_name":"Covert","type_name":"Skin","item_name":"★ Sport Gloves | Vice","wear_name":"Factory New","description":"These synthetic gloves are crafted from a striking mix pink and blue technical fabrics.","badges":["silver_lowest_float"],"serialized_inspect":"steam://rungame/730/76561202255233023/+csgo_econ_action_preview%200010DBEEA9F3B20118A62720C04E2806300338DAAFD9EB03409004DC1D7F2A","gs_sig":"cde16d8eef62b969e5b6"},"is_seller":false,"min_offer_price":827908,"max_offer_discount":800,"is_watchlisted":false,"watchers":122},{"id":"956604303802499647","created_at":"2026-03-24T17:23:58.875199Z","type":"buy_now","price":1500000,"state":"listed","seller":{"away":false,"flags":48,"obfuscated_id":"16836674560647849652","online":false,"stall_public":false,"statistics":{"median_trade_time":124,"total_avoided_trades":0,"total_failed_trades":0,"total_trades":32,"total_verified_trades":32}},"reference":{"base_price":1224822,"float_factor":1.26375,"predicted_price":1559463,"keychain_price":11589,"quantity":251,"last_updated":"2026-04-19T17:46:07.89375Z"},"item":{"asset_id":"47564419482","def_index":9,"paint_index":344,"paint_seed":145,"float_value":0.0044858213514089584,"icon_url":"i0CoZ81Ui0m-9KwlBY1L_18myuGuq1wfhWSaZgMttyVfPaERSR0Wqmu7LAocGIGz3UqlXOLrxM-vMGmW8VNxu5Dx60noTyLwiYbf_jdk4veqYaF7IfysCnWRxuF4j-B-Xxa_nBovp3Pdwtj9cC_GaAd0DZdwQu9fuhS4kNy0NePntVTbjYpCyyT_3CgY5i9j_a9cBkcCWUKV","is_stattrak":false,"is_souvenir":false,"rarity":6,"quality":4,"market_hash_name":"AWP | Dragon Lore (Factory New)","keychains":[{"stickerId":59,"slot":0,"offset_x":8.489196,"offset_y":1.3715806,"offset_z":10.716078,"pattern":92555,"icon_url":"https://community.akamai.steamstatic.com/economy/image/i0CoZ81Ui0m-9KwlBY1L_18myuGuq1wfhWSaZgMttyVfPaERSR0Wqmu7LAocGI6zwki4Uf_a0IWsPGiE7Fhy-I764WbkThD8i5jp6Ttkv6PhY6dSLfmAHW6exuJ_vupWQjynkBovvC6R1NatdHuTPQAiCJF1Re8KsBOwlda0M7vm7gOMj4kUnC__jysf5ytv4OccEf1yvJT6JNo","name":"Charm | Lil' Boo","reference":{"price":11918,"quantity":120,"updated_at":"2026-04-18T00:49:09.225745Z"}}],"tradable":0,"inspect_link":"steam://rungame/730/76561202255233023/+csgo_econ_action_preview%2000109AE3BD98B101180920D8022806300438CCFBCBDC03409101A2011C0800103B1D000000003DBFD3074145F48FAF3F4D0E752B41508BD305A3465B28","cs2_screenshot_id":"9119093324092476743","cs2_screenshot_at":"2026-03-26T01:32:15.677403Z","is_commodity":false,"type":"skin","rarity_name":"Covert","type_name":"Skin","item_name":"AWP | Dragon Lore","wear_name":"Factory New","description":"It has been custom painted with a knotwork dragon.\\n\\n\u003ci\u003e200 keys could never unlock its secrets\u003c/i\u003e","collection":"The Cobblestone Collection","serialized_inspect":"steam://rungame/730/76561202255233023/+csgo_econ_action_preview%2000109AE3BD98B101180920D8022806300438CCFBCBDC03409101A2011C0800103B1D000000003DBFD3074145F48FAF3F4D0E752B41508BD305A3465B28","gs_sig":"bbf340c5928dbdf73dda"},"is_seller":false,"min_offer_price":1380000,"max_offer_discount":800,"is_watchlisted":false,"watchers":146},{"id":"965351607820749565","created_at":"2026-04-17T20:42:38.67056Z","type":"buy_now","price":875000,"state":"listed","seller":{"avatar":"https://avatars.steamstatic.com/d46811978312195410879915c709601929cc9920_full.jpg","away":false,"flags":48,"online":false,"stall_public":true,"statistics":{"median_trade_time":1641,"total_avoided_trades":0,"total_failed_trades":0,"total_trades":147,"total_verified_trades":147},"steam_id":"76561198073900734","username":"RobertBaratheon"},"reference":{"base_price":807662,"float_factor":1.15659,"predicted_price":934132,"quantity":68,"last_updated":"2026-04-19T14:43:58.614329Z"},"item":{"asset_id":"50658438945","def_index":5030,"paint_index":10048,"paint_seed":690,"float_value":0.0601823627948761,"icon_url":"i0CoZ81Ui0m-9KwlBY1L_18myuGuq1wfhWSaZgMttyVfPaERSR0Wqmu7LAocGIGz3UqlXOLrxM-vMGmW8VNxu5Tk5UvzWCL2kpn2-DFk_OKherB0H_KfG2Kv0ed4u95lRi67gVNx4T-Bw434IHyVb1QlAsd1FOUDthG4xNznMu3m4QXXg90Wzn_33C1I8G81tLaDi_rK","is_stattrak":false,"is_souvenir":false,"rarity":6,"quality":3,"market_hash_name":"★ Sport Gloves | Vice (Factory New)","tradable":0,"cs2_screenshot_id":"4886175300193191327","cs2_screenshot_at":"2026-04-17T20:44:02.906126Z","is_commodity":false,"type":"skin","rarity_name":"Covert","type_name":"Skin","item_name":"★ Sport Gloves | Vice","wear_name":"Factory New","description":"These synthetic gloves are crafted from a striking mix pink and blue technical fabrics.","serialized_inspect":"steam://rungame/730/76561202255233023/+csgo_econ_action_preview%200010A1DEE9DBBC0118A62720C04E2806300338C883DAEB0340B205EE56DD37","gs_sig":"95fa89016d4603bf11d1"},"is_seller":false,"min_offer_price":805000,"max_offer_discount":800,"is_watchlisted":false,"watchers":7},{"id":"965604766136797882","created_at":"2026-04-18T13:28:36.316943Z","type":"buy_now","price":1232100,"state":"listed","seller":{"away":false,"flags":48,"obfuscated_id":"1607136186691736736","online":false,"stall_public":false,"statistics":{"median_trade_time":754,"total_avoided_trades":0,"total_failed_trades":1,"total_trades":1666,"total_verified_trades":1665}},"reference":{"base_price":1224822,"float_factor":1.05151,"predicted_price":1287907,"quantity":251,"last_updated":"2026-04-19T13:29:10.995061Z"},"item":{"asset_id":"50984064938","def_index":9,"paint_index":344,"paint_seed":181,"float_value":0.01692480407655239,"icon_url":"i0CoZ81Ui0m-9KwlBY1L_18myuGuq1wfhWSaZgMttyVfPaERSR0Wqmu7LAocGIGz3UqlXOLrxM-vMGmW8VNxu5Dx60noTyLwiYbf_jdk4veqYaF7IfysCnWRxuF4j-B-Xxa_nBovp3Pdwtj9cC_GaAd0DZdwQu9fuhS4kNy0NePntVTbjYpCyyT_3CgY5i9j_a9cBkcCWUKV","is_stattrak":false,"is_souvenir":false,"rarity":6,"quality":4,"market_hash_name":"AWP | Dragon Lore (Factory New)","low_rank":535,"tradable":0,"inspect_link":"steam://rungame/730/76561202255233023/+csgo_econ_action_preview%200010AAAF8CF7BD01180920D8022806300438E3CBAAE40340B5012F2EBA28","cs2_screenshot_id":"8963735220358617143","cs2_screenshot_at":"2026-04-18T13:30:14.675553Z","is_commodity":false,"type":"skin","rarity_name":"Covert","type_name":"Skin","item_name":"AWP | Dragon Lore","wear_name":"Factory New","description":"It has been custom painted with a knotwork dragon.\\n\\n\u003ci\u003e200 keys could never unlock its secrets\u003c/i\u003e","collection":"The Cobblestone Collection","serialized_inspect":"steam://rungame/730/76561202255233023/+csgo_econ_action_preview%200010AAAF8CF7BD01180920D8022806300438E3CBAAE40340B5012F2EBA28","gs_sig":"f31d18459d75cae6d3d1"},"is_seller":false,"min_offer_price":1219779,"max_offer_discount":100,"is_watchlisted":false,"watchers":9},{"id":"965914502514215269","created_at":"2026-04-19T09:59:23.223942Z","type":"buy_now","price":340000,"state":"listed","seller":{"avatar":"https://avatars.steamstatic.com/8c70959e1fbcddd87a02b50696d6fcb2736da094_full.jpg","away":false,"flags":48,"online":false,"stall_public":true,"statistics":{"median_trade_time":171,"total_avoided_trades":4,"total_failed_trades":3,"total_trades":775,"total_verified_trades":772},"steam_id":"76561199160426208","username":"Shaula"},"reference":{"base_price":368710,"float_factor":1.06917,"predicted_price":394213,"quantity":6,"last_updated":"2026-04-19T15:59:20.159396Z"},"item":{"asset_id":"51024650914","def_index":515,"paint_index":1105,"paint_seed":881,"float_value":0.009655123576521873,"icon_url":"i0CoZ81Ui0m-9KwlBY1L_18myuGuq1wfhWSaZgMttyVfPaERSR0Wqmu7LAocGIGz3UqlXOLrxM-vMGmW8VNxu5Dx60noTyL6kJ_m-B1Z-ua6bbZrLOmsDXKvw_tipOR7SSWqqhEooTi6lob-KT-JZw90XJMiTO8PukW4wIXmN-zq5gXf2tpBm37_2y4auylv5exUAKAi_7qX0V8Ly4BE2w","is_stattrak":true,"is_souvenir":false,"rarity":6,"quality":3,"market_hash_name":"★ StatTrak™ Butterfly Knife | Lore (Factory New)","low_rank":7,"tradable":0,"cs2_screenshot_id":"6126214494099938859","cs2_screenshot_at":"2026-04-19T10:05:52.741637Z","is_commodity":false,"type":"skin","rarity_name":"Covert","type_name":"Skin","item_name":"★ Butterfly Knife | Lore","wear_name":"Factory New","description":"It has been custom painted with knotwork.","serialized_inspect":"steam://rungame/730/76561202255233023/+csgo_econ_action_preview%200010A2C5B98ABE0118830420D108280630033886E1F8E00340F106480050B90A25126DE0","gs_sig":"7da5546ac19ae5e894ee"},"is_seller":false,"min_offer_price":306000,"max_offer_discount":1000,"is_watchlisted":false,"watchers":0},{"id":"965532641141064870","created_at":"2026-04-18T08:42:00.377148Z","type":"auction","price":7296,"state":"listed","seller":{"avatar":"https://avatars.steamstatic.com/b1bd2def42bd407d4fd970d92ca2acae31199eaf_full.jpg","away":false,"flags":48,"online":false,"stall_public":true,"statistics":{"median_trade_time":457,"total_avoided_trades":0,"total_failed_trades":0,"total_trades":700,"total_verified_trades":700},"steam_id":"76561197974635628","username":"🗿⃤⃢🍷N ckelJinn"},"reference":{"base_price":60945,"float_factor":1.0012,"predicted_price":61018,"quantity":445,"last_updated":"2026-04-19T14:38:39.192792Z"},"item":{"asset_id":"47774135825","def_index":5031,"paint_index":10070,"paint_seed":604,"float_value":0.1360609382390976,"icon_url":"i0CoZ81Ui0m-9KwlBY1L_18myuGuq1wfhWSaZgMttyVfPaERSR0Wqmu7LAocGIGz3UqlXOLrxM-vMGmW8VNxu5T441rsfhr9kYDl7h1I4_utY5tnIfeGD3Wv1uZ_pORWQyC0nQlp4TnUw9f6J3PCOw4oW8ZxRuEOshK8l9fgZbnqswHX3owXmSisjCIfuzErvbiEoDwfJQ","is_stattrak":false,"is_souvenir":false,"rarity":6,"quality":3,"market_hash_name":"★ Driver Gloves | Snow Leopard (Minimal Wear)","tradable":0,"cs2_screenshot_id":"5966830551376276524","cs2_screenshot_at":"2026-04-18T08:50:37.67721Z","is_commodity":false,"type":"skin","rarity_name":"Covert","type_name":"Skin","item_name":"★ Driver Gloves | Snow Leopard","wear_name":"Minimal Wear","serialized_inspect":"steam://rungame/730/76561202255233023/+csgo_econ_action_preview%20001091ECBDFCB10118A72720D64E28063003388FA7ADF00340DC043917C9D6","gs_sig":"fbbaf3d973f88e99862e"},"is_seller":false,"min_offer_price":6713,"max_offer_discount":800,"is_watchlisted":false,"watchers":143,"auction_details":{"reserve_price":53,"top_bid":{"id":"965985065890876208","created_at":"2026-04-19T14:39:46.843034Z","price":7296,"contract_id":"965532641141064870","state":"active","obfuscated_buyer_id":"17954738811891056840"},"expires_at":"2026-04-25T08:42:00.375382Z","min_next_bid":7396}},{"id":"964971287086763159","created_at":"2026-04-16T19:31:23.141354Z","type":"auction","price":300000,"state":"listed","seller":{"away":false,"flags":48,"obfuscated_id":"1873572727980133725","online":false,"stall_public":false,"statistics":{"median_trade_time":63,"total_avoided_trades":0,"total_failed_trades":0,"total_trades":61,"total_verified_trades":61}},"reference":{"base_price":351491,"predicted_price":351491,"quantity":3,"last_updated":"2026-04-19T13:33:29.780039Z"},"item":{"asset_id":"50542095561","def_index":5034,"paint_index":1414,"paint_seed":411,"float_value":0.06879477947950363,"icon_url":"i0CoZ81Ui0m-9KwlBY1L_18myuGuq1wfhWSaZgMttyVfPaERSR0Wqmu7LAocGIGz3UqlXOLrxM-vMGmW8VNxu5Tk71ruQBH4jYLf-i5U-fe9V6NhL-aWMXSAxO1_se1gXD2Mkg8mtTuMjobGIyfGPV1PVssnHaMUthC9l9e2Mei25wTajN5EziT_2CodvSxs5ugBWKp2rvDX2Q6QMOc8tI5DeqjzpbB7FA","is_stattrak":false,"is_souvenir":false,"rarity":6,"quality":3,"market_hash_name":"★ Specialist Gloves | Blackbook (Factory New)","tradable":0,"inspect_link":"steam://rungame/730/76561202255233023/+csgo_econ_action_preview%200010C9D9ACA4BC0118AA2720860B2806300338C7C8B3EC03409B0392015C78","cs2_screenshot_id":"5601550692815697519","cs2_screenshot_at":"2026-03-30T13:48:18.868336Z","is_commodity":false,"type":"skin","rarity_name":"Covert","type_name":"Skin","item_name":"★ Specialist Gloves | Blackbook","wear_name":"Factory New","collection":"The Dead Hand Collection","serialized_inspect":"steam://rungame/730/76561202255233023/+csgo_econ_action_preview%200010C9D9ACA4BC0118AA2720860B2806300338C7C8B3EC03409B0392015C78","gs_sig":"d1d81539cb42ae548287"},"is_seller":false,"min_offer_price":276000,"max_offer_discount":800,"is_watchlisted":false,"watchers":10,"auction_details":{"reserve_price":300000,"expires_at":"2026-04-19T19:31:23.139857Z","min_next_bid":300000}},{"id":"960796424902148492","created_at":"2026-04-05T07:01:58.431178Z","type":"buy_now","price":350000,"state":"listed","seller":{"away":false,"flags":48,"obfuscated_id":"15738199009457591888","online":false,"stall_public":false,"statistics":{"median_trade_time":100,"total_avoided_trades":0,"total_failed_trades":0,"total_trades":1,"total_verified_trades":1}},"reference":{"base_price":399999,"predicted_price":399999,"quantity":5,"last_updated":"2026-04-19T13:12:55.726952Z"},"item":{"asset_id":"50649422490","def_index":5031,"paint_index":1398,"paint_seed":930,"float_value":0.06414821743965149,"icon_url":"i0CoZ81Ui0m-9KwlBY1L_18myuGuq1wfhWSaZgMttyVfPaERSR0Wqmu7LAocGIGz3UqlXOLrxM-vMGmW8VNxu5T441rsfhr9kYDl7h1c4_24bZtpMvmFC3Wv0ud6u95tXSi0mhMYpDWMjorGLSLANkI-ApsmQrFbtkPux4bgMuvg7gzWjI0Xnyz-23lI6i5s4bpWUqMl-6PQ2xaBb-Mdlpgj5g","is_stattrak":false,"is_souvenir":false,"rarity":6,"quality":3,"market_hash_name":"★ Driver Gloves | Wave Chaser (Factory New)","tradable":0,"inspect_link":"steam://rungame/730/76561202255233023/+csgo_econ_action_preview%2000109AB5C3D7BC0118A72720F60A2806300338A4C08DEC0340A207419E9581","cs2_screenshot_id":"2146419210671222576","cs2_screenshot_at":"2026-04-05T07:02:42.921724Z","is_commodity":false,"type":"skin","rarity_name":"Covert","type_name":"Skin","item_name":"★ Driver Gloves | Wave Chaser","wear_name":"Factory New","collection":"The Dead Hand Collection","serialized_inspect":"steam://rungame/730/76561202255233023/+csgo_econ_action_preview%2000109AB5C3D7BC0118A72720F60A2806300338A4C08DEC0340A207419E9581","gs_sig":"c7ae7dc31bf1d68f8e13"},"is_seller":false,"min_offer_price":322000,"max_offer_discount":800,"is_watchlisted":false,"watchers":13},{"id":"965990393156075916","created_at":"2026-04-19T15:00:56.963113Z","type":"buy_now","price":350000,"state":"listed","seller":{"away":false,"flags":48,"obfuscated_id":"6120335282772100051","online":false,"stall_public":false,"statistics":{"median_trade_time":0,"total_avoided_trades":0,"total_failed_trades":0,"total_trades":0,"total_verified_trades":0}},"reference":{"base_price":399999,"predicted_price":399999,"quantity":5,"last_updated":"2026-04-19T15:00:26.523999Z"},"item":{"asset_id":"50696886441","def_index":5031,"paint_index":1398,"paint_seed":209,"float_value":0.06764543801546097,"icon_url":"i0CoZ81Ui0m-9KwlBY1L_18myuGuq1wfhWSaZgMttyVfPaERSR0Wqmu7LAocGIGz3UqlXOLrxM-vMGmW8VNxu5T441rsfhr9kYDl7h1c4_24bZtpMvmFC3Wv0ud6u95tXSi0mhMYpDWMjorGLSLANkI-ApsmQrFbtkPux4bgMuvg7gzWjI0Xnyz-23lI6i5s4bpWUqMl-6PQ2xaBb-Mdlpgj5g","is_stattrak":false,"is_souvenir":false,"rarity":6,"quality":3,"market_hash_name":"★ Driver Gloves | Wave Chaser (Factory New)","tradable":0,"inspect_link":"steam://rungame/730/76561202255233023/+csgo_econ_action_preview%200010A9B194EEBC0118A72720F60A2806300338B193AAEC0340D101A6EB5146","cs2_screenshot_id":"3414566940959669222","cs2_screenshot_at":"2026-04-05T12:17:16.264707Z","is_commodity":false,"type":"skin","rarity_name":"Covert","type_name":"Skin","item_name":"★ Driver Gloves | Wave Chaser","wear_name":"Factory New","collection":"The Dead Hand Collection","serialized_inspect":"steam://rungame/730/76561202255233023/+csgo_econ_action_preview%200010A9B194EEBC0118A72720F60A2806300338B193AAEC0340D101A6EB5146","gs_sig":"161086c437f5e35a5fc8"},"is_seller":false,"min_offer_price":322000,"max_offer_discount":800,"is_watchlisted":false,"watchers":2},{"id":"965876871311002495","created_at":"2026-04-19T07:29:51.245775Z","type":"auction","price":30474,"state":"listed","seller":{"avatar":"https://avatars.steamstatic.com/1dcb05e25ff58c3dba5d0bed5ccdeca9b735a973_full.jpg","away":false,"flags":48,"online":false,"stall_public":true,"statistics":{"median_trade_time":73,"total_avoided_trades":0,"total_failed_trades":2,"total_trades":267,"total_verified_trades":265},"steam_id":"76561199073723073","username":"Amantes sunt amentes"},"reference":{"base_price":82042,"float_factor":0.975535,"predicted_price":80035,"quantity":550,"last_updated":"2026-04-19T13:28:34.339874Z"},"item":{"asset_id":"51007372319","def_index":508,"paint_index":413,"paint_seed":200,"float_value":0.028486762195825577,"icon_url":"i0CoZ81Ui0m-9KwlBY1L_18myuGuq1wfhWSaZgMttyVfPaERSR0Wqmu7LAocGIGz3UqlXOLrxM-vMGmW8VNxu5Dx60noTyL6kJ_m-B1Wts2sab1iLvWHMWad_uN3ouNlSha1lBkijDGMnYftb3OTbVRyD8Z1RrNctkS6kobkZLzi7gTW2NpFxH33hi9Nuno65uxXAqs7uvqA7lyFHH4","is_stattrak":false,"is_souvenir":false,"rarity":6,"quality":3,"market_hash_name":"★ M9 Bayonet | Marble Fade (Factory New)","tradable":0,"cs2_screenshot_id":"3200123799319788807","cs2_screenshot_at":"2026-04-19T07:31:04.50126Z","is_commodity":false,"type":"skin","rarity_name":"Covert","type_name":"Skin","item_name":"★ M9 Bayonet | Marble Fade","wear_name":"Factory New","description":"It has been painted with black and silver metallic paints using a marbleizing medium, then candy coated in three colors.\\n\\n\u003ci\u003eThe blade is made of many colors, but soon it all looks red\u003c/i\u003e","serialized_inspect":"steam://rungame/730/76561202255233023/+csgo_econ_action_preview%2000109FF89A82BE0118FC03209D03280630033892BAA5E70340C801E30B3F01","gs_sig":"58bf14b7d5e337b2d2b4"},"is_seller":false,"min_offer_price":28037,"max_offer_discount":800,"is_watchlisted":false,"watchers":79,"auction_details":{"reserve_price":100,"top_bid":{"id":"966011846379310185","created_at":"2026-04-19T16:26:11.809401Z","price":30474,"contract_id":"965876871311002495","state":"active","obfuscated_buyer_id":"1007858596809698211"},"expires_at":"2026-04-22T07:29:51.243477Z","min_next_bid":30974}},{"id":"965872600477729001","created_at":"2026-04-19T07:12:52.999416Z","type":"auction","price":10000,"description":"Flawless","state":"listed","seller":{"avatar":"https://avatars.steamstatic.com/8e067464915c8cfba0f9371acb991e43c8642365_full.jpg","away":false,"flags":48,"online":false,"stall_public":true,"statistics":{"median_trade_time":1103,"total_avoided_trades":0,"total_failed_trades":0,"total_trades":463,"total_verified_trades":463},"steam_id":"76561198200149414","username":"✪ Ram0saS"},"reference":{"base_price":53200,"float_factor":1.07819,"predicted_price":57360,"quantity":1222,"last_updated":"2026-04-19T13:12:17.991679Z"},"item":{"asset_id":"51012045053","def_index":5031,"paint_index":10041,"paint_seed":985,"float_value":0.12396572530269623,"icon_url":"i0CoZ81Ui0m-9KwlBY1L_18myuGuq1wfhWSaZgMttyVfPaERSR0Wqmu7LAocGIGz3UqlXOLrxM-vMGmW8VNxu5T441rsfhr9kYDl7h1I4_utY5t-LvGYC3SbyOBJp-lgWyyMmRQguynLz4r6Iy7EbFchApNyR-dbtEbuw4XkN7jq7gHdjtoQzi37hiwYvytvt_FCD_Ql24JgJg","is_stattrak":false,"is_souvenir":false,"rarity":6,"quality":3,"market_hash_name":"★ Driver Gloves | King Snake (Minimal Wear)","tradable":0,"cs2_screenshot_id":"6600140987031389479","cs2_screenshot_at":"2026-04-19T10:15:37.645654Z","is_commodity":false,"type":"skin","rarity_name":"Covert","type_name":"Skin","item_name":"★ Driver Gloves | King Snake","wear_name":"Minimal Wear","description":"It has been crafted out of white leather and snakeskin.","serialized_inspect":"steam://rungame/730/76561202255233023/+csgo_econ_action_preview%200010FD91B884BE0118A72720B94E2806300338BEC3F7EF0340D907D75BEA07","gs_sig":"3c430dbf2f1617352482"},"is_seller":false,"min_offer_price":9600,"max_offer_discount":400,"is_watchlisted":false,"watchers":27,"auction_details":{"reserve_price":10000,"expires_at":"2026-04-26T07:12:52.996582Z","min_next_bid":10000}},{"id":"965508911081849720","created_at":"2026-04-18T07:07:42.690936Z","type":"buy_now","price":288500,"state":"listed","seller":{"avatar":"https://avatars.steamstatic.com/33925ee28a207ae84bf94e84e9a56c83b76b2a29_full.jpg","away":false,"flags":48,"online":false,"stall_public":true,"statistics":{"median_trade_time":144,"total_avoided_trades":0,"total_failed_trades":0,"total_trades":115,"total_verified_trades":115},"steam_id":"76561198168051950","username":"r4wn"},"reference":{"base_price":270479,"float_factor":1.24044,"predicted_price":335514,"quantity":280,"last_updated":"2026-04-19T13:07:48.093042Z"},"item":{"asset_id":"51004446280","def_index":5033,"paint_index":10026,"paint_seed":789,"float_value":0.2278035283088684,"icon_url":"i0CoZ81Ui0m-9KwlBY1L_18myuGuq1wfhWSaZgMttyVfPaERSR0Wqmu7LAocGIGz3UqlXOLrxM-vMGmW8VNxu4r7_lb1QgTykpPf-i5U-fe9V6liNP-BDX6TzetJvehnWxanhxQmvTqJn7D0JC_OK1s-C5EjQuFZsxjpw9XvNezjtFGNi4tCyCz_2CIb6nlp67pQV6pz-6WDiRaBb-O-i3lTww","is_stattrak":false,"is_souvenir":false,"rarity":6,"quality":3,"market_hash_name":"★ Moto Gloves | Spearmint (Field-Tested)","tradable":0,"cs2_screenshot_id":"1338436894069743193","cs2_screenshot_at":"2026-04-18T07:09:39.555904Z","is_commodity":false,"type":"skin","rarity_name":"Covert","type_name":"Skin","item_name":"★ Moto Gloves | Spearmint","wear_name":"Field-Tested","description":"White leather and red stitching make these gloves as stylish as they are comfortable.\\n\\n\u003ci\u003eFor what he's charging us, you'd think Huxley could at least throw in a tin of mints... - Felix Riley, Commanding Officer\u003c/i\u003e","serialized_inspect":"steam://rungame/730/76561202255233023/+csgo_econ_action_preview%200010C8ACE880BE0118A92720AA4E2806300338D48AA5F30340950696F4CE73","gs_sig":"9cbd1746e69eb5ba60bf"},"is_seller":false,"min_offer_price":282730,"max_offer_discount":200,"is_watchlisted":false,"watchers":7},{"id":"964667985652484029","created_at":"2026-04-15T23:26:10.444798Z","type":"auction","price":12100,"description":"Great Pattern ","state":"listed","seller":{"away":false,"flags":48,"obfuscated_id":"15094437064380804677","online":false,"stall_public":false,"statistics":{"median_trade_time":34,"total_avoided_trades":0,"total_failed_trades":0,"total_trades":16,"total_verified_trades":16}},"reference":{"base_price":58032,"float_factor":1.01797,"predicted_price":59075,"quantity":177,"last_updated":"2026-04-19T17:26:36.256021Z"},"item":{"asset_id":"48735584143","def_index":5030,"paint_index":10076,"paint_seed":917,"float_value":0.40330788493156433,"icon_url":"i0CoZ81Ui0m-9KwlBY1L_18myuGuq1wfhWSaZgMttyVfPaERSR0Wqmu7LAocGIGz3UqlXOLrxM-vMGmW8VNxu5Tk5UvzWCL2kpn2-DFk_OKherB0H_qSCXKR09F7teVgWiT9k08l5WrVnNeuI3qRaAEmCZJ0FuRYsRDsm9LnMryw71HfiooUmSn9hzQJsHg51Ex1iQ","is_stattrak":false,"is_souvenir":false,"rarity":6,"quality":3,"market_hash_name":"★ Sport Gloves | Nocts (Well-Worn)","tradable":0,"inspect_link":"steam://rungame/730/76561202255233023/+csgo_econ_action_preview%2000108FFFF7C6B50118A62720DC4E2806300338DFFCB9F60340950771DE8E03","cs2_screenshot_id":"5183623210362740491","cs2_screenshot_at":"2026-04-15T23:27:29.660571Z","is_commodity":false,"type":"skin","rarity_name":"Covert","type_name":"Skin","item_name":"★ Sport Gloves | Nocts","wear_name":"Well-Worn","serialized_inspect":"steam://rungame/730/76561202255233023/+csgo_econ_action_preview%2000108FFFF7C6B50118A62720DC4E2806300338DFFCB9F60340950771DE8E03","gs_sig":"e9de143aa408aafa2001"},"is_seller":false,"min_offer_price":11132,"max_offer_discount":800,"is_watchlisted":false,"watchers":138,"auction_details":{"reserve_price":10000,"top_bid":{"id":"966011995084163380","created_at":"2026-04-19T16:26:47.26334Z","price":12100,"contract_id":"964667985652484029","state":"active","obfuscated_buyer_id":"1007858596809698211"},"expires_at":"2026-04-22T23:26:10.415828Z","min_next_bid":12350}},{"id":"964984903580123386","created_at":"2026-04-16T20:25:29.566951Z","type":"buy_now","price":290000,"state":"listed","seller":{"avatar":"https://avatars.steamstatic.com/aa5080d975c5f55a60062adab0571aa3fc3bae72_full.jpg","away":false,"flags":48,"online":false,"stall_public":true,"statistics":{"median_trade_time":72,"total_avoided_trades":0,"total_failed_trades":1,"total_trades":84,"total_verified_trades":83},"steam_id":"76561198109227466","username":"Pugdog"},"reference":{"base_price":270479,"float_factor":1.24175,"predicted_price":335868,"quantity":280,"last_updated":"2026-04-19T14:27:18.970997Z"},"item":{"asset_id":"48441272100","def_index":5033,"paint_index":10026,"paint_seed":920,"float_value":0.2239738404750824,"icon_url":"i0CoZ81Ui0m-9KwlBY1L_18myuGuq1wfhWSaZgMttyVfPaERSR0Wqmu7LAocGIGz3UqlXOLrxM-vMGmW8VNxu4r7_lb1QgTykpPf-i5U-fe9V6liNP-BDX6TzetJvehnWxanhxQmvTqJn7D0JC_OK1s-C5EjQuFZsxjpw9XvNezjtFGNi4tCyCz_2CIb6nlp67pQV6pz-6WDiRaBb-O-i3lTww","is_stattrak":false,"is_souvenir":false,"rarity":6,"quality":3,"market_hash_name":"★ Moto Gloves | Spearmint (Field-Tested)","tradable":0,"cs2_screenshot_id":"7172251122516323503","cs2_screenshot_at":"2026-04-16T20:26:33.62716Z","is_commodity":false,"type":"skin","rarity_name":"Covert","type_name":"Skin","item_name":"★ Moto Gloves | Spearmint","wear_name":"Field-Tested","description":"White leather and red stitching make these gloves as stylish as they are comfortable.\\n\\n\u003ci\u003eFor what he's charging us, you'd think Huxley could at least throw in a tin of mints... - Felix Riley, Commanding Officer\u003c/i\u003e","serialized_inspect":"steam://rungame/730/76561202255233023/+csgo_econ_action_preview%200010A4CECCBAB40118A92720AA4E2806300338E6B295F3034098079702246B","gs_sig":"45b1dfc7418b94635e35"},"is_seller":false,"min_offer_price":266800,"max_offer_discount":800,"is_watchlisted":false,"watchers":7},{"id":"966001625099537479","created_at":"2026-04-19T15:45:34.866916Z","type":"auction","price":156623,"state":"listed","seller":{"away":false,"flags":48,"obfuscated_id":"7431551762008794348","online":false,"stall_public":false,"statistics":{"median_trade_time":297,"total_avoided_trades":0,"total_failed_trades":4,"total_trades":255,"total_verified_trades":251}},"reference":{"base_price":186536,"float_factor":1.083294,"predicted_price":202073,"quantity":342,"last_updated":"2026-04-19T15:44:12.291676Z"},"item":{"asset_id":"50875487109","def_index":4,"paint_index":38,"paint_seed":435,"float_value":0.0339265801012516,"icon_url":"i0CoZ81Ui0m-9KwlBY1L_18myuGuq1wfhWSaZgMttyVfPaERSR0Wqmu7LAocGIGz3UqlXOLrxM-vMGmW8VNxu5Dx60noTyL2kpnj9h1a7s2oaaBoH_yaCW-Ej-8u5bZvHnq1w0Vz62TUzNj4eCiVblMmXMAkROJeskLpkdXjMrzksVTAy9US8PY25So","is_stattrak":false,"is_souvenir":false,"rarity":4,"quality":4,"market_hash_name":"Glock-18 | Fade (Factory New)","stickers":[{"stickerId":7246,"slot":1,"offset_x":0.033789396,"offset_y":-0.023624986,"icon_url":"https://community.akamai.steamstatic.com/economy/image/i0CoZ81Ui0m-9KwlBY1L_18myuGuq1wfhWSaZgMttyVfPaERSR0Wqmu7LAocGJai0ki7VeTHjMmuOHaC619h7cj35VTqVBP4io_fr3IJu72mZ6hiH_ycGG6extFzqeR6ASrllER_5m3QzdugJHiRblIjD8B3ROILtRW-kIK1Mbjh5lfWj4NDzn_gznQeSY6KSCc","name":"Sticker | Loving Eyes (Holo)","reference":{"price":467,"quantity":537,"updated_at":"2026-04-18T00:49:29.572667Z"}},{"stickerId":4613,"slot":2,"wear":1,"offset_x":-0.0324319,"offset_y":-0.024366975,"icon_url":"https://community.akamai.steamstatic.com/economy/image/i0CoZ81Ui0m-9KwlBY1L_18myuGuq1wfhWSaZgMttyVfPaERSR0Wqmu7LAocGJai0ki7VeTHjMutLGPY7VN0-JP81V_oSBG_nJOzrXdf7KP-OqY7IfHLXz7AwLgu6eU8HXDrzRsi6j_WydirdimWPBhgVMXtl-2Adw","name":"Sticker | Health (Gold)","reference":{"price":946,"quantity":147,"updated_at":"2026-04-18T03:50:56.959141Z"}}],"tradable":0,"inspect_link":"steam://rungame/730/76561202255233023/+csgo_econ_action_preview%20001085A7A9C3BD0118042026280430043899EDABE80340B3036214080110CE381D000000003DC0660A3D453089C1BC621408021085241D0000803F3D50D704BD45409DC7BC338AA7D9","cs2_screenshot_id":"7704083206694701605","cs2_screenshot_at":"2026-04-12T17:02:40.400759Z","is_commodity":false,"type":"skin","rarity_name":"Restricted","type_name":"Skin","item_name":"Glock-18 | Fade","wear_name":"Factory New","description":"It has been painted by airbrushing transparent paints that fade together over a chrome base coat.\\n\\n\u003ci\u003eThis isn't just a weapon, it's a conversation piece - Imogen, Arms Dealer In Training\u003c/i\u003e","collection":"The Assault Collection","fade":{"seed":435,"percentage":97.98511,"rank":110,"type":"fade"},"serialized_inspect":"steam://rungame/730/76561202255233023/+csgo_econ_action_preview%20001085A7A9C3BD0118042026280430043899EDABE80340B3036214080110CE381D000000003DC0660A3D453089C1BC621408021085241D0000803F3D50D704BD45409DC7BC338AA7D9","gs_sig":"7a5345cddcf854f83f60"},"is_seller":false,"is_watchlisted":false,"watchers":6,"auction_details":{"reserve_price":156623,"expires_at":"2026-04-20T15:45:34.865396Z","min_next_bid":156623}},{"id":"965876573989372501","created_at":"2026-04-19T07:28:40.358792Z","type":"auction","price":11600,"state":"listed","seller":{"avatar":"https://avatars.steamstatic.com/1dcb05e25ff58c3dba5d0bed5ccdeca9b735a973_full.jpg","away":false,"flags":48,"online":false,"stall_public":true,"statistics":{"median_trade_time":73,"total_avoided_trades":0,"total_failed_trades":2,"total_trades":267,"total_verified_trades":265},"steam_id":"76561199073723073","username":"Amantes sunt amentes"},"reference":{"base_price":56011,"float_factor":0.997954,"predicted_price":55896,"quantity":97,"last_updated":"2026-04-19T13:28:34.339874Z"},"item":{"asset_id":"50999894694","def_index":518,"paint_index":415,"paint_seed":844,"float_value":0.03283660486340523,"icon_url":"i0CoZ81Ui0m-9KwlBY1L_18myuGuq1wfhWSaZgMttyVfPaERSR0Wqmu7LAocGIGz3UqlXOLrxM-vMGmW8VNxu5Dx60noTyL6kJ_m-B1Y7vyne5tsLc-BG2WJ_uN3ouNlSiCpkBkYvzSCkpu3dnLGOFMmXJJ5FLMC5Ba-w4CzP763tFHZ3Y8Xnir73yJB6So4sOtUU71lpPMvbRQrHg","is_stattrak":false,"is_souvenir":false,"rarity":6,"quality":3,"market_hash_name":"★ Survival Knife | Doppler (Factory New)","low_rank":715,"high_rank":351,"tradable":0,"cs2_screenshot_id":"5674536060393605536","cs2_screenshot_at":"2026-04-19T07:31:55.88964Z","is_commodity":false,"type":"skin","rarity_name":"Covert","type_name":"Skin","item_name":"★ Survival Knife | Doppler","wear_name":"Factory New","phase":"Ruby","description":"It has been painted with black and silver metallic paints using a marbleizing medium, then candy coated.\\n\\n\u003ci\u003eGetting lost in its color can prove fatal\u003c/i\u003e","collection":"The Fever Collection","serialized_inspect":"steam://rungame/730/76561202255233023/+csgo_econ_action_preview%200010A6C5D2FEBD01188604209F032806300338ADFF99E80340CC065923B4F9","gs_sig":"45eb4c758f9a48348249"},"is_seller":false,"min_offer_price":10672,"max_offer_discount":800,"is_watchlisted":false,"watchers":86,"auction_details":{"reserve_price":100,"top_bid":{"id":"966010221686295685","created_at":"2026-04-19T16:19:44.452671Z","price":11600,"contract_id":"965876573989372501","state":"active","obfuscated_buyer_id":"12151054927184156300"},"expires_at":"2026-04-22T07:28:40.355563Z","min_next_bid":11850}},{"id":"963882194298865503","created_at":"2026-04-13T19:23:43.186967Z","type":"auction","price":101000,"description":"3rd Max Fire \u0026 Ice","state":"listed","seller":{"away":false,"flags":48,"obfuscated_id":"9614171646324943223","online":false,"stall_public":false,"statistics":{"median_trade_time":76,"total_avoided_trades":0,"total_failed_trades":0,"total_trades":93,"total_verified_trades":93}},"reference":{"base_price":111531,"float_factor":1.27868,"predicted_price":142613,"quantity":955,"last_updated":"2026-04-19T13:26:25.863276Z"},"item":{"asset_id":"50753058980","def_index":507,"paint_index":413,"paint_seed":281,"float_value":0.03425820916891098,"icon_url":"i0CoZ81Ui0m-9KwlBY1L_18myuGuq1wfhWSaZgMttyVfPaERSR0Wqmu7LAocGIGz3UqlXOLrxM-vMGmW8VNxu5Dx60noTyL6kJ_m-B1Q7uCvZaZkNM-SA1idwPx0vORWSSi3kCIrujqNjsGveH2RaVRxX5ohEe4Juhawm4fiM-ji4APf2YMXmSz_hyoduytv4uhWT-N7rfLHGBJ4","is_stattrak":false,"is_souvenir":false,"rarity":6,"quality":3,"market_hash_name":"★ Karambit | Marble Fade (Factory New)","tradable":0,"inspect_link":"steam://rungame/730/76561202255233023/+csgo_econ_action_preview%200010A4F1F888BD0118FB03209D032806300338D6A4B1E8034099021D848903","cs2_screenshot_id":"3957367244087937300","cs2_screenshot_at":"2026-04-08T16:46:46.80674Z","is_commodity":false,"type":"skin","rarity_name":"Covert","type_name":"Skin","item_name":"★ Karambit | Marble Fade","wear_name":"Factory New","description":"It has been painted with black and silver metallic paints using a marbleizing medium, then candy coated in three colors.\\n\\n\u003ci\u003eThe blade is made of many colors, but soon it all looks red\u003c/i\u003e","badges":["fi_max_3"],"serialized_inspect":"steam://rungame/730/76561202255233023/+csgo_econ_action_preview%200010A4F1F888BD0118FB03209D032806300338D6A4B1E8034099021D848903","gs_sig":"85e99a3399a5b0c4f164"},"is_seller":false,"min_offer_price":92920,"max_offer_discount":800,"is_watchlisted":false,"watchers":410,"auction_details":{"reserve_price":10000,"top_bid":{"id":"965667575839196535","created_at":"2026-04-18T17:38:11.31651Z","price":101000,"contract_id":"963882194298865503","state":"active","obfuscated_buyer_id":"14719324606152574439"},"expires_at":"2026-04-20T19:23:43.185828Z","min_next_bid":103500}},{"id":"965799017340600746","created_at":"2026-04-19T02:20:29.412563Z","type":"auction","price":13150,"description":"Max Cyan - Best Pattern(763)","state":"listed","seller":{"avatar":"https://avatars.steamstatic.com/aff07965d2bb933dd072b3fc103a4c97feb07eba_full.jpg","away":false,"flags":48,"online":false,"stall_public":true,"statistics":{"median_trade_time":117,"total_avoided_trades":0,"total_failed_trades":0,"total_trades":1306,"total_verified_trades":1306},"steam_id":"76561198348305776","username":"Benji"},"reference":{"base_price":53535,"float_factor":1.01543,"predicted_price":54361,"quantity":102,"last_updated":"2026-04-19T14:16:48.178373Z"},"item":{"asset_id":"51166971111","def_index":500,"paint_index":571,"paint_seed":763,"float_value":0.034784626215696335,"icon_url":"i0CoZ81Ui0m-9KwlBY1L_18myuGuq1wfhWSaZgMttyVfPaERSR0Wqmu7LAocGIGz3UqlXOLrxM-vMGmW8VNxu5Dx60noTyLzn4_v8ydP0POjV6NsLf2SMWOf0f56tfNWXyGyhhh0jDGMnYftb3ifPQd2ApZ3Redb5xG-mtzkNuPr5ADXg4tGm33_23hLvCZrt-9XV_Y7uvqA1Mz9WrE","is_stattrak":false,"is_souvenir":false,"rarity":6,"quality":3,"market_hash_name":"★ Bayonet | Gamma Doppler (Factory New)","high_rank":567,"tradable":0,"cs2_screenshot_id":"621375726478885727","cs2_screenshot_at":"2026-04-19T02:20:44.067089Z","is_commodity":false,"type":"skin","rarity_name":"Covert","type_name":"Skin","item_name":"★ Bayonet | Gamma Doppler","wear_name":"Factory New","phase":"Phase 3","description":"It has been painted with black and silver metallic paints using a marbleizing medium, then candy coated.","serialized_inspect":"steam://rungame/730/76561202255233023/+csgo_econ_action_preview%200010E789A8CEBE0118F40320BB042806300338D3F4B9E80340FB05E90C3F35","gs_sig":"31c23279be1c8937dd78"},"is_seller":false,"min_offer_price":12493,"max_offer_discount":500,"is_watchlisted":false,"watchers":107,"auction_details":{"reserve_price":3,"top_bid":{"id":"966033461527842100","created_at":"2026-04-19T17:52:05.262548Z","price":13150,"contract_id":"965799017340600746","state":"active","obfuscated_buyer_id":"10143300228296059909"},"expires_at":"2026-04-22T02:20:29.409632Z","min_next_bid":13400}},{"id":"962664290886746904","created_at":"2026-04-10T10:44:12.385853Z","type":"buy_now","price":575284,"state":"listed","seller":{"away":false,"flags":48,"obfuscated_id":"17997965507313012290","online":false,"stall_public":false,"statistics":{"median_trade_time":78,"total_avoided_trades":0,"total_failed_trades":2,"total_trades":246,"total_verified_trades":244}},"reference":{"base_price":559578,"float_factor":1.1013,"predicted_price":616266,"quantity":181,"last_updated":"2026-04-19T16:51:33.242757Z"},"item":{"asset_id":"40142273060","def_index":7,"paint_index":456,"paint_seed":50,"float_value":0.006935127079486847,"icon_url":"i0CoZ81Ui0m-9KwlBY1L_18myuGuq1wfhWSaZgMttyVfPaERSR0Wqmu7LAocGIGz3UqlXOLrxM-vMGmW8VNxu5Dx60noTyLwlcK3wiNW0PCvZaZiL8-ZG2mXzetJvOhuRz39lk0m4Dncztz7Jy2fagIoC5t5QeNbskW6xNLgZu-24AXZgt4Xyi_4izQJsHjOr8RS6A","d_param":"13871096346039028573","is_stattrak":false,"is_souvenir":false,"rarity":5,"quality":4,"market_hash_name":"AK-47 | Hydroponic (Factory New)","stickers":[{"stickerId":1032,"slot":3,"icon_url":"https://community.akamai.steamstatic.com/economy/image/i0CoZ81Ui0m-9KwlBY1L_18myuGuq1wfhWSaZgMttyVfPaERSR0Wqmu7LAocGJai0ki7VeTHjMmuOW6a50NmptelvBbqUg7Olpns8mxZ7aH-P_U0eKXHXT7Fx7xy57A-HyzhwxhztTuByYygcC_Ba1MjCJFzW6dU5VLMnBLW","name":"Sticker | mousesports (Holo) | MLG Columbus 2016","reference":{"price":4992,"quantity":54,"updated_at":"2026-04-18T01:49:57.296425Z"}},{"stickerId":1032,"slot":0,"icon_url":"https://community.akamai.steamstatic.com/economy/image/i0CoZ81Ui0m-9KwlBY1L_18myuGuq1wfhWSaZgMttyVfPaERSR0Wqmu7LAocGJai0ki7VeTHjMmuOW6a50NmptelvBbqUg7Olpns8mxZ7aH-P_U0eKXHXT7Fx7xy57A-HyzhwxhztTuByYygcC_Ba1MjCJFzW6dU5VLMnBLW","name":"Sticker | mousesports (Holo) | MLG Columbus 2016","reference":{"price":4992,"quantity":54,"updated_at":"2026-04-18T01:49:57.296425Z"}},{"stickerId":1032,"slot":2,"offset_x":0.017897993,"offset_y":-0.000711292,"icon_url":"https://community.akamai.steamstatic.com/economy/image/i0CoZ81Ui0m-9KwlBY1L_18myuGuq1wfhWSaZgMttyVfPaERSR0Wqmu7LAocGJai0ki7VeTHjMmuOW6a50NmptelvBbqUg7Olpns8mxZ7aH-P_U0eKXHXT7Fx7xy57A-HyzhwxhztTuByYygcC_Ba1MjCJFzW6dU5VLMnBLW","name":"Sticker | mousesports (Holo) | MLG Columbus 2016","reference":{"price":4992,"quantity":54,"updated_at":"2026-04-18T01:49:57.296425Z"}},{"stickerId":1032,"slot":1,"offset_x":0.0023575425,"offset_y":-0.0044798553,"icon_url":"https://community.akamai.steamstatic.com/economy/image/i0CoZ81Ui0m-9KwlBY1L_18myuGuq1wfhWSaZgMttyVfPaERSR0Wqmu7LAocGJai0ki7VeTHjMmuOW6a50NmptelvBbqUg7Olpns8mxZ7aH-P_U0eKXHXT7Fx7xy57A-HyzhwxhztTuByYygcC_Ba1MjCJFzW6dU5VLMnBLW","name":"Sticker | mousesports (Holo) | MLG Columbus 2016","reference":{"price":4992,"quantity":54,"updated_at":"2026-04-18T01:49:57.296425Z"}}],"low_rank":228,"tradable":0,"inspect_link":"steam://rungame/730/76561202255233023/+csgo_econ_action_preview%200010A4F4A9C59501180720C803280530043890808DDF034032620A08031088081D00000000620A08001088081D00000000621408021088081D000000003DD09E923C4500763ABA621408011088081D000000003D00811A3B45C0CB92BB5C93F3FD","cs2_screenshot_id":"7141458955967018685","cs2_screenshot_at":"2025-11-10T01:04:11.172262Z","is_commodity":false,"type":"skin","rarity_name":"Classified","type_name":"Skin","item_name":"AK-47 | Hydroponic","wear_name":"Factory New","description":"It has been painted with a bamboo motif using metallic paints.\\n\\n\u003ci\u003eNotice how Gunsmith Yukako used the wood of the AK-47 to accentuate her verdant theme... make no mistake: Hydroponic is as beautiful and deadly as nature itself - Imogen, Arms Dealer In Training\u003c/i\u003e","collection":"The Rising Sun Collection","serialized_inspect":"steam://rungame/730/76561202255233023/+csgo_econ_action_preview%200010A4F4A9C59501180720C803280530043890808DDF034032620A08031088081D00000000620A08001088081D00000000621408021088081D000000003DD09E923C4500763ABA621408011088081D000000003D00811A3B45C0CB92BB5C93F3FD","gs_sig":"18d0b6840d197517bbb9"},"is_seller":false,"is_watchlisted":false,"watchers":33}],"cursor":"CAEQBxjV05TPBiCYhojCp8KErg0opPSpxZUBOOq__f_______wEgAcLmJOs"}
diff --git a/test_proxies.py b/test_proxies.py
new file mode 100644
index 0000000..49dbb6f
--- /dev/null
+++ b/test_proxies.py
@@ -0,0 +1,65 @@
+# ---------------------------------------------
+# getting the list
+
+# import requests
+
+import os
+import requests
+WEBSHARE_API_KEY = os.environ.get("WEBSHARE_API_KEY")
+PLAN_ID = 13345956
+
+# res = requests.get(
+#     # f"https://proxy.webshare.io/api/v2/proxy/list/download/wkiosfpdfdodqhaqjjgeqrvdxavgalhszjdbtmtq/{TOKEN}/any/username/direct/-/?plan_id=13345956"
+#     f"https://proxy.webshare.io/api/v2/proxy/list/download/{TOKEN}/-/any/username/direct/san%20francisco/"
+# )
+
+# print(res.text)
+
+
+# -----------------------------------------------
+# testing proxies
+
+
+# import requests
+# print(requests.get(
+#     "https://ipv4.webshare.io/",
+# ).text)
+
+
+# ----------------------------------------------
+# get proxy config, get proxy list, use proxies to send requests
+
+
+response = requests.get(
+    f"https://proxy.webshare.io/api/v3/proxy/config?plan_id={PLAN_ID}",
+    headers={"Authorization": f"Token {WEBSHARE_API_KEY}"}
+)
+
+proxy_list_download_token = response.json()['proxy_list_download_token']
+
+
+res = requests.get(
+    f"https://proxy.webshare.io/api/v2/proxy/list/download/{proxy_list_download_token}/-/any/username/direct/-/"
+)
+
+print(res.text)
+
+proxies_raw = res.text.split("\r\n")
+proxies = []
+for entry in proxies_raw:
+    if entry == '':
+        continue
+
+    addr, port, username, password = entry.split(":")
+    proxies.append(f"{username}:{password}@{addr}:{port}/")
+
+for proxy in proxies:
+    res = requests.get(
+        "https://ipv4.webshare.io/",
+        proxies={
+            "http": f"http://{proxy}",
+            "https": f"http://{proxy}"
+        }
+    )
+
+    print(res.text)
diff --git a/tests/test_fetchers_async.py b/tests/test_fetchers_async.py
new file mode 100644
index 0000000..110a4e7
--- /dev/null
+++ b/tests/test_fetchers_async.py
@@ -0,0 +1,311 @@
+from __future__ import annotations
+
+import asyncio
+import json
+import sys
+import types
+import unittest
+from contextlib import contextmanager
+
+
+if "requests" not in sys.modules:
+    class _UnusedRequestsStub:
+        class HTTPError(Exception):
+            pass
+
+        class exceptions:
+            class Timeout(Exception):
+                pass
+
+            class ConnectionError(Exception):
+                pass
+
+        @staticmethod
+        def get(*args, **kwargs):  # pragma: no cover - guard for accidental sync network use
+            raise AssertionError("sync requests path should not be used by async fetcher tests")
+
+    sys.modules["requests"] = _UnusedRequestsStub()
+
+import base_screening_and_anal.fetchers as fetchers
+
+
+class FakeClientTimeout:
+    def __init__(self, *, total):
+        self.total = total
+
+
+class FakeTCPConnector:
+    def __init__(self, **kwargs):
+        self.kwargs = kwargs
+
+
+class FakeClientConnectionError(Exception):
+    pass
+
+
+class FakeResponse:
+    def __init__(self, status, body):
+        self.status = status
+        self.body = body if isinstance(body, str) else json.dumps(body)
+
+    async def __aenter__(self):
+        return self
+
+    async def __aexit__(self, exc_type, exc, tb):
+        return False
+
+    async def text(self):
+        return self.body
+
+    async def read(self):
+        return self.body.encode("utf-8")
+
+    def raise_for_status(self):
+        if self.status >= 400:
+            raise RuntimeError(f"HTTP {self.status}")
+
+
+class FakeSession:
+    def __init__(self, responses):
+        self.responses = list(responses)
+        self.calls = []
+
+    async def __aenter__(self):
+        return self
+
+    async def __aexit__(self, exc_type, exc, tb):
+        return False
+
+    async def close(self):
+        return None
+
+    def get(self, url, **kwargs):
+        self.calls.append({"url": url, **kwargs})
+        next_response = self.responses.pop(0)
+        if isinstance(next_response, BaseException):
+            raise next_response
+        return next_response
+
+
+class FakeAiohttp:
+    ClientTimeout = FakeClientTimeout
+    ClientConnectionError = FakeClientConnectionError
+    TCPConnector = FakeTCPConnector
+
+    def __init__(self, responses):
+        self.responses = list(responses)
+        self.sessions = []
+
+    def ClientSession(self, **kwargs):
+        session = FakeSession(self.responses)
+        session.kwargs = kwargs
+        self.sessions.append(session)
+        return session
+
+
+@contextmanager
+def patched_attrs(target, **attrs):
+    old_values = {name: getattr(target, name) for name in attrs}
+    for name, value in attrs.items():
+        setattr(target, name, value)
+    try:
+        yield
+    finally:
+        for name, value in old_values.items():
+            setattr(target, name, value)
+
+
+def no_runtime_delay(key, default):
+    zeroed = {
+        "STEAM_DELAY",
+        "FLOAT_DELAY",
+        "KEY_COOLDOWN_429_SEC",
+        "KEY_COOLDOWN_403_SEC",
+        "STEAM_429_RETRY_WAIT_SEC",
+        "STEAM_NET_SLEEP_MIN",
+        "STEAM_NET_SLEEP_MAX",
+        "CSFLOAT_5XX_SLEEP_MIN",
+        "CSFLOAT_5XX_SLEEP_MAX",
+        "CSFLOAT_NET_SLEEP_MIN",
+        "CSFLOAT_NET_SLEEP_MAX",
+    }
+    if key in zeroed:
+        return 0.0
+    return default
+
+
+class AsyncFetcherTests(unittest.IsolatedAsyncioTestCase):
+    async def test_async_json_request_sends_timeout_headers_and_decodes_json(self):
+        fake_aiohttp = types.SimpleNamespace(
+            ClientTimeout=FakeClientTimeout,
+            ClientConnectionError=FakeClientConnectionError,
+        )
+        session = FakeSession([FakeResponse(200, {"success": True, "price": "$1.23"})])
+
+        with patched_attrs(fetchers, aiohttp=fake_aiohttp):
+            status, data, text = await fetchers._async_json_request(
+                session,
+                "https://example.test/price",
+                params={"market_hash_name": "AK-47 | Redline"},
+                headers={"User-Agent": "test-agent"},
+                proxy="http://user:pass@127.0.0.1:8080",
+                timeout_sec=3.5,
+            )
+
+        self.assertEqual(status, 200)
+        self.assertEqual(data, {"success": True, "price": "$1.23"})
+        self.assertEqual(text, '{"success": true, "price": "$1.23"}')
+        self.assertEqual(session.calls[0]["url"], "https://example.test/price")
+        self.assertEqual(session.calls[0]["params"]["market_hash_name"], "AK-47 | Redline")
+        self.assertEqual(session.calls[0]["headers"]["User-Agent"], "test-agent")
+        self.assertEqual(session.calls[0]["proxy"], "http://user:pass@127.0.0.1:8080")
+        self.assertEqual(session.calls[0]["timeout"].total, 3.5)
+
+    async def test_async_steam_price_uses_median_when_lowest_price_missing(self):
+        fake_aiohttp = types.SimpleNamespace(
+            ClientTimeout=FakeClientTimeout,
+            ClientConnectionError=FakeClientConnectionError,
+        )
+        session = FakeSession([FakeResponse(200, {"success": True, "median_price": "$12.34"})])
+        limiter = fetchers._AsyncStartLimiter("STEAM_DELAY", 0.0)
+        semaphore = asyncio.Semaphore(1)
+
+        with patched_attrs(fetchers, aiohttp=fake_aiohttp, _runtime_float=no_runtime_delay):
+            price = await fetchers._async_get_steam_price(
+                session,
+                limiter,
+                semaphore,
+                None,
+                "AWP | Asiimov (Field-Tested)",
+                1,
+            )
+
+        self.assertEqual(price, 12.34)
+        self.assertEqual(session.calls[0]["url"], fetchers.STEAM_PRICEOVERVIEW_URL)
+        self.assertEqual(session.calls[0]["params"]["currency"], 1)
+        self.assertEqual(
+            session.calls[0]["params"]["market_hash_name"],
+            "AWP | Asiimov (Field-Tested)",
+        )
+
+    async def test_async_csfloat_rotates_key_after_429(self):
+        fake_aiohttp = types.SimpleNamespace(
+            ClientTimeout=FakeClientTimeout,
+            ClientConnectionError=FakeClientConnectionError,
+        )
+        session = FakeSession(
+            [
+                FakeResponse(429, {"message": "rate limited"}),
+                FakeResponse(
+                    200,
+                    {
+                        "data": [
+                            {
+                                "price": 1234,
+                                "reference": {
+                                    "predicted_price": 1400,
+                                    "base_price": 1000,
+                                    "quantity": 8,
+                                },
+                            }
+                        ]
+                    },
+                ),
+            ]
+        )
+        limiter = fetchers._AsyncStartLimiter("FLOAT_DELAY", 0.0)
+        semaphore = asyncio.Semaphore(1)
+        proxy_a = fetchers.ProxyEndpoint("http://user:pass@127.0.0.1:8080", "1:127.0.0.1:8080")
+        proxy_b = fetchers.ProxyEndpoint("http://user:pass@127.0.0.2:8080", "2:127.0.0.2:8080")
+        identity_pool = fetchers.AsyncRotationPool(
+            fetchers._build_csfloat_identities(("key-a", "key-b"), (proxy_a, proxy_b))
+        )
+
+        with patched_attrs(fetchers, aiohttp=fake_aiohttp, _runtime_float=no_runtime_delay):
+            result = await fetchers._async_get_csfloat_prices(
+                session,
+                limiter,
+                semaphore,
+                identity_pool,
+                "AK-47 | Redline (Field-Tested)",
+            )
+
+        self.assertEqual(result["ask"], 12.34)
+        self.assertEqual(result["predicted"], 14.0)
+        self.assertEqual(result["base"], 10.0)
+        self.assertEqual(result["quantity"], 8)
+        self.assertEqual(result["_key"], "2/2, ip=2:127.0.0.2:8080")
+        self.assertEqual(session.calls[0]["headers"]["Authorization"], "key-a")
+        self.assertEqual(session.calls[1]["headers"]["Authorization"], "key-b")
+        self.assertEqual(session.calls[0]["proxy"], "http://user:pass@127.0.0.1:8080")
+        self.assertEqual(session.calls[1]["proxy"], "http://user:pass@127.0.0.2:8080")
+
+    async def test_csfloat_identities_pair_keys_and_proxies_one_to_one(self):
+        proxies = (
+            fetchers.ProxyEndpoint("http://proxy-1", "1:proxy-1"),
+            fetchers.ProxyEndpoint("http://proxy-2", "2:proxy-2"),
+            fetchers.ProxyEndpoint("http://proxy-3", "3:proxy-3"),
+        )
+
+        identities = fetchers._build_csfloat_identities(("key-a", "key-b"), proxies)
+
+        self.assertEqual(len(identities), 2)
+        self.assertEqual((identities[0].key, identities[0].proxy.url), ("key-a", "http://proxy-1"))
+        self.assertEqual((identities[1].key, identities[1].proxy.url), ("key-b", "http://proxy-2"))
+
+
+class FetchAllPricesAsyncIntegrationTests(unittest.TestCase):
+    def test_fetch_all_prices_async_path_builds_dataframe_without_network(self):
+        fake_aiohttp = FakeAiohttp(
+            [
+                FakeResponse(200, {"success": True, "lowest_price": "$20.00"}),
+                FakeResponse(
+                    200,
+                    {
+                        "data": [
+                            {
+                                "price": 1500,
+                                "reference": {
+                                    "predicted_price": 1800,
+                                    "base_price": 1200,
+                                    "quantity": 3,
+                                },
+                            }
+                        ]
+                    },
+                ),
+            ]
+        )
+
+        with patched_attrs(
+            fetchers,
+            aiohttp=fake_aiohttp,
+            _runtime_float=no_runtime_delay,
+            _runtime_int=lambda key, default: default,
+            _csfloat_api_keys=lambda: ("test-key",),
+            FETCHERS_USE_AIOHTTP=True,
+        ):
+            df = fetchers.fetch_all_prices(
+                ["AK-47 | Redline (Field-Tested)"],
+                steam_delay=0.0,
+                float_delay=0.0,
+                steam_concurrency=2,
+                float_concurrency=2,
+                use_async=True,
+            )
+
+        self.assertEqual(len(df), 1)
+        row = df.iloc[0].to_dict()
+        self.assertEqual(row["item"], "AK-47 | Redline (Field-Tested)")
+        self.assertEqual(row["steam_ask"], 20.0)
+        self.assertEqual(row["float_ask"], 15.0)
+        self.assertEqual(row["float_pred"], 18.0)
+        self.assertEqual(row["float_base"], 12.0)
+        self.assertEqual(row["float_qty"], 3)
+        self.assertEqual(row["spread_ask%"], 25.0)
+        self.assertEqual(row["spread_pred%"], 10.0)
+        self.assertEqual(len(fake_aiohttp.sessions), 1)
+
+
+if __name__ == "__main__":
+    unittest.main()
diff --git a/tests/test_fetchers_e2e.py b/tests/test_fetchers_e2e.py
new file mode 100644
index 0000000..ce83a3f
--- /dev/null
+++ b/tests/test_fetchers_e2e.py
@@ -0,0 +1,379 @@
+from __future__ import annotations
+
+import asyncio
+import os
+import ipaddress
+import unittest
+
+
+if os.environ.get("RUN_FETCHERS_E2E") != "1":
+    raise unittest.SkipTest(
+        "set RUN_FETCHERS_E2E=1 to run live fetchers E2E tests")
+
+try:
+    import aiohttp  # noqa: F401
+    import requests  # noqa: F401
+except ImportError as exc:
+    raise unittest.SkipTest(
+        f"live E2E dependencies are not installed: {exc}") from exc
+
+import base_screening_and_anal.fetchers as fetchers
+from base_screening_and_anal.proxy_rotation import (
+    AsyncRotationPool,
+    SyncRotationPool,
+    fetch_webshare_proxies,
+)
+
+
+WEBSHARE_IP_ECHO_URL = "https://ipv4.webshare.io/"
+MIN_WEBSHARE_E2E_IPS = 5
+FETCHER_PROXY_E2E_PAIR_COUNT = max(
+    1, int(os.environ.get("FETCHER_PROXY_E2E_PAIR_COUNT", "5")))
+STEAM_ONLY_E2E_TIMEOUT_SEC = float(
+    os.environ.get("STEAM_ONLY_E2E_TIMEOUT_SEC", "30"))
+FETCHER_PROXY_E2E_ITEMS = [
+    "AK-47 | Redline (Field-Tested)",
+    "AWP | Asiimov (Field-Tested)",
+    "M4A1-S | Printstream (Field-Tested)",
+    "USP-S | Kill Confirmed (Field-Tested)",
+    "Glock-18 | Water Elemental (Field-Tested)",
+]
+
+
+def _short_text(text: str, limit: int = 120) -> str:
+    compact = " ".join(text.split())
+    if len(compact) <= limit:
+        return compact
+    return f"{compact[:limit]}..."
+
+
+class FetchersLiveE2ETests(unittest.TestCase):
+    def test_fetch_all_prices_async_live_smoke(self):
+        if not _configured_csfloat_keys():
+            self.skipTest("CSFLOAT_API_KEY is required for live CSFloat E2E")
+
+        df = fetchers.fetch_all_prices(
+            ["AK-47 | Redline (Field-Tested)"],
+            steam_delay=0.25,
+            float_delay=0.25,
+            steam_concurrency=1,
+            float_concurrency=1,
+            use_async=True,
+        )
+
+        self.assertFalse(df.empty)
+        self.assertEqual(df.iloc[0]["item"], "AK-47 | Redline (Field-Tested)")
+        for column in ("steam_ask", "float_ask", "float_pred", "spread_pred%"):
+            self.assertIn(column, df.columns)
+
+    def test_webshare_proxy_rotation_has_at_least_five_distinct_ips(self):
+        webshare_key = os.environ.get("WEBSHARE_API_KEY")
+        if not webshare_key:
+            self.skipTest(
+                "WEBSHARE_API_KEY is required for live proxy rotation E2E")
+
+        proxies = fetch_webshare_proxies(
+            api_key=webshare_key,
+            plan_id=os.environ.get("WEBSHARE_PLAN_ID") or 13345956,
+            http_get=requests.get,
+        )
+        print(f"\n[webshare-e2e] loaded {len(proxies)} proxies")
+        self.assertGreaterEqual(
+            len(proxies),
+            MIN_WEBSHARE_E2E_IPS,
+            f"expected at least {MIN_WEBSHARE_E2E_IPS} Webshare proxies",
+        )
+
+        pool = SyncRotationPool(proxies)
+        observed_ips: set[str] = set()
+        failures: list[str] = []
+        attempts = min(len(proxies), max(
+            MIN_WEBSHARE_E2E_IPS * 3, MIN_WEBSHARE_E2E_IPS))
+
+        for _ in range(attempts):
+            lease = pool.acquire()
+            self.assertIsNotNone(lease)
+            proxy = lease.item
+            try:
+                response = requests.get(
+                    WEBSHARE_IP_ECHO_URL,
+                    proxies=proxy.requests_proxies,
+                    timeout=20,
+                )
+                body_preview = _short_text(response.text)
+                print(
+                    f"[webshare-e2e] {proxy.label} -> "
+                    f"HTTP {response.status_code}, body={body_preview!r}"
+                )
+                response.raise_for_status()
+                observed_ip = body_preview
+                ipaddress.ip_address(observed_ip)
+                observed_ips.add(observed_ip)
+            except Exception as exc:
+                print(f"[webshare-e2e] {proxy.label} -> ERROR {exc}")
+                failures.append(f"{proxy.label}: {exc}")
+                pool.cooldown(lease.index, 60.0)
+            if len(observed_ips) >= MIN_WEBSHARE_E2E_IPS:
+                break
+
+        print(f"[webshare-e2e] distinct outbound IPs: {sorted(observed_ips)}")
+
+        self.assertGreaterEqual(
+            len(observed_ips),
+            MIN_WEBSHARE_E2E_IPS,
+            "expected at least five distinct outbound IPs via Webshare proxies; "
+            f"got {sorted(observed_ips)}; failures={failures[:5]}",
+        )
+
+    def test_fetch_all_prices_async_live_uses_webshare_key_ip_pairs(self):
+        pair_count = FETCHER_PROXY_E2E_PAIR_COUNT
+        csfloat_keys = _configured_csfloat_keys()
+        if len(csfloat_keys) < pair_count:
+            self.skipTest(
+                f"at least {pair_count} CSFloat keys are required for "
+                "one-to-one CSFloat key/IP proxy E2E; set CSFLOAT_API_KEYS"
+            )
+        webshare_key = os.environ.get("WEBSHARE_API_KEY")
+        if not webshare_key:
+            self.skipTest(
+                "WEBSHARE_API_KEY is required for live fetcher proxy E2E")
+
+        proxies = fetch_webshare_proxies(
+            api_key=webshare_key,
+            plan_id=os.environ.get("WEBSHARE_PLAN_ID") or 13345956,
+            http_get=requests.get,
+        )
+        self.assertGreaterEqual(
+            len(proxies),
+            pair_count,
+            f"expected at least {pair_count} Webshare proxies",
+        )
+        selected_proxies = tuple(proxies[:pair_count])
+        selected_keys = tuple(csfloat_keys[:pair_count])
+        selected_items = FETCHER_PROXY_E2E_ITEMS[:pair_count]
+        proxy_label_by_url = {
+            proxy.url: proxy.label for proxy in selected_proxies}
+        proxied_calls: list[tuple[str, str, int | None]] = []
+        print(
+            "\n[fetcher-proxy-e2e] selected proxies: "
+            f"{[proxy.label for proxy in selected_proxies]}"
+        )
+        print(
+            f"[fetcher-proxy-e2e] selected CSFloat keys: {len(selected_keys)}")
+        print(f"[fetcher-proxy-e2e] selected items: {len(selected_items)}")
+
+        original_proxy_endpoints = fetchers._proxy_endpoints
+        original_csfloat_api_keys = fetchers._csfloat_api_keys
+        original_async_json_request = fetchers._async_json_request
+
+        async def recording_async_json_request(session, url, **kwargs):
+            proxy_url = kwargs.get("proxy")
+            target = _fetcher_target_name(url)
+            proxy_label = proxy_label_by_url.get(proxy_url, "direct")
+            try:
+                status, data, text = await original_async_json_request(session, url, **kwargs)
+                proxied_calls.append((target, proxy_url or "", status))
+                print(
+                    f"[fetcher-proxy-e2e] {target} via {proxy_label} -> "
+                    f"HTTP {status}, body={_short_text(text)!r}"
+                )
+                return status, data, text
+            except Exception as exc:
+                proxied_calls.append((target, proxy_url or "", None))
+                print(
+                    f"[fetcher-proxy-e2e] {target} via {proxy_label} -> ERROR {exc}")
+                raise
+
+        try:
+            fetchers._proxy_endpoints = lambda: selected_proxies
+            fetchers._csfloat_api_keys = lambda: selected_keys
+            fetchers._async_json_request = recording_async_json_request
+            df = fetchers.fetch_all_prices(
+                selected_items,
+                steam_delay=0.25,
+                float_delay=0.25,
+                steam_concurrency=2,
+                float_concurrency=2,
+                use_async=True,
+            )
+        finally:
+            fetchers._proxy_endpoints = original_proxy_endpoints
+            fetchers._csfloat_api_keys = original_csfloat_api_keys
+            fetchers._async_json_request = original_async_json_request
+
+        used_proxy_urls = {proxy_url for _, proxy_url,
+                           _ in proxied_calls if proxy_url}
+        steam_proxy_urls = {
+            proxy_url for target, proxy_url, _ in proxied_calls if target == "Steam" and proxy_url
+        }
+        csfloat_proxy_urls = {
+            proxy_url for target, proxy_url, _ in proxied_calls if target == "CSFloat" and proxy_url
+        }
+        print(
+            "[fetcher-proxy-e2e] used proxy labels: "
+            f"{[proxy_label_by_url[url] for url in sorted(used_proxy_urls)]}"
+        )
+        print(f"[fetcher-proxy-e2e] dataframe rows: {len(df)}")
+
+        self.assertGreaterEqual(len(used_proxy_urls), pair_count)
+        self.assertGreaterEqual(len(steam_proxy_urls), pair_count)
+        self.assertGreaterEqual(len(csfloat_proxy_urls), pair_count)
+        self.assertFalse(df.empty)
+        for column in ("steam_ask", "float_ask", "float_pred", "spread_pred%"):
+            self.assertIn(column, df.columns)
+
+    def test_async_steam_only_live_uses_webshare_proxies(self):
+        pair_count = FETCHER_PROXY_E2E_PAIR_COUNT
+        webshare_key = os.environ.get("WEBSHARE_API_KEY")
+        if not webshare_key:
+            self.skipTest(
+                "WEBSHARE_API_KEY is required for live Steam proxy E2E")
+
+        proxies = fetch_webshare_proxies(
+            api_key=webshare_key,
+            plan_id=os.environ.get("WEBSHARE_PLAN_ID") or 13345956,
+            http_get=requests.get,
+        )
+        self.assertGreaterEqual(
+            len(proxies),
+            pair_count,
+            f"expected at least {pair_count} Webshare proxies",
+        )
+        selected_proxies = _steam_ok_proxies(proxies, pair_count)
+        self.assertGreaterEqual(
+            len(selected_proxies),
+            pair_count,
+            f"expected at least {pair_count} Webshare proxies that Steam accepts",
+        )
+        selected_items = FETCHER_PROXY_E2E_ITEMS[:pair_count]
+        proxy_label_by_url = {
+            proxy.url: proxy.label for proxy in selected_proxies}
+        proxied_calls: list[tuple[str, str, int | None]] = []
+        print(
+            "\n[steam-only-e2e] selected proxies: "
+            f"{[proxy.label for proxy in selected_proxies]}"
+        )
+        print(f"[steam-only-e2e] selected items: {len(selected_items)}")
+
+        original_async_json_request = fetchers._async_json_request
+
+        async def recording_async_json_request(session, url, **kwargs):
+            proxy_url = kwargs.get("proxy")
+            target = _fetcher_target_name(url)
+            proxy_label = proxy_label_by_url.get(proxy_url, "direct")
+            try:
+                status, data, text = await original_async_json_request(session, url, **kwargs)
+                proxied_calls.append((target, proxy_url or "", status))
+                print(
+                    f"[steam-only-e2e] {target} via {proxy_label} -> "
+                    f"HTTP {status}, body={_short_text(text)!r}"
+                )
+                return status, data, text
+            except Exception as exc:
+                proxied_calls.append((target, proxy_url or "", None))
+                print(
+                    f"[steam-only-e2e] {target} via {proxy_label} -> ERROR {exc}")
+                raise
+
+        async def run_steam_only():
+            limiter = fetchers._AsyncStartLimiter("STEAM_DELAY", 0.25)
+            semaphore = asyncio.Semaphore(2)
+            proxy_pool = AsyncRotationPool(selected_proxies)
+            async with fetchers._AsyncSessionPool() as sessions:
+                tasks = [
+                    asyncio.create_task(
+                        fetchers._async_get_steam_price(
+                            sessions,
+                            limiter,
+                            semaphore,
+                            proxy_pool,
+                            item,
+                            1,
+                        )
+                    )
+                    for item in selected_items
+                ]
+                return await asyncio.wait_for(
+                    asyncio.gather(*tasks, return_exceptions=True),
+                    timeout=STEAM_ONLY_E2E_TIMEOUT_SEC,
+                )
+
+        try:
+            fetchers._async_json_request = recording_async_json_request
+            try:
+                results = asyncio.run(run_steam_only())
+            except asyncio.TimeoutError:
+                self.fail(
+                    f"Steam-only proxy E2E timed out after {STEAM_ONLY_E2E_TIMEOUT_SEC:.0f}s; "
+                    f"calls={proxied_calls}"
+                )
+        finally:
+            fetchers._async_json_request = original_async_json_request
+
+        used_proxy_urls = {proxy_url for _, proxy_url,
+                           _ in proxied_calls if proxy_url}
+        steam_proxy_urls = {
+            proxy_url for target, proxy_url, _ in proxied_calls if target == "Steam" and proxy_url
+        }
+        non_steam_targets = {target for target, _,
+                             _ in proxied_calls if target != "Steam"}
+        print(
+            "[steam-only-e2e] used proxy labels: "
+            f"{[proxy_label_by_url[url] for url in sorted(used_proxy_urls)]}"
+        )
+        print(f"[steam-only-e2e] results: {results}")
+
+        self.assertEqual(non_steam_targets, set())
+        self.assertGreaterEqual(len(steam_proxy_urls), pair_count)
+        self.assertTrue(results)
+        for result in results:
+            self.assertIsInstance(result, float)
+
+
+def _fetcher_target_name(url: str) -> str:
+    if url == fetchers.STEAM_PRICEOVERVIEW_URL:
+        return "Steam"
+    if url == fetchers.CSFLOAT_LISTINGS_URL:
+        return "CSFloat"
+    return url
+
+
+def _steam_ok_proxies(proxies, count: int):
+    async def check():
+        ok = []
+        async with fetchers._AsyncSessionPool() as sessions:
+            for proxy in proxies:
+                try:
+                    status, data, text = await fetchers._async_json_request(
+                        sessions.for_proxy(proxy),
+                        fetchers.STEAM_PRICEOVERVIEW_URL,
+                        params={
+                            "appid": 730,
+                            "currency": 1,
+                            "market_hash_name": FETCHER_PROXY_E2E_ITEMS[0],
+                        },
+                        headers=fetchers._http_headers(),
+                        proxy=proxy.url,
+                        timeout_sec=15,
+                    )
+                    print(
+                        f"[steam-only-e2e] precheck {proxy.label} -> "
+                        f"HTTP {status}, body={_short_text(text)!r}"
+                    )
+                    if status == 200 and isinstance(data, dict) and data.get("success"):
+                        ok.append(proxy)
+                        if len(ok) >= count:
+                            break
+                except Exception as exc:
+                    print(f"[steam-only-e2e] precheck {proxy.label} -> ERROR {exc}")
+        return tuple(ok)
+
+    return asyncio.run(check())
+
+
+def _configured_csfloat_keys() -> tuple[str, ...]:
+    return fetchers._csfloat_api_keys()
+
+
+if __name__ == "__main__":
+    unittest.main()
diff --git a/tests/test_proxy_rotation.py b/tests/test_proxy_rotation.py
new file mode 100644
index 0000000..7d5df17
--- /dev/null
+++ b/tests/test_proxy_rotation.py
@@ -0,0 +1,88 @@
+from __future__ import annotations
+
+import asyncio
+import unittest
+
+from base_screening_and_anal.proxy_rotation import (
+    AsyncRotationPool,
+    SyncRotationPool,
+    fetch_webshare_proxies,
+    parse_proxy_entries,
+)
+
+
+class FakeResponse:
+    def __init__(self, *, json_data=None, text=""):
+        self._json_data = json_data
+        self.text = text
+
+    def json(self):
+        return self._json_data
+
+    def raise_for_status(self):
+        return None
+
+
+class ProxyRotationTests(unittest.TestCase):
+    def test_parse_webshare_proxy_lines(self):
+        proxies = parse_proxy_entries(
+            "10.0.0.1:8000:user-a:pass-a\r\n"
+            "10.0.0.2:9000:user-b:pass-b\r\n"
+        )
+
+        self.assertEqual(len(proxies), 2)
+        self.assertEqual(proxies[0].url, "http://user-a:pass-a@10.0.0.1:8000")
+        self.assertEqual(proxies[0].label, "1:10.0.0.1:8000")
+        self.assertEqual(
+            proxies[1].requests_proxies,
+            {
+                "http": "http://user-b:pass-b@10.0.0.2:9000",
+                "https": "http://user-b:pass-b@10.0.0.2:9000",
+            },
+        )
+
+    def test_fetch_webshare_proxies_uses_config_then_download(self):
+        calls = []
+
+        def fake_get(url, **kwargs):
+            calls.append({"url": url, **kwargs})
+            if url.endswith("/proxy/config"):
+                return FakeResponse(json_data={"proxy_list_download_token": "download-token"})
+            return FakeResponse(text="10.0.0.3:7000:user-c:pass-c\r\n")
+
+        proxies = fetch_webshare_proxies(
+            api_key="webshare-token",
+            plan_id=13345956,
+            http_get=fake_get,
+        )
+
+        self.assertEqual(proxies[0].url, "http://user-c:pass-c@10.0.0.3:7000")
+        self.assertEqual(calls[0]["headers"]["Authorization"], "Token webshare-token")
+        self.assertEqual(calls[0]["params"]["plan_id"], 13345956)
+        self.assertIn("/download/download-token/", calls[1]["url"])
+
+    def test_sync_rotation_pool_skips_cooled_down_item(self):
+        pool = SyncRotationPool(("ip-a", "ip-b"))
+
+        first = pool.acquire()
+        pool.cooldown(first.index, 60.0)
+        second = pool.acquire()
+
+        self.assertEqual(first.item, "ip-a")
+        self.assertEqual(second.item, "ip-b")
+
+
+class AsyncProxyRotationTests(unittest.IsolatedAsyncioTestCase):
+    async def test_async_rotation_pool_skips_cooled_down_item(self):
+        pool = AsyncRotationPool(("pair-a", "pair-b"))
+
+        first = await pool.acquire()
+        await pool.cooldown(first.index, 60.0)
+        second = await pool.acquire()
+
+        self.assertEqual(first.item, "pair-a")
+        self.assertEqual(second.item, "pair-b")
+
+
+if __name__ == "__main__":
+    unittest.main()
