from __future__ import annotations

import base64
import hashlib
import json
import os
import random
import re
import signal
import string
import subprocess
import threading
import time
import urllib.parse
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from typing import Any, Callable

import requests
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait
from seleniumbase import Driver as create_driver

from . import PROJECT_ROOT as _PROJECT_ROOT
from .mail import Mailbox, MailError, MailProvider
from .codex_switcher import CLIENT_ID, decode_jwt_payload

LOGIN_URL = "https://chatgpt.com/auth/login_with"

_FIRST_NAMES = [
    "Alex", "Jordan", "Taylor", "Morgan", "Casey", "Riley", "Jamie",
    "Avery", "Quinn", "Blake", "Drew", "Sage", "River", "Skyler",
]
_LAST_NAMES = [
    "Smith", "Johnson", "Williams", "Brown", "Jones", "Davis",
    "Miller", "Wilson", "Moore", "Taylor", "Anderson", "Thomas",
]


def _human_delay(lo: float = 0.3, hi: float = 0.8) -> None:
    """Случайная пауза, имитирующая человека."""
    time.sleep(random.uniform(lo, hi))


def _human_type(driver: Any, selector: str, text: str) -> None:
    """Посимвольный ввод текста с человеческими задержками."""
    elem = WebDriverWait(driver, 30).until(
        EC.presence_of_element_located((By.CSS_SELECTOR, selector))
    )
    try:
        elem.clear()
    except Exception:
        pass
    for ch in text:
        elem.send_keys(ch)
        time.sleep(random.uniform(0.04, 0.12))
    _human_delay(0.2, 0.5)


class Locator:
    def __init__(self, driver: Any, selector: str) -> None:
        self._driver = driver
        self._selector = selector

    def count(self) -> int:
        return len(self._driver.find_elements(By.CSS_SELECTOR, self._selector))

    def fill(self, value: str) -> None:
        elem = WebDriverWait(self._driver, 30).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, self._selector))
        )
        try:
            elem.clear()
        except Exception:
            pass
        elem.send_keys(value)

    def click(self) -> None:
        elem = WebDriverWait(self._driver, 30).until(
            EC.element_to_be_clickable((By.CSS_SELECTOR, self._selector))
        )
        try:
            elem.click()
        except Exception:
            self._driver.execute_script("arguments[0].click();", elem)

    def get_attribute(self, name: str) -> str | None:
        elems = self._driver.find_elements(By.CSS_SELECTOR, self._selector)
        if not elems:
            return None
        return elems[0].get_attribute(name)


class Keyboard:
    _KEY_MAP = {
        "ArrowUp": Keys.ARROW_UP,
        "ArrowDown": Keys.ARROW_DOWN,
        "ArrowLeft": Keys.ARROW_LEFT,
        "ArrowRight": Keys.ARROW_RIGHT,
        "Enter": Keys.ENTER,
        "Tab": Keys.TAB,
        "Escape": Keys.ESCAPE,
        "Backspace": Keys.BACKSPACE,
    }

    def __init__(self, driver: Any) -> None:
        self._driver = driver

    def press(self, key: str) -> None:
        active = self._driver.switch_to.active_element
        active.send_keys(self._KEY_MAP.get(key, key))


class BrowserContext:
    def __init__(self, driver: Any, profile_dir: Path | None = None) -> None:
        self.driver = driver
        self._closed = False
        self._profile_dir = profile_dir
        self.page = Page(driver, self)

    @property
    def pages(self) -> list["Page"]:
        if self._closed:
            return []
        try:
            _ = self.driver.current_url
            return [self.page]
        except Exception:
            return []

    def close(self) -> None:
        if self._closed:
            return
        try:
            self.driver.quit()
        except Exception:
            if self._profile_dir:
                _kill_chrome_for_profile(self._profile_dir)
        finally:
            self._closed = True


class Page:
    def __init__(self, driver: Any, context: BrowserContext) -> None:
        self._driver = driver
        self.context = context
        self.keyboard = Keyboard(driver)

    @property
    def url(self) -> str:
        try:
            current_url = self._driver.current_url
            if current_url.startswith("chrome://") or current_url in {"about:blank", "data:,"}:
                _activate_best_tab(self._driver)
                current_url = self._driver.current_url
            return current_url
        except Exception:
            return ""

    def goto(self, url: str, wait_until: str | None = None, timeout: int | None = None) -> None:
        self._driver.get(url)
        _activate_best_tab(self._driver, [url, urllib.parse.urlparse(url).netloc])
        if wait_until in {"domcontentloaded", "load"}:
            t = (timeout or 30000) / 1000
            WebDriverWait(self._driver, t).until(
                lambda d: d.execute_script("return document.readyState") in {"interactive", "complete"}
            )

    def locator(self, selector: str) -> Locator:
        return Locator(self._driver, selector)

    def wait_for_selector(self, selector: str, timeout: int = 30000) -> None:
        WebDriverWait(self._driver, timeout / 1000).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, selector))
        )

    def wait_for_url(self, predicate: Callable[[str], bool], timeout: int = 30000) -> None:
        deadline = time.monotonic() + timeout / 1000
        while time.monotonic() < deadline:
            cur = self.url
            if predicate(cur):
                return
            time.sleep(0.2)
        raise TimeoutError(f"URL не достигнут за {timeout}мс")

    def evaluate(self, script: str, args: Any = None) -> Any:
        result = self._driver.execute_async_script(
            """
const done = arguments[arguments.length - 1];
const source = arguments[0];
const payload = arguments[1];
(async () => {
  try {
    const fn = eval(source);
    const out = (typeof fn === 'function') ? await fn(payload) : fn;
    done({ ok: true, out });
  } catch (e) {
    done({ ok: false, err: String(e && e.stack ? e.stack : e) });
  }
})();
""",
            script,
            args,
        )
        if not result or not result.get("ok"):
            err = result.get("err") if isinstance(result, dict) else "evaluate failed"
            raise RuntimeError(str(err))
        return result.get("out")


_open_contexts: list[BrowserContext] = []

_DEBUG_DIR = _PROJECT_ROOT / "logs" / "debug"


