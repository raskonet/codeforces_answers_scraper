import gzip  # For Gzip decompression
import io  # For handling bytes as files
import json
import os
import subprocess
import time  # Import time for delays
import traceback  # For detailed error printing

import brotli  # For Brotli decompression
import cloudscraper  # Import cloudscraper
import requests  # Needed for exception handling
from bs4 import BeautifulSoup
from dotenv import load_dotenv

# Load environment variables, but we'll make CF_HANDLE optional
load_dotenv()
CF_HANDLE = os.getenv("CODEFORCES_HANDLE")

# --- Configuration ---
COOKIE_FILE = "codeforces_cookies.json"
REQUEST_DELAY = 2
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
# --- End Configuration ---


def create_session():
    """Creates a cloudscraper session with necessary headers."""
    print("Creating cloudscraper session...")
    session = cloudscraper.create_scraper(
        browser={"browser": "chrome", "platform": "windows", "mobile": False}
    )
    session.headers["User-Agent"] = USER_AGENT
    session.headers["Accept-Language"] = "en-US,en;q=0.9"
    session.headers["Accept-Encoding"] = "gzip, deflate, br"
    session.headers["Accept"] = (
        "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.9"
    )
    session.headers["Connection"] = "keep-alive"
    session.headers["Sec-Fetch-Dest"] = "document"
    session.headers["Sec-Fetch-Mode"] = "navigate"
    session.headers["Sec-Fetch-Site"] = "none"
    session.headers["Sec-Fetch-User"] = "?1"
    session.headers["Upgrade-Insecure-Requests"] = "1"
    session.headers["Referer"] = "https://codeforces.com/"
    print("Session created.")
    return session


# **** UPDATED HELPER FUNCTION FOR DECOMPRESSION AND DECODING ****
def get_decoded_html(response):
    """Attempts to decompress (Brotli, Gzip) and decode the response content."""
    content_bytes = response.content
    encoding_type = response.headers.get("Content-Encoding", "").lower()
    html_text = None

    print(
        f"Attempting to decode/decompress content with detected encoding: '{encoding_type}'"
    )

    try:
        if "br" in encoding_type:
            print("Attempting Brotli decompression...")
            decompressed_bytes = brotli.decompress(content_bytes)
            print("Successfully decompressed Brotli content.")
        elif "gzip" in encoding_type:
            print("Attempting Gzip decompression...")
            with io.BytesIO(content_bytes) as bio:
                with gzip.GzipFile(fileobj=bio, mode="rb") as gz:
                    decompressed_bytes = gz.read()
            print("Successfully decompressed Gzip content.")
        else:
            print("No known compression detected ('br' or 'gzip'). Using raw bytes.")
            decompressed_bytes = content_bytes

        guessed_encoding = response.apparent_encoding or "utf-8"
        print(f"Attempting to decode bytes using encoding: '{guessed_encoding}'")
        html_text = decompressed_bytes.decode(guessed_encoding, errors="replace")
        print("Successfully decoded bytes to text.")
        return html_text

    except brotli.error as br_err:
        print(f"Brotli decompression failed: {br_err}")
    except (gzip.BadGzipFile, OSError, EOFError) as gz_err:
        print(f"Gzip decompression failed: {gz_err}")
    except Exception as e:
        print(f"Unexpected error during decompression/decoding: {e}")
        traceback.print_exc()

    if html_text is None:
        print(
            "Decompression/decoding failed. Falling back to direct UTF-8 decode of original bytes."
        )
        try:
            html_text = content_bytes.decode("utf-8", errors="replace")
            print(
                "Fallback decode as UTF-8 successful (might still be incorrect if data was compressed)."
            )
            return html_text
        except Exception as decode_err:
            print(f"Fallback UTF-8 decode failed: {decode_err}")
            print("All decoding attempts failed. Returning None.")
            return None  # Changed from returning raw bytes snippet

    return html_text  # Should only return successfully decoded text or None


