import os, traceback
from playwright.sync_api import sync_playwright
URL, OUT = "http://localhost:8501", "shots"
os.makedirs(OUT, exist_ok=True)

def safe(tag, page, fn):
    try:
        fn()
    except Exception:
        print(f"[{tag}] FAILED"); traceback.print_exc()
        try: page.screenshot(path=f"{OUT}/fail_{tag}.png", full_page=True)
        except Exception: pass

def login(page):
    page.goto(URL); page.wait_for_timeout(6000)
    page.get_by_label("Password").fill("ci-pass"); page.get_by_role("button", name="Log in").click()
    page.wait_for_timeout(12000)

def shot(page, name, full=True):
    page.screenshot(path=f"{OUT}/{name}.png", full_page=full)
    t = page.inner_text("body")
    for bad in ("Traceback", "Error", "couldn't load"):
        if bad in t: print(f"[{name}] page mentions: {bad}")

def tab(page, name):
    page.get_by_role("tab", name=name).click(); page.wait_for_timeout(5000)

with sync_playwright() as p:
    b = p.chromium.launch()
    ph = b.new_page(viewport={"width": 390, "height": 844}, device_scale_factor=2)
    safe("login", ph, lambda: (login(ph), shot(ph, "1_phone_home")))
    safe("race", ph, lambda: (tab(ph, "Race"), shot(ph, "2_phone_race")))
    safe("card", ph, lambda: (ph.locator("details.more summary").first.click(), ph.wait_for_timeout(800), shot(ph, "3_phone_card_open")))
    for t_ in ("Suggestions", "Portfolio", "Insiders"):
        safe(t_, ph, lambda t_=t_: (tab(ph, t_), shot(ph, f"4_phone_{t_.lower()}")))
    safe("settings", ph, lambda: (ph.get_by_role("button", name="Settings").first.click(), ph.wait_for_timeout(1500), shot(ph, "5_phone_settings", False)))
    dk = b.new_page(viewport={"width": 1440, "height": 900})
    def desk():
        login(dk)
        dk.get_by_role("button", name="Settings").first.click(); dk.wait_for_timeout(1500)
        dk.get_by_text("Desktop view").first.click(); dk.wait_for_timeout(12000)
        dk.keyboard.press("Escape"); dk.wait_for_timeout(1500)
        shot(dk, "6_desktop", False)
    safe("desktop", dk, desk)
    b.close()
print("done")
