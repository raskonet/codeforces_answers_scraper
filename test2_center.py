import os
import json
import requests
from bs4 import BeautifulSoup
import re
import time
from dotenv import load_dotenv
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.firefox.options import Options
from selenium.webdriver.firefox.service import Service
from selenium.common.exceptions import TimeoutException, NoSuchElementException
from selenium.webdriver.common.action_chains import ActionChains
from webdriver_manager.firefox import GeckoDriverManager

# Load environment variables
load_dotenv()

def login_to_cf():
    session = requests.Session()
    
    # Set up user agent to avoid 403 errors - Linux Firefox user agent
    session.headers.update({
        'User-Agent': 'Mozilla/5.0 (X11; Linux x86_64; rv:109.0) Gecko/20100101 Firefox/109.0'
    })
    
    # Check if cookie file exists
    cookie_file = 'codeforces_cookies.json'
    if not os.path.exists(cookie_file):
        raise Exception(f"Cookie file '{cookie_file}' not found. Please export your Firefox cookies to this file.")
    
    # Load cookies from the JSON file
    try:
        with open(cookie_file, 'r') as f:
            cookies = json.load(f)
            
        # Add cookies to session - adapted for Cookie-Editor format
        for cookie in cookies:
            session.cookies.set(
                cookie['name'], 
                cookie['value'], 
                domain=cookie['domain'],
                path=cookie.get('path', '/'),
                secure=cookie.get('secure', False)
            )
    except json.JSONDecodeError:
        raise Exception("Invalid JSON in cookie file. Please check the format.")
    except Exception as e:
        raise Exception(f"Error loading cookies: {str(e)}")
    
    # Test if we're logged in by checking a protected page
    response = session.get('https://codeforces.com/submissions/my')
    
    # Debug info
    print(f"Login test response code: {response.status_code}")
    
    # If we get a 403, cookies may still be valid but we need to validate another way
    if response.status_code == 403:
        print("Got 403 error, but will proceed anyway to verify login (this might be a CloudFlare protection)")
    
    # Check for common patterns that indicate we're not logged in
    if 'Enter' in response.text and 'Login' in response.text:
        print("Debug: Found 'Enter' and 'Login' text in response, suggesting not logged in")
        raise Exception("Login failed. Cookies may have expired or are not valid.")
    
    print("Login verification successful!")
    return session

def extract_code_from_html(html_content):
    """
    Extract code from the HTML content using BeautifulSoup
    """
    soup = BeautifulSoup(html_content, 'html.parser')
    
    # Try to find the code element with ID 'program-source-text'
    code_element = soup.find(id='program-source-text')
    if code_element:
        return code_element.get_text()
    
    # If that fails, look for any pre elements that might contain the code
    pre_elements = soup.find_all('pre')
    for pre in pre_elements:
        # Look for pre elements that might contain the code (often with a specific class or nearby context)
        if pre.get('id') == 'program-source-text' or pre.get('class') and 'source' in ' '.join(pre.get('class')):
            return pre.get_text()
    
    return None