def login_to_cf(session):
    """Loads cookies and attempts to verify login."""
    if not os.path.exists(COOKIE_FILE):
        raise Exception(f"Cookie file '{COOKIE_FILE}' not found...")
    loaded_cookies_count = 0
    try:
        print(f"Loading cookies from '{COOKIE_FILE}'...")
        with open(COOKIE_FILE, "r", encoding="utf-8") as f:
            cookies_list = json.load(f)
        if not isinstance(cookies_list, list):
            raise TypeError("Cookie file should contain a JSON list/array...")
        for cookie in cookies_list:
            if (
                isinstance(cookie, dict)
                and "name" in cookie
                and "value" in cookie
                and "domain" in cookie
            ):
                domain = cookie["domain"]
                if domain and not domain.startswith("."):
                    if domain.count(".") == 1 and not domain.startswith("."):
                        domain = "." + domain
                session.cookies.set(
                    cookie["name"],
                    cookie["value"],
                    domain=domain,
                    path=cookie.get("path", "/"),
                    secure=cookie.get("secure", False),
                )
                loaded_cookies_count += 1
            else:
                print(f"  Skipping invalid cookie entry...")
        if loaded_cookies_count > 0:
            print(f"Successfully loaded {loaded_cookies_count} cookies...")
        else:
            print("Warning: No valid cookies loaded.")
    except Exception as e:
        raise Exception(f"Error loading cookies: {str(e)}")

    # --- Verification Part ---
    print("Attempting to verify login by fetching settings page...")
    verify_url = "https://codeforces.com/settings/general"
    try:
        response = session.get(verify_url, timeout=30)
        print(f"Raw response headers: {response.headers}")
        response.raise_for_status()
        print(f"Login test page status code: {response.status_code}")

        html = get_decoded_html(response)
        if html is None:
            raise Exception(
                f"Failed to decompress/decode response content for login check."
            )

        print(
            f"\n--- Login Page Content Snippet (First 1500 chars, AFTER DECODE/DECOMPRESS) ---"
        )
        printable_snippet = "".join(
            c if c.isprintable() or c.isspace() else "?" for c in html[:1500]
        )
        print(f"'''\n{printable_snippet}...\n'''")
        print(f"--- End Snippet ---\n")

        soup = BeautifulSoup(html, "html.parser")
        header_links = soup.select("div.lang-chooser a, #header-menu ul li a")
        header_link_texts = [a.text.strip() for a in header_links if a.text]
        print(f"Detected texts in header/chooser links: {header_link_texts}")
        user_handle_element = soup.select_one('#header a[href*="/profile/"]')
        detected_handle = (
            user_handle_element.text.strip() if user_handle_element else "Not Found"
        )
        print(f"Detected user handle in header profile link: {detected_handle}")
        found_logout = any("Logout" in text for text in header_link_texts)
        is_expected_user = False
        if (
            CF_HANDLE
            and detected_handle != "Not Found"
            and detected_handle.lower() == CF_HANDLE.lower()
        ):
            is_expected_user = True
            print(f"Handle matches expected.")
        elif detected_handle != "Not Found" and CF_HANDLE:
            print(f"Warning: Handle '{detected_handle}' != expected '{CF_HANDLE}'.")
        if found_logout or is_expected_user:
            print("Login verification successful!")
            return session
        else:
            found_login_register = any(
                text in ["Enter", "Register"] for text in header_link_texts
            )
            login_form = soup.find("form", action="/enter")
            if found_login_register or login_form:
                raise Exception("Login failed: Received login/register page content...")
            elif "<title>Just a moment...</title>" in html:
                raise Exception(
                    "Login failed: Blocked by Cloudflare (Interstitial page detected)."
                )
            else:
                print("\n--- Login Check Debug Info ---")
                print(f"Found 'Logout'?: {found_logout}")
                print(
                    f"Handle matched?: {is_expected_user} (Det: {detected_handle}, Exp: {CF_HANDLE})"
                )
                print(f"Found 'Enter'/'Register'?: {found_login_register}")
                print(f"Found login form?: {'Yes' if login_form else 'No'}")
                print("--- End Debug Info ---\n")
                raise Exception(
                    f"Login failed: Could not confirm login. Page content checks failed. Page start: {printable_snippet}..."
                )
    except cloudscraper.exceptions.CloudflareException as e:
        raise Exception(f"Login failed: Cloudflare challenge failed. {e}")
    except requests.exceptions.RequestException as e:
        raise Exception(f"Login failed: Network error. {e}")
    except Exception as e:
        print("Traceback:")
        traceback.print_exc()
        raise Exception(f"Login failed: Unexpected error. {e}")


