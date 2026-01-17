import os
import sys
import time
import json
import base64

from bs4 import BeautifulSoup  # type: ignore

from selenium import webdriver  # type: ignore
from selenium.webdriver.chrome.options import Options as ChromeOptions  # type: ignore
from selenium.webdriver.common.by import By  # type: ignore
from selenium.webdriver.support.ui import WebDriverWait  # type: ignore
from selenium.webdriver.support import expected_conditions as EC  # type: ignore

# We'll primarily use the app's configured GEMINI_MODEL for consistency
try:
    from concierge.config import GEMINI_MODEL  # type: ignore
except Exception:
    GEMINI_MODEL = None
try:
    import google.generativeai as genai  # type: ignore
except Exception:
    genai = None

# Load .env to access GEMINI_API_KEY when running standalone
try:
    from dotenv import load_dotenv  # type: ignore
    load_dotenv()
except Exception:
    pass


HOUSE_RULES_URL = os.environ.get(
    "HOUSE_RULES_URL",
    "https://www.airbnb.com/rooms/1224688859490426480/house-rules",
)
SAFETY_URL = os.environ.get(
    "SAFETY_URL",
    "https://www.airbnb.com/rooms/1224688859490426480/safety",
)


def get_driver() -> webdriver.Chrome:
    opts = ChromeOptions()
    opts.add_argument("--headless")
    opts.add_argument("--window-size=1440,2000")
    opts.add_argument("--no-sandbox")
    opts.add_argument("--disable-dev-shm-usage")
    drv = webdriver.Chrome(options=opts)
    drv.set_page_load_timeout(60)
    return drv


def capture_screenshot(url: str, mode: str) -> bytes:
    driver = get_driver()
    try:
        driver.get(url)

        # Progressive waits to allow the modal/page to fully render
        wait_windows = [3, 5, 8, 12]

        if mode == "safety":
            selectors = [
                "//*[@role='dialog']",
                "//*[contains(@aria-modal,'true')]",
                "//*[contains(@data-testid,'modal')]",
                "//section[contains(translate(., 'SAFETY', 'safety'), 'safety')]",
                "//div[contains(translate(., 'SAFETY', 'safety'), 'safety')]",
                "//*[contains(translate(., 'PROPERTY SAFETY', 'property safety'), 'property safety')]",
            ]
        else:  # rules/rules_additional
            selectors = [
                "//*[@role='dialog']",
                "//*[contains(@aria-modal,'true')]",
                "//*[contains(@data-testid,'modal')]",
                "//section[contains(translate(., 'HOUSE RULES', 'house rules'), 'house rules')]",
                "//div[contains(translate(., 'HOUSE RULES', 'house rules'), 'house rules')]",
            ]

        for delay in wait_windows:
            time.sleep(delay)
            for xp in selectors:
                try:
                    elem = driver.find_element(By.XPATH, xp)
                    text = elem.text.strip()
                    if len(text) < 20:
                        continue
                    driver.execute_script("arguments[0].scrollIntoView(true);", elem)
                    time.sleep(0.3)
                    return elem.screenshot_as_png
                except Exception:
                    continue

        # If still nothing and mode is rules or rules_additional, try clicking 'Show more' under Additional rules WITHIN the House rules modal
        if mode in ('rules', 'rules_additional'):
            try:
                # First ensure we have the main House rules modal context
                rules_modal = None
                try:
                    rules_modal = driver.find_element(By.XPATH, "//*[@role='dialog' or @aria-modal='true'][.//*[contains(translate(., 'HOUSE RULES', 'house rules'), 'house rules')]]")
                except Exception:
                    rules_modal = None

                # Find Additional rules block inside the house rules modal
                addl_container = None
                if rules_modal is not None:
                    try:
                        addl_container = rules_modal.find_element(By.XPATH, ".//*[contains(translate(., 'ADDITIONAL RULES', 'additional rules'), 'additional rules')]/ancestor-or-self::*[self::section or self::div][1]")
                    except Exception:
                        addl_container = None

                # Click a 'Show more' within that container specifically (inside modal)
                if addl_container is not None:
                    candidates = addl_container.find_elements(By.XPATH, ".//button[contains(translate(., 'SHOW MORE', 'show more'), 'show more')] | .//a[contains(translate(., 'SHOW MORE', 'show more'), 'show more')]")
                else:
                    candidates = []
                clicked = False
                for el in candidates:
                    try:
                        driver.execute_script("arguments[0].scrollIntoView(true);", el)
                        time.sleep(0.3)
                        el.click()
                        clicked = True
                        break
                    except Exception:
                        continue
                # Wait for nested Additional rules modal/dialog (distinct from the parent House rules modal)
                if clicked:
                    for extra in [3, 5, 8, 12]:
                        time.sleep(extra)
                        try:
                            nested = driver.find_element(By.XPATH, "(//*[@role='dialog' or @aria-modal='true'][.//*[contains(translate(., 'ADDITIONAL RULES', 'additional rules'), 'additional rules')]])[last()]")
                            txt = nested.text.strip()
                            if len(txt) >= 20:
                                driver.execute_script("arguments[0].scrollIntoView(true);", nested)
                                time.sleep(0.3)
                                return nested.screenshot_as_png
                        except Exception:
                            continue
                    # If a separate nested modal wasn't found, try the expanded Additional rules section content within the parent modal
                    if addl_container is not None:
                        for extra in [2, 4, 6]:
                            time.sleep(extra)
                            try:
                                expanded_txt = addl_container.text.strip()
                                # Heuristic: expect long text (e.g., 15 paragraphs)
                                if len(expanded_txt) > 300:
                                    driver.execute_script("arguments[0].scrollIntoView(true);", addl_container)
                                    time.sleep(0.3)
                                    return addl_container.screenshot_as_png
                            except Exception:
                                continue
                # Wait and try targeted element again
                for extra in [3, 5, 8]:
                    time.sleep(extra)
                    for xp in selectors:
                        try:
                            elem = driver.find_element(By.XPATH, xp)
                            text = elem.text.strip()
                            if len(text) < 20:
                                continue
                            driver.execute_script("arguments[0].scrollIntoView(true);", elem)
                            time.sleep(0.3)
                            return elem.screenshot_as_png
                        except Exception:
                            continue
            except Exception:
                pass

        try:
            return driver.get_full_page_screenshot_as_png()
        except Exception:
            return driver.get_screenshot_as_png()
    finally:
        try:
            driver.quit()
        except Exception:
            pass


