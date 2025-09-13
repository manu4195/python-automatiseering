import os
import time
import requests
from dotenv import load_dotenv
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import (
    StaleElementReferenceException,
    TimeoutException
)
from webdriver_manager.chrome import ChromeDriverManager

# .env inladen (laad omgevingsvariabelen uit .env bestand)
load_dotenv()
OSIRIS_USER = os.getenv("OSIRIS_USER")
OSIRIS_PASS = os.getenv("OSIRIS_PASS")
DISCORD_WEBHOOK = os.getenv("DISCORD_WEBHOOK")

# ===== Helpers =====
def start_driver():
    # Start een headless Chrome browser met Selenium
    chrome_options = Options()
    chrome_options.add_argument("--headless=new")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-gpu")
    chrome_options.add_argument("--window-size=1920,1080")
    service = Service(ChromeDriverManager().install())
    return webdriver.Chrome(service=service, options=chrome_options)

def send_to_discord(file_path=None, content=None):
    # Stuur een bericht (en optioneel een bestand) naar Discord via webhook
    data = {}
    files = {}
    if content:
        data["content"] = content
    if file_path and os.path.exists(file_path):
        files["file"] = open(file_path, "rb")
    resp = requests.post(DISCORD_WEBHOOK, data=data, files=files)
    if files.get("file"):
        files["file"].close()
    if file_path and os.path.exists(file_path):
        os.remove(file_path)
    if resp.status_code >= 400:
        print("Fout bij sturen:", resp.status_code, resp.text)

def save_and_send(driver, name, note=None):
    # Maak een screenshot en stuur deze naar Discord
    timestamp = time.strftime("%Y%m%d-%H%M%S")
    fname = f"{name}_{timestamp}.png"
    driver.save_screenshot(fname)
    content = f"📸 Screenshot: {name}"
    if note:
        content += f"\n📝 {note}"
    send_to_discord(fname, content=content)

def safe_click(driver, locator, timeout=12, retries=3):
    # Klik veilig op een element, probeer het meerdere keren bij fouten
    wait = WebDriverWait(driver, timeout)
    last_err = None
    for attempt in range(1, retries+1):
        try:
            elem = wait.until(EC.element_to_be_clickable(locator))
            elem.click()
            return True
        except (StaleElementReferenceException, TimeoutException) as e:
            last_err = e
            print(f"⚠️ Poging {attempt} mislukt voor {locator}, opnieuw proberen...")
    raise Exception(f"Kon element {locator} niet stabiel klikken") from last_err

def wait_present(driver, locator, timeout=15):
    # Wacht tot een element aanwezig is in de DOM
    return WebDriverWait(driver, timeout).until(EC.presence_of_element_located(locator))

def wait_any_present(driver, locators, timeout=15):
    # Wacht tot een van meerdere elementen aanwezig is
    wait = WebDriverWait(driver, timeout)
    def any_present(d):
        for loc in locators:
            elems = d.find_elements(*loc)
            if elems:
                return elems[0]
        return False
    return wait.until(any_present)

def find_password_field(driver, timeout=15):
    # Zoek het wachtwoordveld, ook in iframes indien nodig
    candidates = [
        (By.NAME, "passwd"),
        (By.ID, "i0118"),
        (By.CSS_SELECTOR, "input[type='password']")
    ]
    for loc in candidates:
        try:
            return wait_present(driver, loc, timeout=timeout)
        except TimeoutException:
            continue
    print("🔍 Wachtwoordveld niet direct gevonden, zoeken in iframes...")
    for iframe in driver.find_elements(By.TAG_NAME, "iframe"):
        driver.switch_to.frame(iframe)
        for loc in candidates:
            try:
                return wait_present(driver, loc, timeout=timeout)
            except TimeoutException:
                continue
        driver.switch_to.default_content()
    raise TimeoutException("Geen wachtwoordveld gevonden")