def get_problem_samples(session, contest_id, problem_index):
    url = f"https://codeforces.com/problemset/problem/{contest_id}/{problem_index}"
    print(f"Fetching samples from: {url}")
    try:
        time.sleep(REQUEST_DELAY)
        response = session.get(url, timeout=30)
        response.raise_for_status()

        html = get_decoded_html(response)
        if html is None:
            print("Error: Failed to decompress/decode response content for samples.")
            return None

        if (
            "<title>Just a moment...</title>" in html
            or "Checking if the site connection is secure" in html
        ):
            print(
                "Warning: Received Cloudflare interstitial page when fetching samples."
            )
            return []

        soup = BeautifulSoup(html, "html.parser")
        inputs = []
        outputs = []
        sample_tests_div = soup.find("div", class_="sample-test")
        if not sample_tests_div:
            input_divs = soup.find_all("div", class_="input")
            output_divs = soup.find_all("div", class_="output")
            print("Using fallback method.")
        else:
            input_divs = sample_tests_div.find_all("div", class_="input")
            output_divs = sample_tests_div.find_all("div", class_="output")
            print("Using preferred container.")

        if not input_divs:
            print("Warning: No input cases found.")
        for inp in input_divs:
            pre = inp.find("pre")
            if pre:
                text_content = []
                for element in pre.contents:
                    if isinstance(element, str):
                        text_content.append(element.strip())
                    elif element.name == "div":
                        text_content.append(element.get_text().strip())
                    elif element.name == "br":
                        text_content.append("\n")
                    else:
                        text_content.append(element.get_text().strip())
                full_text = "\n".join(filter(None, text_content))
                inputs.append(
                    full_text.replace("\r\n", "\n").replace("\r", "\n").strip()
                )

        if not output_divs:
            print("Warning: No output cases found.")
        for out in output_divs:
            pre = out.find("pre")
            if pre:
                outputs.append(
                    pre.get_text(separator="\n", strip=True)
                    .replace("\r\n", "\n")
                    .replace("\r", "\n")
                    .strip()
                )

        if not inputs or not outputs:
            print("Warning: Failed to extract inputs/outputs.")
            return []
        if len(inputs) != len(outputs):
            print(f"Warning: Unequal inputs/outputs...")
            min_len = min(len(inputs), len(outputs))
            return list(zip(inputs[:min_len], outputs[:min_len]))
        return list(zip(inputs, outputs))
    except cloudscraper.exceptions.CloudflareException as e:
        print(f"Error: Cloudflare challenge failed. {e}")
        return []
    except requests.exceptions.RequestException as e:
        print(f"Error: Network error {e}")
        return []
    except Exception as e:
        print(f"Error: Unexpected error.")
        traceback.print_exc()
        return None