def capture_rules_pair(url: str) -> tuple[bytes | None, bytes | None]:
    """Capture two screenshots: the House rules modal, then the Additional rules after clicking Show more.
    Returns (main_png, additional_png). Either can be None if not found.
    """
    driver = get_driver()
    main_png: bytes | None = None
    add_png: bytes | None = None
    try:
        driver.get(url)
        wait_windows = [3, 5, 8, 12]
        # 1) Capture main House rules modal element (unconditionally save if found)
        try:
            WebDriverWait(driver, 15).until(
                EC.presence_of_element_located((
                    By.XPATH,
                    "//*[@role='dialog' or @aria-modal='true'][.//*[contains(translate(., 'HOUSE RULES', 'house rules'), 'house rules')]]"
                ))
            )
        except Exception:
            pass
        for delay in wait_windows:
            time.sleep(delay)
            try:
                rules_modal = driver.find_element(By.XPATH, "//*[@role='dialog' or @aria-modal='true'][.//*[contains(translate(., 'HOUSE RULES', 'house rules'), 'house rules')]]")
                driver.execute_script("arguments[0].scrollIntoView(true);", rules_modal)
                time.sleep(0.3)
                main_png = rules_modal.screenshot_as_png
                break
            except Exception:
                continue

        # 2) Click Show more within Additional rules subsection and capture nested/expanded content
        try:
            rules_modal = driver.find_element(By.XPATH, "//*[@role='dialog' or @aria-modal='true'][.//*[contains(translate(., 'HOUSE RULES', 'house rules'), 'house rules')]]")
        except Exception:
            rules_modal = None

        if rules_modal is not None:
            addl_container = None
            try:
                addl_container = rules_modal.find_element(By.XPATH, ".//*[contains(translate(., 'ADDITIONAL RULES', 'additional rules'), 'additional rules')]/ancestor-or-self::*[self::section or self::div][1]")
            except Exception:
                addl_container = None

            if addl_container is not None:
                candidates = addl_container.find_elements(By.XPATH, ".//button[contains(translate(., 'SHOW MORE', 'show more'), 'show more')] | .//a[contains(translate(., 'SHOW MORE', 'show more'), 'show more')]")
                for el in candidates:
                    try:
                        driver.execute_script("arguments[0].scrollIntoView(true);", el)
                        time.sleep(0.3)
                        el.click()
                        # Give a short extra wait per instruction for content to appear
                        time.sleep(2)
                        break
                    except Exception:
                        continue

                # Wait for nested dialog or expanded long content
                for extra in [3, 5, 8, 12]:
                    time.sleep(extra)
                    # Try nested dialog first
                    try:
                        nested = driver.find_element(By.XPATH, "(//*[@role='dialog' or @aria-modal='true'][.//*[contains(translate(., 'ADDITIONAL RULES', 'additional rules'), 'additional rules')]])[last()]")
                        if nested:
                            driver.execute_script("arguments[0].scrollIntoView(true);", nested)
                            time.sleep(0.3)
                            add_png = nested.screenshot_as_png
                            break
                    except Exception:
                        pass
                    # Fallback to expanded section inside parent modal
                    try:
                        driver.execute_script("arguments[0].scrollIntoView(true);", addl_container)
                        time.sleep(0.3)
                        add_png = addl_container.screenshot_as_png
                        break
                    except Exception:
                        pass

                # If still nothing, save full page after click
                if add_png is None:
                    try:
                        add_png = driver.get_full_page_screenshot_as_png()
                    except Exception:
                        try:
                            add_png = driver.get_screenshot_as_png()
                        except Exception:
                            add_png = None

        return (main_png, add_png)
    finally:
        try:
            driver.quit()
        except Exception:
            pass