# ===== 2FA =====
def handle_2fa_sms(driver):
    # Afhandelen van 2FA via sms
    print("📲 2FA: sms-methode kiezen en code versturen...")
    save_and_send(driver, "2fa_start", "2FA-scherm gedetecteerd")

    # Toon alternatieve methodes (indien aanwezig)
    try:
        safe_click(driver, (By.PARTIAL_LINK_TEXT, "Outlook-app"), timeout=5)
    except:
        pass

    # Kies sms-optie (als zichtbaar)
    for loc in [
        (By.XPATH, "//div[@data-value='OneWaySMS']"),
        (By.XPATH, "//span[@data-value='OneWaySMS']"),
        (By.XPATH, "//div[contains(@data-bind,'data-value') and contains(., 'SMS')]"),
        (By.XPATH, "//div[contains(@class,'table') and .//span[contains(@data-value,'OneWaySMS')]]"),
    ]:
        try:
            safe_click(driver, loc, timeout=6)
            save_and_send(driver, "2fa_sms_selected", "Sms-optie geselecteerd")
            break
        except:
            continue

    # Wacht op codeveld
    code_field = wait_any_present(driver, [
        (By.NAME, "otc"),
        (By.ID, "idTxtBx_SAOTCC"),
        (By.CSS_SELECTOR, "input[type='tel']")
    ], timeout=20)
    save_and_send(driver, "2fa_code_field", "Codeveld zichtbaar")

    # Vraag direct om code; leeg = 1x opnieuw verzenden proberen
    code = input("Voer de ontvangen sms-code in (laat leeg voor opnieuw verzenden): ").strip()
    if not code:
        print("🔄 Probeer 'opnieuw verzenden'...")
        # knop voor opnieuw verzenden (indien aanwezig)
        for loc in [
            (By.ID, "resendCode"),
            (By.XPATH, "//a[contains(., 'Opnieuw') or contains(., 'Nogmaals') or contains(., 'Resend') or contains(., 'Erneut')]"),
            (By.XPATH, "//button[contains(., 'Opnieuw') or contains(., 'Nogmaals') or contains(., 'Resend') or contains(., 'Erneut')]"),
        ]:
            try:
                safe_click(driver, loc, timeout=5)
                save_and_send(driver, "2fa_resend_clicked", "Opnieuw verzenden geklikt")
                break
            except:
                continue
        code = input("Voer de ontvangen sms-code in: ").strip()

    code_field.clear()
    code_field.send_keys(code)
    save_and_send(driver, "2fa_code_entered", "Code ingevuld")

    # Bevestigen/verifiëren
    for loc in [
        (By.ID, "idSubmit_SAOTCC_Continue"),
        (By.ID, "idSubmit_ProofUp_Redirect"),
        (By.CSS_SELECTOR, "input[type='submit']"),
        (By.XPATH, "//button[contains(., 'Verifi') or contains(., 'Verify') or contains(., 'Doorgaan') or contains(., 'Weiter')]"),
    ]:
        try:
            safe_click(driver, loc, timeout=8)
            save_and_send(driver, "2fa_submitted", "2FA verstuurd")
            break
        except:
            continue

# ===== Main flow =====
def login_and_fetch_screenshot():
    # Log in op Osiris en maak een screenshot van het rooster
    driver = start_driver()

    try:
        print("🌐 Openen van Osiris roosterpagina...")
        driver.get("https://mborijnland.osiris-student.nl/rooster")
        save_and_send(driver, "step_opened", "Pagina geopend")

        # E-mail
        print("✉️  E-mailadres invullen...")
        email_input = wait_present(driver, (By.NAME, "loginfmt"), timeout=20)
        email_input.clear()
        email_input.send_keys(OSIRIS_USER)
        save_and_send(driver, "step_email_filled", "E-mail ingevuld")

        # Volgende
        safe_click(driver, (By.ID, "idSIButton9"))
        save_and_send(driver, "after_email_submit", "Volgende geklikt — controleer pagina")

        # Wachtwoord
        print("🔑 Wachtwoord invullen...")
        pass_input = find_password_field(driver, timeout=20)
        pass_input.clear()
        pass_input.send_keys(OSIRIS_PASS)
        save_and_send(driver, "step_password_filled", "Wachtwoord ingevuld")

        # Extra zekerheid: vlak voor submit nogmaals invullen
        pass_input = find_password_field(driver, timeout=10)
        pass_input.clear()
        pass_input.send_keys(OSIRIS_PASS)

        # Aanmelden
        safe_click(driver, (By.ID, "submitButton"))
        save_and_send(driver, "after_password_submit", "Aanmelden geklikt")

        # 2FA
        try:
            handle_2fa_sms(driver)
        except TimeoutException:
            print("ℹ️ Geen 2FA-scherm gevonden of niet nodig")

        # Blijf aangemeld? no
        print("📌 Controleren op 'Blijf aangemeld?' scherm...")
        try:
            safe_click(driver, (By.ID, "idSIButton9"), timeout=8)
            save_and_send(driver, "stay_signed_in", "Blijf aangemeld bevestigd")
        except:
            print("ℹ️ Geen stay-signed-in scherm, doorgaan")

        # Wachten op rooster (heuristisch)
        print("⏳ Wachten tot rooster zichtbaar is...")
        try:
            WebDriverWait(driver, 25).until(
                EC.any_of(
                    EC.presence_of_element_located((By.CSS_SELECTOR, "[data-testid='rooster'], .rooster, #rooster")),
                    EC.presence_of_element_located((By.TAG_NAME, "table")),
                    EC.url_contains("rooster")
                )
            )
        except TimeoutException:
            pass
        save_and_send(driver, "final_rooster", "Rooster geladen of eindstatus")

        # Eind-screenshot
        fname = "rooster.png"
        driver.save_screenshot(fname)
        send_to_discord(fname, content="✅ Eind-rooster screenshot")

    finally:
        driver.quit()

def main():
    # Start het hoofdproces: inloggen en rooster ophalen
    print("➡️ Ophalen en inloggen…")
    login_and_fetch_screenshot()
    print("✅ Klaar!")

if __name__ == "__main__":
    main()