def _save_debug_html(
    page: Page,
    label: str,
    log: Callable[[str], Any] | None = None,
) -> Path | None:
    """Сохранить HTML страницы и скриншот для отладки."""
    try:
        _DEBUG_DIR.mkdir(parents=True, exist_ok=True)
        ts = datetime.now().strftime("%Y%m%d-%H%M%S")
        safe_label = re.sub(r'[^\w\-.]', '_', label)[:80]
        base = f"{ts}-{safe_label}"

        # HTML
        html = page._driver.page_source
        html_path = _DEBUG_DIR / f"{base}.html"
        html_path.write_text(html, encoding="utf-8")

        # Скриншот (png)
        try:
            png_path = _DEBUG_DIR / f"{base}.png"
            page._driver.save_screenshot(str(png_path))
        except Exception:
            png_path = None

        if log:
            files = str(html_path.name)
            if png_path:
                files += f", {png_path.name}"
            log(f"[debug] Сохранено: {files}")
        return html_path
    except Exception as e:
        if log:
            log(f"[debug] Не удалось сохранить: {e}")
        return None


def extract_code_from_subject(subject: str) -> str | None:
    match = re.search(r"\b(\d{6})\b", subject)
    return match.group(1) if match else None


def poll_for_code(
    mail_client: MailProvider,
    mailbox: Mailbox,
    existing_ids: set[str],
    timeout: int = 60,
    interval: int = 5,
    log: Callable[[str], Any] | None = None,
) -> str:
    _log = log or print
    elapsed = 0
    while elapsed < timeout:
        inbox = mail_client.inbox(mailbox)
        for msg in inbox.messages:
            if msg.id in existing_ids:
                continue
            code = extract_code_from_subject(msg.subject)
            if code:
                _log(f"Получен код: {code} (из: {msg.subject})")
                return code
        _log(f"Ожидание кода... ({elapsed}/{timeout} сек)")
        time.sleep(interval)
        elapsed += interval
    raise TimeoutError(f"Код не получен за {timeout} секунд")


def make_openai_password(mail_password: str, min_len: int = 13) -> str:
    pwd = mail_password
    if len(pwd) < min_len:
        pad = string.ascii_letters + string.digits
        pwd += "".join(random.choices(pad, k=min_len - len(pwd)))
    return pwd


def _random_name() -> str:
    return f"{random.choice(_FIRST_NAMES)} {random.choice(_LAST_NAMES)}"


def _random_birthday() -> tuple[str, str, str]:
    year = random.randint(1990, 2004)
    month = random.randint(1, 12)
    day = random.randint(1, 28)
    return str(day).zfill(2), str(month).zfill(2), str(year)


def _check_birthday_values(page: Page) -> dict[str, str]:
    return page.evaluate(
        """() => {
            const d = document.querySelector('[data-type="day"][role="spinbutton"]');
            const m = document.querySelector('[data-type="month"][role="spinbutton"]');
            const y = document.querySelector('[data-type="year"][role="spinbutton"]');
            return {
                day: d ? d.textContent || d.innerText || '' : '',
                month: m ? m.textContent || m.innerText || '' : '',
                year: y ? y.textContent || y.innerText || '' : '',
            };
        }"""
    )


def _birthday_ok(values: dict[str, str]) -> bool:
    y = values.get("year", "")
    m = values.get("month", "")
    d = values.get("day", "")
    return (
        len(y) == 4 and y.isdigit()
        and len(m) <= 2 and m.isdigit()
        and len(d) <= 2 and d.isdigit()
    )


def _fill_birthday(
    page: Page, day: str, month: str, year: str, log: Callable[[str], Any],
) -> None:
    """Заполнить дату рождения на странице регистрации OpenAI."""
    has_spinbuttons = page.locator('[role="spinbutton"]').count() > 0
    if not has_spinbuttons:
        log("[предупреждение] Spinbutton-элементы даты не найдены")
        for sel_type, val in [("day", day), ("month", month), ("year", year)]:
            for sel in (f'input[name="{sel_type}"]', f'input[placeholder*="{sel_type}"]'):
                if page.locator(sel).count() > 0:
                    page.locator(sel).fill(val)
                    break
        return

    day_sel = '[data-type="day"][role="spinbutton"]'
    month_sel = '[data-type="month"][role="spinbutton"]'
    year_sel = '[data-type="year"][role="spinbutton"]'

    # Стратегия 1: beforeinput events (надёжно работает в headless)
    for sel, digits in [(day_sel, day), (month_sel, month), (year_sel, year)]:
        if page.locator(sel).count() == 0:
            continue
        page.locator(sel).click()
        _human_delay(0.15, 0.35)
        for ch in digits:
            page.evaluate(
                """(args) => {
                    const el = document.querySelector(args.sel);
                    if (!el) return;
                    el.dispatchEvent(new InputEvent('beforeinput', {
                        cancelable: true, data: args.ch,
                        inputType: 'insertText', bubbles: true
                    }));
                }""",
                {"sel": sel, "ch": ch},
            )
            _human_delay(0.06, 0.15)
        _human_delay(0.2, 0.5)

    values = _check_birthday_values(page)
    log(f"Дата (beforeinput): day={values.get('day')}, month={values.get('month')}, year={values.get('year')}")
    if _birthday_ok(values):
        return

    # Стратегия 2: полная JS-имитация (focus + keydown/beforeinput/input/keyup)
    log("beforeinput не сработал, пробую JS fallback...")
    page.evaluate(
        """(args) => {
            function fillSpin(sel, value) {
                const el = document.querySelector(sel);
                if (!el) return;
                el.focus();
                for (const ch of String(value)) {
                    const opts = { key: ch, code: 'Digit' + ch, bubbles: true, cancelable: true };
                    el.dispatchEvent(new KeyboardEvent('keydown', opts));
                    el.dispatchEvent(new InputEvent('beforeinput', {
                        data: ch, inputType: 'insertText', bubbles: true, cancelable: true
                    }));
                    el.dispatchEvent(new InputEvent('input', {
                        data: ch, inputType: 'insertText', bubbles: true
                    }));
                    el.dispatchEvent(new KeyboardEvent('keyup', opts));
                }
            }
            fillSpin('[data-type="day"][role="spinbutton"]', args.day);
            fillSpin('[data-type="month"][role="spinbutton"]', args.month);
            fillSpin('[data-type="year"][role="spinbutton"]', args.year);
        }""",
        {"day": day, "month": month, "year": year},
    )
    time.sleep(0.5)

    values = _check_birthday_values(page)
    log(f"Дата (JS fallback): day={values.get('day')}, month={values.get('month')}, year={values.get('year')}")