RULES_PROMPT = (
    "You are given a screenshot image of the Airbnb House Rules modal/page. "
    "Extract ALL rule-related texts faithfully from the screenshot, including sections like 'Checking in and out', 'During your stay', 'Before you leave', and 'Additional rules'. "
    "Then return a strict JSON array where each item has: {title, content, type}. "
    "- title: short label like 'Quiet hours', 'Pets', 'No smoking', 'Parties and events', 'Departure instructions', or a concise heading derived from the text. "
    "- content: the full rule text for that item, preserving times and limits (e.g., 'Quiet hours 9:00 PM - 7:00 AM', 'Maximum 2 guests'). "
    "- type: one of 'rule' or 'instruction' (use 'instruction' for 'Before you leave' checklist items; otherwise 'rule'). "
    "Do not add commentary. Return ONLY the JSON array."
)

SAFETY_PROMPT = (
    "You are given a screenshot image of the Airbnb Safety & property page or modal. "
    "Extract ALL safety/emergency-related texts faithfully (e.g., Smoke alarm, Carbon monoxide alarm, Security camera/recording device, Potential hazards, Waterfront or nearby water, Must climb stairs, etc.). "
    "Return a strict JSON array where each item has: {title, content, type}. "
    "- title: concise safety label like 'Smoke alarm', 'Carbon monoxide alarm', 'Security camera', 'Waterfront', 'Must climb stairs'. "
    "- content: the full associated text, including whether devices are present/absent and any instructions or caveats. "
    "- type: use 'emergency'. "
    "Do not add commentary. Return ONLY the JSON array."
)


def run_gemini_on_image(png_bytes: bytes, mode: str) -> list:
    """Call Gemini with the configured app model, falling back to legacy SDK."""
    text = ""
    api_key = os.environ.get("GEMINI_API_KEY")
    if api_key and genai is not None:
        try:
            genai.configure(api_key=api_key)
            model_name = os.environ.get("GEMINI_MODEL_NAME", "gemini-2.5-flash-lite")
            model = genai.GenerativeModel(model_name)
            attempts = 0
            last_err = None
            while attempts < 3:
                try:
                    prompt = SAFETY_PROMPT if mode == "safety" else RULES_PROMPT
                    resp = model.generate_content([prompt, {"mime_type": "image/png", "data": png_bytes}])
                    text = resp.text or "[]"
                    break
                except Exception as e:
                    last_err = e
                    attempts += 1
                    time.sleep(2 * attempts)
            else:
                text = f"ERROR: {last_err}"
        except Exception as e:
            text = f"ERROR: {e}"
    elif GEMINI_MODEL is not None:
        try:
            prompt = SAFETY_PROMPT if mode == "safety" else RULES_PROMPT
            resp = GEMINI_MODEL.generate_content([prompt, {"mime_type": "image/png", "data": png_bytes}])
            text = resp.text or "[]"
        except Exception as e:
            text = f"ERROR: {e}"
    else:
        text = "[]"

    text = text.strip()
    if text.startswith("```"):
        parts = text.split("\n", 1)
        text = parts[1] if len(parts) > 1 else text
        if text.endswith("```"):
            text = text[:-3]

    try:
        data = json.loads(text)
        if isinstance(data, list):
            return data
    except Exception:
        pass

    return [
        {"title": "Extracted", "content": text, "type": "rule"}
    ]


def main():
    mode = "rules"
    url = HOUSE_RULES_URL
    if len(sys.argv) > 1:
        arg = sys.argv[1]
        if arg in ("rules", "safety", "rules_both"):
            mode = arg
            url = HOUSE_RULES_URL if mode == "rules" else SAFETY_URL
        else:
            url = arg
            mode = "rules" if "house-rules" in url else ("safety" if "safety" in url else "rules")

    if mode == "rules_both":
        main_png, add_png = capture_rules_pair(url)
        out_main = os.path.abspath("rules_modal_main.png")
        out_add = os.path.abspath("rules_modal_additional.png")
        main_items = []
        add_items = []
        if main_png:
            with open(out_main, "wb") as f:
                f.write(main_png)
            main_items = run_gemini_on_image(main_png, "rules")
        if add_png:
            with open(out_add, "wb") as f:
                f.write(add_png)
            add_items = run_gemini_on_image(add_png, "rules")
        print(json.dumps({
            "main_screenshot": out_main if main_png else None,
            "additional_screenshot": out_add if add_png else None,
            "main_items": main_items,
            "additional_items": add_items,
        }, ensure_ascii=False, indent=2))
    else:
        png = capture_screenshot(url, mode)
        out_png = os.path.abspath("rules_modal_screenshot.png")
        with open(out_png, "wb") as f:
            f.write(png)

        items = run_gemini_on_image(png, mode)
        print(json.dumps({"screenshot_path": out_png, "items": items}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()


