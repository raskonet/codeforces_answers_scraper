import json
import os
import random
import subprocess
import time

from selenium import webdriver
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.common.by import By
from selenium.webdriver.firefox.options import Options
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait


def setup_driver():
    """Set up a Firefox browser with anti-detection options."""
    options = Options()
    options.headless = True  # Headless mode (can toggle to False for debugging)
    options.add_argument("--width=1920")  # Set realistic window size
    options.add_argument("--height=1080")

    # Use a realistic user agent for Firefox on Linux
    options.set_preference(
        "general.useragent.override",
        "Mozilla/5.0 (X11; Linux x86_64; rv:91.0) Gecko/20100101 Firefox/91.0",
    )

    # Disable automation flags to avoid detection
    options.set_preference("dom.webdriver.enabled", False)
    options.set_preference("useAutomationExtension", False)

    # Ensure JavaScript is enabled (Cloudflare often checks this)
    options.set_preference("javascript.enabled", True)

    driver = webdriver.Firefox(options=options)
    return driver


def load_cookies(driver):
    """Load cookies to maintain a session."""
    driver.get("https://codeforces.com")
    try:
        with open("codeforces_cookies.json", "r") as f:
            cookies = json.load(f)
        for cookie in cookies:
            driver.add_cookie(
                {
                    "name": cookie["name"],
                    "value": cookie["value"],
                    "domain": cookie["domain"],
                    "path": cookie.get("path", "/"),
                    "secure": cookie.get("secure", False),
                }
            )
    except FileNotFoundError:
        print("Cookies file not found. Proceeding without cookies.")
    driver.refresh()
    time.sleep(random.uniform(2, 5))  # Random delay to mimic human pace


def simulate_human_behavior(driver):
    """Simulate human-like actions to avoid bot detection."""
    actions = ActionChains(driver)
    # Random mouse movement
    actions.move_by_offset(random.randint(100, 500), random.randint(100, 500)).perform()
    time.sleep(random.uniform(0.5, 1.5))

    # Scroll down and back up
    driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
    time.sleep(random.uniform(1, 2))
    driver.execute_script("window.scrollTo(0, 0);")
    time.sleep(random.uniform(0.5, 1.5))


def get_problem_samples(driver, contest_id, problem_index):
    """Fetch problem samples with human-like behavior."""
    url = f"https://codeforces.com/problemset/problem/{contest_id}/{problem_index}"
    driver.get(url)
    simulate_human_behavior(driver)

    # Wait for page elements to load (longer timeout for Cloudflare)
    WebDriverWait(driver, 15).until(
        EC.presence_of_element_located((By.CSS_SELECTOR, "div.input"))
    )
    time.sleep(random.uniform(1, 3))  # Extra delay

    inputs = [
        elem.text.strip().replace("\r", "")
        for elem in driver.find_elements(By.CSS_SELECTOR, "div.input pre")
    ]
    outputs = [
        elem.text.strip().replace("\r", "")
        for elem in driver.find_elements(By.CSS_SELECTOR, "div.output pre")
    ]
    return list(zip(inputs, outputs))


def main():
    """Main function to test the script."""
    driver = setup_driver()
    try:
        print("Setting up browser and loading cookies...")
        load_cookies(driver)

        # Example: Fetch samples for problem 2069F
        contest_id = "2069"
        problem_index = "F"
        print(f"Fetching samples for problem {contest_id}{problem_index}...")
        samples = get_problem_samples(driver, contest_id, problem_index)

        if samples:
            print(f"Found {len(samples)} test cases:")
            for i, (inp, out) in enumerate(samples):
                print(f"Test {i+1}:")
                print(f"Input: {inp}")
                print(f"Output: {out}\n")
        else:
            print("No samples found or Cloudflare blocked the request.")
    except Exception as e:
        print(f"An error occurred: {e}")
    finally:
        driver.quit()  # Clean up


if __name__ == "__main__":
    main()