def get_solution_code(session, contest_id, problem_index):
    status_url = (
        f"https://codeforces.com/problemset/status/{contest_id}/problem/{problem_index}"
    )
    print(f"Fetching status page: {status_url}")
    try:
        time.sleep(REQUEST_DELAY)
        response = session.get(status_url, timeout=30)
        response.raise_for_status()

        html = get_decoded_html(response)
        if html is None:
            print(
                "Error: Failed to decompress/decode response content for status page."
            )
            return None

        if (
            "<title>Just a moment...</title>" in html
            or "Checking if the site connection is secure" in html
        ):
            print(
                "Warning: Received Cloudflare interstitial page when fetching status."
            )
            return None

        soup = BeautifulSoup(html, "html.parser")
        rows = soup.select("table.status-frame-datatable tr[data-submission-id]")
        if not rows:
            print("Warning: No submission rows found...")
            return None
        print(f"Found {len(rows)} submissions...")
        for row in rows:
            cells = row.find_all("td")
            if len(cells) < 8:
                continue

            submission_id = row.get("data-submission-id")

            # ***** CORRECTED SYNTAX HERE *****
            if not submission_id:
                id_link = cells[0].find("a")
                if id_link and id_link.text.strip().isdigit():
                    submission_id = id_link.text.strip()
                else:
                    print(f"Warning: Could not extract submission ID from row.")
                    continue  # Skip this row if ID can't be found
            # ***** END CORRECTION *****

            verdict_cell = cells[5]
            lang_cell = cells[4]
            if verdict_cell and lang_cell:
                verdict_span = verdict_cell.find("span", class_="verdict-accepted")
                verdict_text = verdict_cell.get_text(strip=True).lower()
                lang_text = lang_cell.get_text(strip=True).lower()
                is_accepted = verdict_span or "accepted" in verdict_text
                is_python = "python" in lang_text
                if is_accepted and is_python:
                    print(f"Found accepted Python submission: ID {submission_id}...")
                    fetched_code = fetch_submission_code(
                        session, contest_id, submission_id
                    )
                    if fetched_code:
                        return fetched_code  # Return first successful one
                    else:
                        print(f"Failed fetch for {submission_id}, continuing...")
                        continue
                        # Continue searching
        print("No accepted Python solution found/fetched successfully.")
        return None
    except cloudscraper.exceptions.CloudflareException as e:
        print(f"Error: Cloudflare challenge failed. {e}")
        return None
    except requests.exceptions.RequestException as e:
        print(f"Error: Network error {e}")
        return None
    except Exception as e:
        print(f"Error: Unexpected error.")
        traceback.print_exc()
        return None


def fetch_submission_code(session, contest_id, submission_id):
    sub_url = f"https://codeforces.com/contest/{contest_id}/submission/{submission_id}"
    print(f"Fetching submission code from: {sub_url}")
    try:
        time.sleep(REQUEST_DELAY)
        response = session.get(sub_url, timeout=30)
        response.raise_for_status()

        html = get_decoded_html(response)
        if html is None:
            print(
                f"Error: Failed to decompress/decode response content for submission {submission_id}."
            )
            return None

        if (
            "<title>Just a moment...</title>" in html
            or "Checking if the site connection is secure" in html
        ):
            print(
                f"Warning: Received Cloudflare interstitial page when fetching submission {submission_id}."
            )
            return None

        soup = BeautifulSoup(html, "html.parser")
        code_pre = soup.find("pre", id="program-source-text")
        if not code_pre:
            print(f"Warning: ID selector failed...")
            code_pre = soup.find("pre", class_="prettyprint")
        if not code_pre:
            print(f"Error: Could not find code block...")
            return None
        elif not soup.find("pre", id="program-source-text"):
            print("Found code using fallback.")
        code = code_pre.get_text(separator="\n").strip()
        code = code.replace("\r\n", "\n").replace("\r", "\n")
        if not code or "source code is unavailable" in code.lower():
            print(f"Warning: Code empty/unavailable.")
            return None
        return code
    except cloudscraper.exceptions.CloudflareException as e:
        print(f"Error: Cloudflare challenge failed. {e}")
        return None
    except requests.exceptions.RequestException as e:
        print(f"Error: Network error {e}")
        return None
    except Exception as e:
        print(f"Error: Unexpected error.")
        traceback.print_exc()
        return None