def get_solution_with_selenium(problem_id):
    """
    Use Selenium with Firefox to fetch the top solution for a problem
    """
    driver = None
    try:
        print("Initializing Selenium with Firefox...")
        
        # Setup Firefox options
        firefox_options = Options()
        firefox_options.add_argument("--headless")  # Run in headless mode
        firefox_options.set_preference("general.useragent.override", 
                                      "Mozilla/5.0 (X11; Linux x86_64; rv:109.0) Gecko/20100101 Firefox/109.0")
        
        # Initialize the driver
        service = Service(GeckoDriverManager().install())
        driver = webdriver.Firefox(service=service, options=firefox_options)
        
        # Set a larger window size to ensure all elements are visible
        driver.set_window_size(1920, 1080)
        
        # Load cookie file for Selenium
        cookie_file = 'codeforces_cookies.json'
        with open(cookie_file, 'r') as f:
            cookies = json.load(f)
            
        # Navigate to Codeforces first to set cookies
        driver.get("https://codeforces.com")
        
        # Add cookies to the driver
        for cookie in cookies:
            # Adjust cookie for Selenium
            cookie_dict = {
                'name': cookie['name'],
                'value': cookie['value'],
                'domain': cookie['domain'],
                'path': cookie.get('path', '/'),
                'secure': cookie.get('secure', False),
                'expiry': cookie.get('expirationDate', None)
            }
            
            # Remove problematic fields
            if 'sameSite' in cookie_dict:
                del cookie_dict['sameSite']
            if 'hostOnly' in cookie_dict:
                del cookie_dict['hostOnly']
            if cookie_dict['expiry'] is not None:
                cookie_dict['expiry'] = int(cookie_dict['expiry'])
                
            try:
                driver.add_cookie(cookie_dict)
            except Exception as e:
                print(f"Warning: Could not add cookie {cookie['name']}: {str(e)}")
                
        # Parse the problem ID
        match = re.match(r'^(\d+)([A-Z])$', problem_id)
        if not match:
            raise ValueError("Invalid problem ID format")
        
        contest_id = match.group(1)
        problem_index = match.group(2)
        
        # Navigate to problem status page
        status_url = f"https://codeforces.com/problemset/status/{contest_id}/problem/{problem_index}"
        print(f"Navigating to: {status_url}")
        driver.get(status_url)
        
        # Wait for the page to load
        WebDriverWait(driver, 15).until(
            EC.presence_of_element_located((By.CLASS_NAME, "datatable"))
        )
        
        # Find the first submission with "Accepted" verdict
        rows = driver.find_elements(By.CSS_SELECTOR, "table.status-frame-datatable tr")
        submission_id = None
        submission_info = {}
        
        print("Scanning for accepted submissions...")
        
        for row in rows[1:]:  # Skip header row
            try:
                cells = row.find_elements(By.TAG_NAME, "td")
                
                # Check if this has an Accepted verdict
                verdict_cell = cells[5] if len(cells) > 5 else None
                if verdict_cell and "Accepted" in verdict_cell.text:
                    # Get submission ID
                    id_cell = cells[0]
                    submission_id = id_cell.text.strip()
                    
                    # Collect all relevant information for display
                    submission_info = {
                        "id": submission_id,
                        "when": cells[1].text.strip() if len(cells) > 1 else "Unknown",
                        "who": cells[2].text.strip() if len(cells) > 2 else "Unknown",
                        "problem": cells[3].text.strip() if len(cells) > 3 else "Unknown",
                        "lang": cells[4].text.strip() if len(cells) > 4 else "Unknown",
                        "verdict": cells[5].text.strip() if len(cells) > 5 else "Unknown",
                        "time": cells[6].text.strip() if len(cells) > 6 else "Unknown",
                        "memory": cells[7].text.strip() if len(cells) > 7 else "Unknown"
                    }
                    
                    print(f"Found accepted submission: {submission_id}")
                    break
            except Exception as e:
                print(f"Error processing row: {str(e)}")
                continue
        
        if not submission_id:
            print("No accepted submissions found")
            driver.quit()
            return None, None
        
        # Navigate directly to the submission page
        submission_url = f"https://codeforces.com/contest/{contest_id}/submission/{submission_id}"
        print(f"Navigating to submission page: {submission_url}")
        driver.get(submission_url)
        
        # Wait for the page to load
        print("Waiting for submission page to load...")
        time.sleep(3)  # Give the page some time to fully load
        
        # Try multiple methods to extract the source code
        code = None
        
        # Method 1: Try to find the element directly
        try:
            print("Trying to find source code element directly...")
            WebDriverWait(driver, 10).until(
                EC.presence_of_element_located((By.ID, "program-source-text"))
            )
            code_element = driver.find_element(By.ID, "program-source-text")
            code = code_element.text
            if code:
                print("Successfully extracted code using direct element method")
        except Exception as e:
            print(f"Direct element method failed: {str(e)}")
        
        # Method 2: Parse the HTML content to find the code
        if not code:
            try:
                print("Trying to extract code by parsing HTML...")
                html_content = driver.page_source
                code = extract_code_from_html(html_content)
                if code:
                    print("Successfully extracted code by parsing HTML")
            except Exception as e:
                print(f"HTML parsing method failed: {str(e)}")
        
        # Method 3: Try to use the copy button
        if not code:
            try:
                print("Trying to use the copy button...")
                # Find the copy button by its attributes
                copy_buttons = driver.find_elements(By.CSS_SELECTOR, "div.source-copier")
                if not copy_buttons:
                    copy_buttons = driver.find_elements(By.CSS_SELECTOR, "div[data-clipboard-target='#program-source-text']")
                
                if copy_buttons:
                    print(f"Found {len(copy_buttons)} copy buttons")
                    # Click the first copy button
                    ActionChains(driver).move_to_element(copy_buttons[0]).click().perform()
                    print("Clicked copy button")
                    
                    # Since we can't access clipboard in headless mode, we'll try to get the code again
                    code_element = driver.find_element(By.ID, "program-source-text")
                    code = code_element.text
                    if code:
                        print("Successfully extracted code after clicking copy button")
            except Exception as e:
                print(f"Copy button method failed: {str(e)}")
        
        # Method 4: Look for any pre elements that might contain the code
        if not code:
            try:
                print("Looking for any pre elements that might contain the code...")
                pre_elements = driver.find_elements(By.TAG_NAME, "pre")
                for pre in pre_elements:
                    # Skip small elements that are likely not the code
                    if len(pre.text) > 100:  # Arbitrary threshold
                        code = pre.text
                        print("Found potential code in a pre element")
                        break
            except Exception as e:
                print(f"Pre element search failed: {str(e)}")
        
        # If we still don't have the code, save the page source for debugging
        if not code:
            try:
                debug_file = "page_source.html"
                with open(debug_file, "w", encoding="utf-8") as f:
                    f.write(driver.page_source)
                print(f"Page source saved to {debug_file} for debugging")
                
                # Take a screenshot too
                screenshot_path = "page_screenshot.png"
                driver.save_screenshot(screenshot_path)
                print(f"Screenshot saved to {screenshot_path}")
            except Exception as e:
                print(f"Failed to save debug info: {str(e)}")
        
        # Close the browser
        driver.quit()
        
        return submission_info, code
        
    except Exception as e:
        print(f"Error with Selenium: {str(e)}")
        if driver:
            # Take a screenshot for debugging
            try:
                screenshot_path = "error_screenshot.png"
                driver.save_screenshot(screenshot_path)
                print(f"Error screenshot saved to {screenshot_path}")
                
                # Save page source for debugging
                with open("error_page_source.html", "w", encoding="utf-8") as f:
                    f.write(driver.page_source)
            except:
                pass
                
            driver.quit()
        return None, None

