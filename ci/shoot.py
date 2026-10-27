from playwright.sync_api import sync_playwright
URL, OUT = "http://localhost:8501", "shots"
import os; os.makedirs(OUT, exist_ok=True)
def login(page):
    page.goto(URL); page.get_by_label("Password").fill("ci-pass"); page.get_by_role("button", name="Log in").click()
    page.wait_for_timeout(9000)
def errs(page, tag):
    t = page.inner_text("body")
    for bad in ("Traceback", "Error", "couldn't load"):
        if bad in t: print(f"[{tag}] page mentions: {bad}")
with sync_playwright() as p:
    b = p.chromium.launch()
    ph = b.new_page(viewport={"width": 390, "height": 844}, device_scale_factor=2)
    login(ph); ph.screenshot(path=f"{OUT}/1_phone_home.png", full_page=True); errs(ph, "home")
    ph.get_by_role("tab", name="Race").click(); ph.wait_for_timeout(5000)
    ph.screenshot(path=f"{OUT}/2_phone_race.png", full_page=True); errs(ph, "race")
    ph.locator("details.more summary").first.click(); ph.wait_for_timeout(800)
    ph.screenshot(path=f"{OUT}/3_phone_race_card_open.png", full_page=True)
    for tab in ("Suggestions", "Portfolio", "Insiders"):
        ph.get_by_role("tab", name=tab).click(); ph.wait_for_timeout(4000)
        ph.screenshot(path=f"{OUT}/4_phone_{tab.lower()}.png", full_page=True); errs(ph, tab)
    ph.get_by_role("button", name="Settings").first.click(); ph.wait_for_timeout(1500)
    ph.screenshot(path=f"{OUT}/5_phone_settings.png")
    dk = b.new_page(viewport={"width": 1440, "height": 900})
    login(dk)
    dk.get_by_role("button", name="Settings").first.click(); dk.wait_for_timeout(1000)
    dk.get_by_text("Desktop view").click(); dk.wait_for_timeout(9000)
    dk.keyboard.press("Escape"); dk.wait_for_timeout(1500)
    dk.screenshot(path=f"{OUT}/6_desktop.png"); errs(dk, "desktop")
    b.close()
print("done")