def test_solution(code, samples):
    if not code:
        print("Error: No code provided...")
        return False
    if not samples:
        print("Warning: No samples provided...")
        return True
    temp_file_path = "temp_solution.py"
    try:
        with open(temp_file_path, "w", encoding="utf-8") as f:
            f.write(code)
    except IOError as e:
        print(f"Error: Could not write temp file: {e}")
        return False
    print("-" * 20)
    print("Running samples...")
    all_passed = True
    for i, (input_data, expected_output) in enumerate(samples):
        print(f"--- Sample {i+1} ---")
        try:
            process = subprocess.run(
                ["python3", temp_file_path],
                input=input_data.encode("utf-8"),
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=5,
            )
            actual_stdout = process.stdout.decode("utf-8", errors="ignore")
            actual_stderr = process.stderr.decode("utf-8", errors="ignore")
            actual_normalized = normalize_output(actual_stdout)
            expected_normalized = normalize_output(expected_output)
            print(
                f"Input:\n{input_data}\n-------\nExpected:\n{expected_normalized}\n-------\nActual:\n{actual_normalized}\n-------"
            )
            if process.returncode != 0:
                print(f"Status: Runtime Error (Code: {process.returncode})")
                all_passed = False
                print(f"Stderr:\n{actual_stderr.strip()}")
            elif actual_normalized == expected_normalized:
                print("Status: Passed")
            else:
                print("Status: Failed (Wrong Answer)")
                all_passed = False
            if actual_stderr and process.returncode == 0:
                print(f"Warning: Stderr produced:\n{actual_stderr.strip()}")
        except subprocess.TimeoutExpired:
            print("Status: Time Limit Exceeded")
            all_passed = False
        except FileNotFoundError:
            print(f"Error: 'python3' not found.")
            return False
        except Exception as e:
            print(f"Error testing sample {i+1}: {e}")
            traceback.print_exc()
            all_passed = False
    try:
        os.remove(temp_file_path)
        print(f"Removed temp file.")
    except OSError as e:
        print(f"Warning: Could not remove temp file: {e}")
    print("-" * 20)
    return all_passed


def normalize_output(output):
    lines = [line.strip() for line in output.strip().splitlines()]
    return "\n".join(filter(None, lines))


def main():
    session = None
    try:
        session = create_session()
        login_to_cf(session)
        print("Cookie loading/verification step completed.")
    except Exception as e:
        print(f"\n******************* ERROR *******************")
        print(f"Error during initial setup: {e}")
        print(f"*********************************************\n")
        print(
            "Please ensure prerequisites are met (connectivity, cookies, brotli installed, etc.)."
        )
        return

    while True:
        try:
            problem_id_input = (
                input("Enter Codeforces problem ID (e.g., 1850A, or 'quit'): ")
                .strip()
                .upper()
            )
            if problem_id_input == "QUIT":
                break
            if len(problem_id_input) < 2 or not problem_id_input[-1].isalpha():
                print("Invalid format.")
                continue
            problem_index = problem_id_input[-1]
            contest_id = problem_id_input[:-1]
            if not contest_id:
                print("Invalid ID: Missing contest.")
                continue

            print(f"\n======= Processing Problem: {contest_id}{problem_index} =======")

            print("\nFetching problem samples...")
            samples = get_problem_samples(session, contest_id, problem_index)
            if samples is None:
                print("Critical error fetching samples. Skipping problem.")
                continue
            elif not samples:
                print(
                    "Could not fetch/find samples. Attempting solution search anyway..."
                )
            else:
                print(f"Found {len(samples)} samples.")

            print("\nSearching for an accepted Python solution...")
            code = get_solution_code(session, contest_id, problem_index)
            if not code:
                print("No accepted Python solution found/fetched. Skipping problem.")
                continue

            print("\nFound a potential solution. Testing against samples...")
            if not samples:
                print("No samples were found/fetched, cannot test automatically.")
                print(
                    "=" * 50
                    + f"\nAccepted Python Solution Code for {contest_id}{problem_index} (Untested):\n"
                    + "=" * 50
                )
                print(code)
                print("=" * 50)
            else:
                solution_passed = test_solution(code, samples)
                if solution_passed:
                    print("\nSolution passed all provided samples!")
                    print(
                        "=" * 50
                        + f"\nAccepted Python Solution Code for {contest_id}{problem_index}:\n"
                        + "=" * 50
                    )
                    print(code)
                    print("=" * 50)
                else:
                    print("\nSolution failed one or more samples.")

            print(f"======= Finished Problem: {contest_id}{problem_index} =======")
            print("\n")

        except KeyboardInterrupt:
            print("\nExiting (Ctrl+C).")
            break
        except Exception as e:
            print("\n!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!")
            print(f"An unexpected error occurred in the main loop:")
            traceback.print_exc()
            print("!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!\n")
            print("Trying to continue...")

    print("Exiting script.")


if __name__ == "__main__":
    main()