def main():
    try:
        # We'll still use the login function to verify cookies, but use Selenium for fetching
        session = login_to_cf()
        print("Successfully logged in using browser cookies!")
    except Exception as e:
        print(e)
        print("\nTo export cookies from Firefox:")
        print("1. Install the 'Cookie-Editor' extension")
        print("2. Go to codeforces.com (while logged in)")
        print("3. Click the Cookie-Editor icon and select 'Export' (as JSON)")
        print("4. Save the exported JSON to 'codeforces_cookies.json' in the same directory as this script")
        return

    problem_id = input("Enter Codeforces problem ID (e.g., 2069F): ").strip().upper()
    
    # Validate problem ID format
    if not re.match(r'^\d+[A-Z]$', problem_id):
        print("Invalid problem ID format. Use format like '2069F'.")
        return
    
    print(f"Looking for top accepted solution for problem {problem_id}...")
    
    # Use Selenium to get the solution
    submission_info, code = get_solution_with_selenium(problem_id)
    
    if submission_info:
        print("\nSubmission Details:")
        print("-" * 80)
        print(f"ID:      {submission_info['id']}")
        print(f"When:    {submission_info['when']}")
        print(f"Who:     {submission_info['who']}")
        print(f"Problem: {submission_info['problem']}")
        print(f"Lang:    {submission_info['lang']}")
        print(f"Verdict: {submission_info['verdict']}")
        print(f"Time:    {submission_info['time']}")
        print(f"Memory:  {submission_info['memory']}")
        print("-" * 80)
    
    if code:
        print("\n" + "="*50)
        print(f"Top Accepted Solution for {problem_id}:")
        print("="*50)
        print(code)
        
        # Save the code to a file as well
        try:
            filename = f"solution_{problem_id}.txt"
            with open(filename, 'w', encoding='utf-8') as f:
                f.write(code)
            print(f"\nSolution saved to {filename}")
        except Exception as e:
            print(f"Warning: Could not save solution to file: {str(e)}")
    else:
        print(f"Failed to retrieve solution for problem {problem_id}")
    
if __name__ == "__main__":
    main()