def _wait_fieldset_enabled(page: Page, log: Callable[[str], Any], timeout: int = 30) -> None:
    """Ждём пока <fieldset disabled> на about-you станет enabled (Sentinel антибот)."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        disabled = page.evaluate(
            """() => {
                const fs = document.querySelector('fieldset');
                return fs ? fs.disabled : false;
            }"""
        )
        if not disabled:
            return
        time.sleep(0.5)

    log("[предупреждение] fieldset остаётся disabled — снимаю принудительно")
    page.evaluate(
        """() => {
            document.querySelectorAll('fieldset[disabled]').forEach(fs => {
                fs.removeAttribute('disabled');
            });
        }"""
    )
    time.sleep(0.3)


def _submit_about_you_form(page: Page, log: Callable[[str], Any]) -> None:
    """Отправить форму about-you. Если кнопка не кликается — submit через JS."""
    try:
        page.locator('button[type="submit"]').click()
    except Exception:
        log("[предупреждение] Кнопка submit не кликается, отправляю через JS")
        page.evaluate(
            """() => {
                const form = document.querySelector('form[action="/about-you"]');
                if (form) {
                    form.requestSubmit();
                } else {
                    const btn = document.querySelector('button[type="submit"]');
                    if (btn) btn.click();
                }
            }"""
        )


def _is_oops_error(page: Page) -> bool:
    """Проверить, показывается ли страница 'Oops, an error occurred!'."""
    try:
        return page.locator('button[data-dd-action-name="Try again"]').count() > 0
    except Exception:
        return False


def _handle_oops_retry(
    page: Page, log: Callable[[str], Any], max_retries: int = 3,
) -> bool:
    """Если на странице 'Oops' — нажать 'Try again' до max_retries раз. True = удалось уйти."""
    for attempt in range(1, max_retries + 1):
        if not _is_oops_error(page):
            return True
        log(f"[oops] Обнаружена ошибка 'Oops', нажимаю Try again ({attempt}/{max_retries})...")
        _save_debug_html(page, f"oops-error-attempt-{attempt}", log)
        try:
            page.locator('button[data-dd-action-name="Try again"]').click()
        except Exception:
            pass
        time.sleep(5)
    return not _is_oops_error(page)


def extract_invite_link(body: str) -> str | None:
    match = re.search(r'href="(https://chatgpt\.com/auth/login\?[^"]+)"', body)
    if match:
        return match.group(1)
    match = re.search(r'(https://chatgpt\.com/auth/login\?[^\s<>"\']+)', body)
    return match.group(1) if match else None


def poll_for_invite(
    mail_client: MailProvider,
    mailbox: Mailbox,
    existing_ids: set[str],
    timeout: int = 90,
    interval: int = 5,
    log: Callable[[str], Any] | None = None,
) -> str:
    _log = log or print
    elapsed = 0
    while elapsed < timeout:
        inbox = mail_client.inbox(mailbox)
        for msg in inbox.messages:
            if msg.id in existing_ids:
                continue
            link = extract_invite_link(msg.body)
            if link:
                _log("Инвайт-ссылка получена")
                return link
        _log(f"Ожидание инвайта... ({elapsed}/{timeout} сек)")
        time.sleep(interval)
        elapsed += interval
    raise TimeoutError(f"Инвайт не получен за {timeout} секунд")


def _kill_chrome_for_profile(profile_dir: Path) -> None:
    """Kill any Chrome/uc_driver processes that hold this profile directory."""
    resolved = str(profile_dir.resolve())
    killed = False
    try:
        if os.name == "nt":
            # Windows: use PowerShell Get-CimInstance (wmic removed on newer Win11)
            ps_cmd = (
                "Get-CimInstance Win32_Process -Filter \"name like '%chrome%'\" | "
                "ForEach-Object { \"$($_.ProcessId)|$($_.CommandLine)\" }"
            )
            out = subprocess.check_output(
                ["powershell", "-NoProfile", "-Command", ps_cmd],
                text=True, timeout=15,
            )
            resolved_win = resolved.replace("/", "\\")
            for line in out.splitlines():
                line = line.strip()
                if "|" not in line:
                    continue
                pid_str, cmdline = line.split("|", 1)
                if resolved_win not in cmdline and resolved not in cmdline:
                    continue
                try:
                    pid = int(pid_str.strip())
                    if pid == os.getpid():
                        continue
                    subprocess.run(["taskkill", "/F", "/PID", str(pid)], timeout=5,
                                   capture_output=True)
                    killed = True
                except (ValueError, OSError):
                    pass
        else:
            out = subprocess.check_output(["ps", "aux"], text=True, timeout=5)
            for line in out.splitlines():
                if resolved not in line:
                    continue
                parts = line.split()
                if len(parts) < 2:
                    continue
                try:
                    pid = int(parts[1])
                    if pid == os.getpid():
                        continue
                    os.kill(pid, signal.SIGTERM)
                    killed = True
                except (ValueError, ProcessLookupError, PermissionError):
                    pass
    except Exception:
        pass
    if killed:
        time.sleep(2)
    # Remove stale Chrome lock files so the profile can be reused
    for name in ("SingletonLock", "SingletonCookie", "SingletonSocket"):
        lock = profile_dir / name
        try:
            lock.unlink(missing_ok=True)
        except OSError:
            pass


def _launch_page(profile_dir: Path, headless: bool = False) -> tuple[Page, BrowserContext]:
    profile_dir.parent.mkdir(parents=True, exist_ok=True)
    if profile_dir.exists():
        try:
            next(profile_dir.iterdir())
        except StopIteration:
            profile_dir.rmdir()
    _kill_chrome_for_profile(profile_dir)
    _MOBILE_UA = (
        "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) "
        "AppleWebKit/605.1.15 (KHTML, like Gecko) "
        "Version/17.0 Mobile/15E148 Safari/604.1"
    )
    driver = create_driver(
        browser="chrome",
        headed=not headless,
        uc=True,
        headless2=headless,
        user_data_dir=str(profile_dir.resolve()),
        locale_code="en",
        mobile=True,
        d_width=393,
        d_height=852,
        d_p_r=3,
    )
    driver.set_script_timeout(60)

    # UC mode применяет setDeviceMetricsOverride внутри driver.get(),
    # но User-Agent и touch нужно выставить отдельно — CDP-команды
    # для UA и touch сохраняются между навигациями.
    try:
        driver.execute_cdp_cmd("Emulation.setUserAgentOverride", {
            "userAgent": _MOBILE_UA,
        })
        driver.execute_cdp_cmd("Emulation.setTouchEmulationEnabled", {
            "enabled": True,
        })
    except Exception:
        pass

    # SeleniumBase UC mode перехватывает driver.get() и внутри вызывает driver.close()
    # для антидетекта. Если в браузере только 1 таб — Chrome зависает на
    # "failed to close window in 20 seconds". Гарантируем наличие 2+ табов.
    try:
        handles = list(driver.window_handles)
        primary_handle = driver.current_window_handle
        # Переключиться на основной (не chrome://) таб
        if len(handles) > 1:
            for h in handles:
                driver.switch_to.window(h)
                if not driver.current_url.startswith("chrome://"):
                    primary_handle = h
                    break
        # Если только 1 таб — открыть второй пустой для UC mode
        if len(driver.window_handles) < 2:
            driver.execute_script("window.open('about:blank')")
        driver.switch_to.window(primary_handle)
    except Exception:
        pass

    context = BrowserContext(driver, profile_dir=profile_dir)
    _open_contexts.append(context)
    return context.page, context


def _wait_for_any(
    page: Page,
    selectors: list[str],
    url_contains: list[str] | None = None,
    url_excludes: list[str] | None = None,
    timeout: int = 30000,
) -> str:
    interval_ms = 500
    elapsed = 0
    while elapsed < timeout:
        try:
            current_url = page.url
            for substr in (url_contains or []):
                if substr in current_url and not any(exc in current_url for exc in (url_excludes or [])):
                    return "url"
            for sel in selectors:
                if page.locator(sel).count() > 0:
                    return sel
        except Exception:
            pass
        time.sleep(interval_ms / 1000)
        elapsed += interval_ms
    raise TimeoutError(f"Таймаут {timeout}мс: ни один селектор/URL не сработал")


def close_browser(page: Page, log: Callable[[str], Any] | None = None) -> None:
    _log = log or print
    try:
        context = page.context
        context.close()
        _open_contexts[:] = [c for c in _open_contexts if c != context]
        _log("Браузер закрыт")
    except Exception as e:
        _log(f"Ошибка при закрытии браузера: {e}")


def open_browser(
    profile_dir: Path,
    url: str = "https://chatgpt.com/",
    log: Callable[[str], Any] | None = None,
    headless: bool = False,
) -> tuple[Page, BrowserContext]:
    _log = log or print
    _log("Открываю браузер...")
    _log(f"Chrome profile: {profile_dir}")
    page, context = _launch_page(profile_dir, headless=headless)
    driver = context.driver

    _log(f"Открываю {url}...")
    driver.get(url)
    _activate_best_tab(driver, [url, urllib.parse.urlparse(url).netloc])

    WebDriverWait(driver, 30).until(
        lambda d: d.execute_script("return document.readyState") in {"interactive", "complete"}
    )

    # Oops fallback
    if _is_oops_error(page):
        _handle_oops_retry(page, _log)

    _log(f"Браузер открыт: {page.url}")
    return page, context


def wait_for_browser_close(context: BrowserContext, log: Callable[[str], Any] | None = None) -> None:
    _log = log or print
    while True:
        pages = context.pages
        if not pages:
            break
        time.sleep(1)
    context.close()
    _open_contexts[:] = [c for c in _open_contexts if c != context]
    _log("Браузер закрыт")



def _activate_best_tab(driver: Any, preferred_url_parts: list[str] | None = None) -> None:
    preferred = [part for part in (preferred_url_parts or []) if part]

    try:
        handles = list(driver.window_handles)
    except Exception:
        return

    best_handle: str | None = None
    fallback_handle: str | None = None

    for handle in handles:
        try:
            driver.switch_to.window(handle)
            current_url = (driver.current_url or "").strip()
        except Exception:
            continue

        if not current_url.startswith("chrome://") and fallback_handle is None:
            fallback_handle = handle

        if any(part in current_url for part in preferred):
            best_handle = handle
            break

        if current_url and current_url not in {"about:blank", "data:,"}:
            best_handle = handle

    target = best_handle or fallback_handle
    if target:
        try:
            driver.switch_to.window(target)
        except Exception:
            pass


def _start_callback_server(state: str) -> tuple[HTTPServer, str, dict[str, str | None]]:
    holder: dict[str, str | None] = {"code": None, "error": None}

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:  # noqa: N802
            parsed = urllib.parse.urlparse(self.path)
            if parsed.path != "/auth/callback":
                self.send_response(404)
                self.end_headers()
                return

            query = urllib.parse.parse_qs(parsed.query)
            code = (query.get("code") or [""])[0]
            recv_state = (query.get("state") or [""])[0]
            error = (query.get("error") or [""])[0]

            if error:
                holder["error"] = f"OAuth error: {error}"
            elif recv_state != state:
                holder["error"] = "State mismatch"
            elif code:
                holder["code"] = code

            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write("<html><body><h2>OK! Можно закрыть вкладку.</h2></body></html>".encode("utf-8"))

        def log_message(self, format: str, *args: object) -> None:  # noqa: A003
            return

    server: HTTPServer | None = None
    port = 1455
    for candidate in (1455, 1456):
        try:
            server = HTTPServer(("127.0.0.1", candidate), Handler)
            port = candidate
            break
        except OSError:
            continue

    if server is None:
        raise RuntimeError("Не удалось поднять callback-сервер на портах 1455/1456")

    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server, f"http://localhost:{port}/auth/callback", holder


def _wait_for_callback(holder: dict[str, str | None], timeout: int = 120) -> str:
    deadline = time.time() + timeout
    while time.time() < deadline:
        if holder.get("error"):
            raise RuntimeError(holder["error"] or "OAuth callback error")
        if holder.get("code"):
            return holder["code"] or ""
        time.sleep(0.2)
    raise TimeoutError("Не удалось получить authorization code")


def _handle_consent_and_wait(page: Page, log: Callable[[str], Any], callback_wait_seconds: int = 30) -> None:
    deadline = time.time() + callback_wait_seconds
    while time.time() < deadline:
        url = page.url
        if "localhost" in url:
            return
        if "consent" in url and page.locator('button[type="submit"]').count() > 0:
            log("Страница consent — нажимаю 'Продолжить'...")
            page.locator('button[type="submit"]').click()
        time.sleep(1)


def _prepare_oauth_authorize_url() -> tuple[str, HTTPServer, dict[str, str | None], str, str]:
    code_verifier = base64.urlsafe_b64encode(os.urandom(96)).rstrip(b"=").decode()
    code_challenge = base64.urlsafe_b64encode(hashlib.sha256(code_verifier.encode()).digest()).rstrip(b"=").decode()
    state = os.urandom(16).hex()

    server, redirect_uri, holder = _start_callback_server(state)
    params = urllib.parse.urlencode({
        "client_id": CLIENT_ID,
        "response_type": "code",
        "redirect_uri": redirect_uri,
        "scope": "openid email profile offline_access",
        "state": state,
        "code_challenge": code_challenge,
        "code_challenge_method": "S256",
        "prompt": "login",
        "id_token_add_organizations": "true",
        "codex_cli_simplified_flow": "true",
    })
    authorize_url = f"https://auth.openai.com/oauth/authorize?{params}"
    return authorize_url, server, holder, redirect_uri, code_verifier


def _exchange_oauth_code(auth_code: str, redirect_uri: str, code_verifier: str) -> dict[str, Any]:
    token_data = {
        "grant_type": "authorization_code",
        "client_id": CLIENT_ID,
        "code": auth_code,
        "redirect_uri": redirect_uri,
        "code_verifier": code_verifier,
    }
    resp = requests.post(
        "https://auth.openai.com/oauth/token",
        data=token_data,
        headers={"Content-Type": "application/x-www-form-urlencoded", "Accept": "application/json"},
        timeout=30,
    )
    if resp.status_code != 200:
        raise RuntimeError(f"Token exchange failed [{resp.status_code}]: {resp.text[:200]}")

    tokens = resp.json()
    access_token = tokens.get("access_token", "")
    id_token = tokens.get("id_token", "")
    refresh_token = tokens.get("refresh_token", "")
    expires_in = tokens.get("expires_in", 0)

    session_result: dict[str, Any] = {
        "access_token": access_token,
        "id_token": id_token,
        "refresh_token": refresh_token,
    }

    jwt_data = decode_jwt_payload(id_token or access_token)
    if jwt_data:
        auth_info = jwt_data.get("https://api.openai.com/auth", {})
        session_result["account_id"] = auth_info.get("chatgpt_account_id")
        profile = jwt_data.get("https://api.openai.com/profile", {})
        session_result["email"] = profile.get("email") or jwt_data.get("email")
        exp = jwt_data.get("exp")
        if exp:
            session_result["expired"] = datetime.fromtimestamp(exp, tz=timezone.utc).isoformat()
        elif expires_in:
            session_result["expired"] = (datetime.now(timezone.utc) + timedelta(seconds=expires_in)).isoformat()

    return session_result


def _has_chatgpt_web_session(page: Page) -> bool:
    result = page.evaluate(
        """async () => {
            try {
                const resp = await fetch("https://chatgpt.com/api/auth/session", {
                    credentials: "include",
                    cache: "no-store",
                });
                const text = await resp.text();
                return { status: resp.status, text };
            } catch (e) {
                return { status: 0, text: String(e) };
            }
        }"""
    )

    if not isinstance(result, dict):
        return False
    if result.get("status") != 200:
        return False

    text = str(result.get("text", ""))
    return "\"accessToken\"" in text or "\"user\"" in text


def _bootstrap_chatgpt_session(
    page: Page,
    log: Callable[[str], Any],
    *,
    timeout_seconds: int = 45,
    interactive: bool = False,
) -> None:
    last_error = ""
    auth_prompt_logged = False
    consent_logged = False
    workspace_logged = False

    if interactive:
        try:
            log("Открываю chatgpt.com для web-сессии...")
            page.goto("https://chatgpt.com/", wait_until="domcontentloaded", timeout=30000)
        except Exception as e:
            last_error = str(e)

        deadline = time.time() + timeout_seconds
        while time.time() < deadline:
            try:
                current_url = page.url
                if "localhost" in current_url:
                    time.sleep(1)
                    continue
                if _has_chatgpt_web_session(page):
                    log("Web-сессия chatgpt.com активна")
                    time.sleep(3)
                    return
                if "/auth/" not in current_url and page.locator('button[name="workspace_id"]').count() > 0:
                    if not workspace_logged:
                        log("Открыт выбор workspace. Финальную web-сессию подтвержу после выбора workspace.")
                        workspace_logged = True
                    time.sleep(3)
                    return
                if ("/auth/" in current_url or "auth.openai.com" in current_url) and not auth_prompt_logged:
                    log("Нужен второй вход для web-сессии chatgpt.com. Завершите его вручную в этом же окне, я подожду.")
                    auth_prompt_logged = True
                if "consent" in current_url and page.locator('button[type="submit"]').count() > 0:
                    if not consent_logged:
                        log("Обнаружен consent для web-сессии, можно подтвердить его в браузере.")
                        consent_logged = True
            except Exception as e:
                last_error = str(e)
            time.sleep(1)

        if last_error:
            log(f"[предупреждение] Не удалось подтвердить web-сессию: {last_error}")
        else:
            log("[предупреждение] Не удалось подтвердить web-сессию chatgpt.com")
        return

    for url in (LOGIN_URL, "https://chatgpt.com/"):
        try:
            log(f"Закрепляю web-сессию: {url}")
            page.goto(url, wait_until="domcontentloaded", timeout=30000)
        except Exception as e:
            last_error = str(e)
            continue

        deadline = time.time() + timeout_seconds
        while time.time() < deadline:
            try:
                current_url = page.url
                if "localhost" in current_url:
                    time.sleep(1)
                    continue
                if _has_chatgpt_web_session(page):
                    log("Web-сессия chatgpt.com активна")
                    time.sleep(3)
                    return
                if "/auth/" not in current_url and page.locator('button[name="workspace_id"]').count() > 0:
                    if not workspace_logged:
                        log("Открыт выбор workspace. Финальную web-сессию подтвержу после выбора workspace.")
                        workspace_logged = True
                    time.sleep(3)
                    return
            except Exception as e:
                last_error = str(e)
            time.sleep(1)

    if last_error:
        log(f"[предупреждение] Не удалось подтвердить web-сессию: {last_error}")
    else:
        log("[предупреждение] Не удалось подтвердить web-сессию chatgpt.com")


def ensure_chatgpt_web_session(
    page: Page,
    log: Callable[[str], Any],
    *,
    timeout_seconds: int = 45,
    open_home: bool = False,
) -> bool:
    last_error = ""
    if open_home:
        try:
            log("Проверяю финальную web-сессию на chatgpt.com...")
            page.goto("https://chatgpt.com/", wait_until="domcontentloaded", timeout=30000)
        except Exception as e:
            last_error = str(e)

    deadline = time.time() + timeout_seconds
    while time.time() < deadline:
        try:
            current_url = page.url
            if "localhost" in current_url:
                time.sleep(1)
                continue
            if _has_chatgpt_web_session(page):
                log("Финальная web-сессия chatgpt.com подтверждена")
                time.sleep(2)
                return True
        except Exception as e:
            last_error = str(e)
        time.sleep(1)

    if last_error:
        log(f"[предупреждение] Финальная web-сессия не подтверждена: {last_error}")
    else:
        log("[предупреждение] Финальная web-сессия chatgpt.com не подтверждена")
    return False


def oauth_login(
    email: str,
    password: str,
    mail_client: MailProvider,
    mailbox: Mailbox,
    profile_dir: Path,
    log: Callable[[str], Any] | None = None,
    headless: bool = False,
) -> tuple[Page, dict]:
    _log = log or print

    _log("Открываю браузер...")
    page, _context = _launch_page(profile_dir, headless=headless)

    existing_ids: set[str] = set()
    try:
        inbox = mail_client.inbox(mailbox)
        existing_ids = {msg.id for msg in inbox.messages}
        _log(f"В почте {len(existing_ids)} писем, игнорируем их")
    except MailError as e:
        _log(f"Почта недоступна, продолжаю без prefetch inbox: {e}")

    authorize_url, server, holder, redirect_uri, code_verifier = _prepare_oauth_authorize_url()

    try:
        page.goto(authorize_url, wait_until="domcontentloaded", timeout=30000)
        _human_delay(1.5, 3.0)

        # Oops fallback
        if _is_oops_error(page):
            if not _handle_oops_retry(page, _log):
                raise RuntimeError("Страница 'Oops' не исчезла после retry")
            _human_delay(1.5, 3.0)

        if "log-in-or-create-account" in page.url and page.locator('a[href="/log-in"]').count() > 0:
            _human_delay(0.5, 1.2)
            page.locator('a[href="/log-in"]').click()
            _log("Нажато 'Войти'")
            _human_delay(1.0, 2.0)

        wait_result = _wait_for_any(
            page,
            ['input[type="email"][name="email"]', 'input[name="code"]', 'input[name="password"]'],
            url_contains=["localhost"],
            timeout=30000,
        )

        if wait_result == 'input[type="email"][name="email"]':
            _human_delay(0.5, 1.2)
            _human_type(page._driver, 'input[type="email"][name="email"]', email)
            _human_delay(0.3, 0.7)
            page.locator('button[type="submit"]').click()
            _log("Email введён, нажато Продолжить")

            wait_result = _wait_for_any(
                page,
                ['input[name="code"]', 'input[name="password"]', 'button[value="passwordless_login_send_otp"]'],
                url_contains=["localhost"],
                timeout=30000,
            )

        if wait_result == 'button[value="passwordless_login_send_otp"]':
            _human_delay(0.3, 0.8)
            page.locator('button[value="passwordless_login_send_otp"]').click()
            _log("Нажат вход через одноразовый код")
            _human_delay(1.0, 2.0)
            _wait_for_any(page, ['input[name="code"]'], timeout=30000)
            code = poll_for_code(mail_client, mailbox, existing_ids, log=_log)
            _human_delay(0.3, 0.8)
            _human_type(page._driver, 'input[name="code"]', code)
            _human_delay(0.2, 0.5)
            page.locator('button[name="intent"][value="validate"]').click()
        elif wait_result == 'input[name="password"]':
            if page.locator('button[value="passwordless_login_send_otp"]').count() > 0:
                _human_delay(0.3, 0.8)
                page.locator('button[value="passwordless_login_send_otp"]').click()
                _human_delay(1.0, 2.0)
                _wait_for_any(page, ['input[name="code"]'], timeout=30000)
                code = poll_for_code(mail_client, mailbox, existing_ids, log=_log)
                _human_delay(0.3, 0.8)
                _human_type(page._driver, 'input[name="code"]', code)
                _human_delay(0.2, 0.5)
                page.locator('button[name="intent"][value="validate"]').click()
            else:
                _human_delay(0.4, 1.0)
                _human_type(page._driver, 'input[name="password"]', password)
                _human_delay(0.3, 0.7)
                page.locator('button[type="submit"]').click()
        elif wait_result == 'input[name="code"]':
            code = poll_for_code(mail_client, mailbox, existing_ids, log=_log)
            _human_delay(0.3, 0.8)
            _human_type(page._driver, 'input[name="code"]', code)
            _human_delay(0.2, 0.5)
            page.locator('button[name="intent"][value="validate"]').click()

        _handle_consent_and_wait(page, _log, callback_wait_seconds=45)
        auth_code = _wait_for_callback(holder, timeout=120)
        _log("Authorization code получен")
        session_result = _exchange_oauth_code(auth_code, redirect_uri, code_verifier)

        _bootstrap_chatgpt_session(page, _log)
        return page, session_result
    except Exception:
        try:
            _save_debug_html(page, f"oauth-error-{email}", _log)
        except Exception:
            pass
        try:
            _context.close()
        except Exception:
            pass
        _open_contexts[:] = [c for c in _open_contexts if c != _context]
        raise
    finally:
        server.shutdown()
        server.server_close()


def oauth_login_manual(
    profile_dir: Path,
    log: Callable[[str], Any] | None = None,
    *,
    expected_email: str | None = None,
    timeout_seconds: int = 600,
) -> tuple[Page, dict]:
    _log = log or print

    _log("Открываю браузер для ручного логина...")
    page, _context = _launch_page(profile_dir)
    authorize_url, server, holder, redirect_uri, code_verifier = _prepare_oauth_authorize_url()

    try:
        page.goto(authorize_url, wait_until="domcontentloaded", timeout=30000)
        _activate_best_tab(
            _context.driver,
            [
                "chatgpt.com",
                "auth.openai.com",
                "login_with",
                redirect_uri,
            ],
        )
        if expected_email:
            _log(f"В браузере завершите вход вручную для {expected_email}.")
        else:
            _log("В браузере завершите вход вручную.")
        _log("Я больше ничего не нажимаю: email, пароль, код и consent подтверждайте сами в браузере.")
        _log("Как только произойдёт переход на localhost callback, я перехвачу код и сохраню сессию.")

        auth_code = _wait_for_callback(holder, timeout=timeout_seconds)
        _log("Authorization code получен")

        session_result = _exchange_oauth_code(auth_code, redirect_uri, code_verifier)
        return page, session_result
    except Exception:
        try:
            _context.close()
        except Exception:
            pass
        _open_contexts[:] = [c for c in _open_contexts if c != _context]
        raise
    finally:
        server.shutdown()
        server.server_close()


def save_codex_file(folder: Path, session: dict, email: str) -> Path:
    filename = f"codex-{email}-Team.json"
    path = folder / filename

    old: dict = {}
    if path.exists():
        try:
            old = json.loads(path.read_text())
        except Exception:
            pass

    access = session.get("access_token", "")
    if not access:
        raise RuntimeError("Нет access_token — codex-файл не сохранён")

    codex = {
        "id_token": session.get("id_token") or old.get("id_token", ""),
        "access_token": access,
        "refresh_token": session.get("refresh_token") or old.get("refresh_token", ""),
        "account_id": session.get("account_id") or old.get("account_id", ""),
        "last_refresh": datetime.now(timezone.utc).isoformat(),
        "email": email,
        "type": "codex",
        "expired": session.get("expired") or old.get("expired", ""),
    }

    folder.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(codex, indent=2, ensure_ascii=False))

    from . import PROJECT_ROOT
    codex_dir = PROJECT_ROOT / "codex"
    codex_dir.mkdir(parents=True, exist_ok=True)
    copy_path = codex_dir / filename
    copy_path.write_text(json.dumps(codex, indent=2, ensure_ascii=False))

    return path


def get_workspaces(page: Page, log: Callable[[str], Any] | None = None) -> list[dict]:
    _log = log or print
    try:
        page.wait_for_selector('button[name="workspace_id"]', timeout=10000)
    except Exception:
        _log("Workspace кнопки не найдены")
        return []

    workspace_info = page.evaluate(
        """() => {
            const buttons = document.querySelectorAll('button[name="workspace_id"]');
            const result = [];
            buttons.forEach(btn => {
                const spans = btn.querySelectorAll('span');
                let name = '';
                for (const s of spans) {
                    const text = s.textContent.trim();
                    if (text && text.length > 1 && !text.match(/^[A-Z]{1,2}$/)) {
                        name = text;
                        break;
                    }
                }
                if (!name) name = btn.textContent.trim();
                result.push({ workspace_id: btn.value, name: name });
            });
            return result;
        }"""
    )

    if not workspace_info:
        _log("Workspace кнопки не найдены")
        return []

    _log(f"Найдено {len(workspace_info)} workspace(s)")
    return workspace_info


def select_workspace(page: Page, workspace_id: str, log: Callable[[str], Any] | None = None) -> None:
    _log = log or print
    page.locator(f'button[name="workspace_id"][value="{workspace_id}"]').click()
    _log(f"Выбран workspace: {workspace_id}, ожидаю редирект...")
    try:
        page.wait_for_url(lambda url: "chatgpt.com" in url, timeout=30000)
    except Exception:
        time.sleep(5)


def browser_register(
    invite_url: str,
    email: str,
    openai_password: str,
    mail_client: MailProvider,
    mailbox: Mailbox,
    profile_dir: Path,
    log: Callable[[str], Any] | None = None,
    headless: bool = False,
) -> Page:
    _log = log or print

    existing_ids: set[str] = set()
    try:
        inbox = mail_client.inbox(mailbox)
        existing_ids = {msg.id for msg in inbox.messages}
    except MailError as e:
        _log(f"Почта недоступна, продолжаю без prefetch inbox: {e}")

    page, _context = _launch_page(profile_dir, headless=headless)
    try:
        page.goto(invite_url, wait_until="domcontentloaded")
        _human_delay(1.5, 3.0)

        # Oops fallback — страница ошибки вместо формы
        if _is_oops_error(page):
            if not _handle_oops_retry(page, _log):
                raise RuntimeError("Страница 'Oops' не исчезла после retry")
            _human_delay(1.5, 3.0)

        if page.locator('[data-testid="signup-button"]').count() > 0:
            _human_delay(0.5, 1.5)
            page.locator('[data-testid="signup-button"]').click()
            _human_delay(1.5, 3.0)

        if "log-in-or-create-account" in page.url and page.locator('a[href="/create-account"]').count() > 0:
            _human_delay(0.4, 1.0)
            page.locator('a[href="/create-account"]').click()
            _human_delay(1.0, 2.0)

        _wait_for_any(page, ['input[type="email"][name="email"]'], timeout=30000)
        _human_delay(0.5, 1.2)
        _human_type(page._driver, 'input[type="email"][name="email"]', email)
        _human_delay(0.3, 0.7)
        page.locator('button[type="submit"]').click()

        pwd_selector = _wait_for_any(page, ['input[name="new-password"]', 'input[name="password"]'], timeout=30000)
        _human_delay(0.4, 1.0)
        _human_type(page._driver, pwd_selector, openai_password)
        _human_delay(0.3, 0.7)
        page.locator('button[type="submit"]').click()

        wait_result = _wait_for_any(
            page,
            ['input[name="code"]', 'input[name="name"]'],
            url_contains=["chatgpt.com"],
            url_excludes=["/auth/"],
            timeout=60000,
        )

        if wait_result == 'input[name="code"]':
            code = poll_for_code(mail_client, mailbox, existing_ids, log=_log)
            _human_delay(0.3, 0.8)
            _human_type(page._driver, 'input[name="code"]', code)
            _human_delay(0.2, 0.5)
            page.locator('button[name="intent"][value="validate"]').click()
            wait_result = _wait_for_any(
                page,
                ['input[name="name"]'],
                url_contains=["chatgpt.com"],
                url_excludes=["/auth/"],
                timeout=60000,
            )

        if wait_result == "url":
            return page

        day, month, year = _random_birthday()
        name = _random_name()

        if wait_result == 'input[name="name"]' or page.locator('input[name="name"]').count() > 0:
            # Ждём пока fieldset станет enabled (Sentinel антибот)
            _wait_fieldset_enabled(page, _log, timeout=30)

            _human_delay(0.6, 1.5)
            _human_type(page._driver, 'input[name="name"]', name)
            _log(f"Имя: {name}")

            _human_delay(0.4, 0.9)
            _log(f"Дата рождения: {day}.{month}.{year}")
            _fill_birthday(page, day, month, year, _log)

            # Пере-заполняем имя — дата-стратегии могли добавить мусор
            cur_name = page.locator('input[name="name"]').get_attribute("value") or ""
            if cur_name != name:
                _log(f"Имя испорчено: '{cur_name}', исправляю...")
                page.locator('input[name="name"]').fill(name)

            _human_delay(0.5, 1.2)
            _submit_about_you_form(page, _log)
            _log("Форма регистрации отправлена")

        # Ждём редирект с about-you, повторяем submit если застряли
        deadline = time.time() + 120
        submit_retried = False
        while time.time() < deadline:
            cur_url = page.url
            # Успех — ушли с auth
            if "chatgpt.com" in cur_url and "/auth/" not in cur_url:
                break
            if page.locator('button[name="workspace_id"]').count() > 0:
                break

            # Oops — ошибка сервера, нажать Try again
            if _is_oops_error(page):
                _log("[oops] Ошибка на about-you, нажимаю Try again...")
                _handle_oops_retry(page, _log)
                time.sleep(3)
                # После retry форма может появиться снова — заполняем
                if page.locator('input[name="name"]').count() > 0:
                    _wait_fieldset_enabled(page, _log, timeout=15)
                    page.locator('input[name="name"]').fill(name)
                    _fill_birthday(page, day, month, year, _log)
                    page.locator('input[name="name"]').fill(name)
                    _submit_about_you_form(page, _log)
                    _log("Форма повторно заполнена после Oops")
                continue

            # Застряли на about-you — ждём подольше перед retry
            if "about-you" in cur_url and not submit_retried:
                time.sleep(15)
                _save_debug_html(page, f"about-you-stuck-{email}", _log)
                diag = page.evaluate(
                    """() => {
                        const btns = [...document.querySelectorAll('button')].map(b => ({
                            text: b.textContent.trim().slice(0, 50),
                            type: b.type, disabled: b.disabled, name: b.name
                        }));
                        const inputs = [...document.querySelectorAll('input, select, textarea')].map(i => ({
                            name: i.name, type: i.type, value: i.value, checked: i.checked
                        }));
                        const errors = [...document.querySelectorAll('[role="alert"], .error, [class*="error"], [class*="Error"]')]
                            .map(e => e.textContent.trim().slice(0, 100));
                        return { btns, inputs, errors, url: location.href };
                    }"""
                )
                _log(f"[диагностика about-you] {json.dumps(diag, ensure_ascii=False, default=str)}")

                # Повторная попытка: снять disabled, заполнить, submit
                try:
                    _wait_fieldset_enabled(page, _log, timeout=15)
                    if page.locator('input[name="name"]').count() > 0:
                        _log("Повторная попытка заполнить форму...")
                        page.locator('input[name="name"]').fill(name)
                        _fill_birthday(page, day, month, year, _log)
                        page.locator('input[name="name"]').fill(name)
                        time.sleep(0.5)
                        _submit_about_you_form(page, _log)
                        _log("Повторный submit")
                except Exception as retry_err:
                    _log(f"Повторная попытка не удалась: {retry_err}")
                submit_retried = True

            time.sleep(1)
        else:
            raise TimeoutError("Таймаут 120000мс: ни один селектор/URL не сработал")

        return page
    except Exception:
        try:
            _log(f"[диагностика] URL при ошибке: {page.url}")
            _save_debug_html(page, f"register-error-{email}", _log)
        except Exception:
            pass
        try:
            _context.close()
        except Exception:
            pass
        _open_contexts[:] = [c for c in _open_contexts if c != _context]
        raise
