import gspread
from google.oauth2.service_account import Credentials
from playwright.sync_api import sync_playwright
import time

# Authenticate and open the Google Sheet
scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
creds = Credentials.from_service_account_file("Client1.json", scopes=scope)
client = gspread.authorize(creds)

# Open the Google Sheet
sheet = client.open("BettingExpert").worksheet("EuroLeague")

# Get the list of rows from the sheet
rows = sheet.get_all_values()

# Create a list of clubs starting from the first empty "Result Club 1" row
clubs = []
start_index = 1  # Start from the second row (index 1)

# Find the first empty row in "Result Club 1" - row[2]
for idx, row in enumerate(rows[start_index:], start_index):
    if row[2] == "":
        start_index = idx
        break

# Create a list of clubs from the first empty "Result Club 1" row
for row in rows[start_index:]:
    clubs.append(row[0])

def is_crossed_out(element):
    # Check if the element has a class indicating it's crossed out
    class_name = element.get_attribute("class")
    return "line-through" in class_name

def run(playwright, clubs, start_index, sheet):
    # Launch the browser
    browser = playwright.chromium.launch(headless=False)
    context = browser.new_context()
    page = context.new_page()

    # Iterate over each club
    for club in clubs:
        club_index = clubs.index(club) + start_index + 1  # Adjust for 1-based index and header row

        # Navigate to the results page
        page.goto("https://www.oddsportal.com/basketball/europe/euroleague/results/")
        
        try:
            # Accept the cookie consent if present
            page.wait_for_selector("#onetrust-accept-btn-handler", timeout=5000)
            page.click("#onetrust-accept-btn-handler")
        except:
            pass

        # Find all links with the club's name
        club_links = page.query_selector_all(f'a:has-text("{club}")')

        if club_links:
            # Click the first link found
            club_links[0].click()
        else:
            print(f"No links found for team {club}.")
            continue

        # Wait for the page to load
        page.wait_for_load_state("networkidle")

        # Select elements that display the results
        home_score_element = page.query_selector('div.max-mm\\:gap-2.flex.items-center.justify-end > div.text-gray-dark')
        away_score_element = page.query_selector('div.max-mm\\:order-last.max-mm\\:gap-2.order-first.flex > div.flex-center.text-gray-dark')

        # Get the scores
        away_score = away_score_element.inner_text() if away_score_element else "No result found"
        home_score = home_score_element.inner_text() if home_score_element else "No result found"

        print(f"Home score for {club}: {home_score}, Away score: {away_score}")

        # Update the Google Sheet with the scores
        sheet.update_cell(club_index, 3, home_score)
        sheet.update_cell(club_index, 4, away_score)

        # Find the div element containing "Asian Handicap"
        asian_handicap_element = page.query_selector('span.flex:has(div:has-text("Asian Handicap"))')

        if asian_handicap_element:
            # Click the Asian Handicap element
            asian_handicap_element.click()
            print(f"Clicked on Asian Handicap for {club}.")
        else:
            print(f"Asian Handicap element not found for {club}.")

        try:
            # Wait for the elements to appear
            page.wait_for_selector('p[data-v-08a44f4e][class="height-content !text-black-main next-m:min-w-[100%] flex-center min-h-full min-w-[50px] hover:!bg-gray-medium default-odds-bg-bgcolor border gradient-green-added-border"]', timeout=5000)
        except TimeoutError:
            print("Elements not found in the expected time.")

        # Find all elements that contain the odds
        elements = page.query_selector_all('p[data-v-08a44f4e][class="height-content !text-black-main next-m:min-w-[100%] flex-center min-h-full min-w-[50px] hover:!bg-gray-medium default-odds-bg-bgcolor border gradient-green-added-border"]')

        # Initialize an empty list to store float values
        all_values = []

        # Iterate through the found elements
        for element in elements:
            text = element.inner_text()
            for number in text.split():
                if number == '-':
                    # Convert '-' to the number 10
                    float_number = 10.0
                else:
                    try:
                        # Convert the text to a float value
                        float_number = float(number)
                    except ValueError:
                        print(f"Could not convert '{number}' to float.")
                        continue  # Skip this value if conversion is not possible
                all_values.append(float_number)

        # Create a new list that includes every other element from all_values
        all_values = all_values[::2]
        # Print the result
        print(all_values)

        def find_closest_index(all_values, target):
            closest_odd = None
            closest_distance = float('inf')
            closest_index = None

            # Find the closest value to the target in the list
            for index, t in enumerate(all_values):
                distance = abs(t - target)
                if distance < closest_distance:
                    closest_distance = distance
                    closest_odd = t
                    closest_index = index

            return closest_odd, closest_index

        def extract_bet365_values(page):
            # Find the row containing 'bet365'
            bet365_row = page.query_selector("div[data-v-21fd171a]:has-text('bet365')")
            if bet365_row:
                # Extract values based on their specific positions and structure
                handicap_element = bet365_row.query_selector("[provider-name]")
                value_1_element = bet365_row.query_selector("div:nth-child(3) .height-content")
                value_2_element = bet365_row.query_selector("div:nth-child(4) .height-content")
                payout_element = bet365_row.query_selector("div:nth-child(5) .height-content")

                # Check if any of the elements are crossed out
                if any(is_crossed_out(el) for el in [handicap_element, value_1_element, value_2_element, payout_element]):
                    return None

                # Get the text content or attributes of the elements
                handicap = handicap_element.get_attribute("provider-name")
                value_1 = value_1_element.inner_text()
                value_2 = value_2_element.inner_text()
                payout = payout_element.inner_text()

                print(f"Handicap: {handicap}")
                print(f"1st Value: {value_1}")
                print(f"2nd Value: {value_2}")
                print(f"Payout: {payout}")
                return handicap, value_1, value_2, payout
            else:
                print("bet365 row not found")
                return None

        def find_and_click_closest(asian_handicap_elements, closest_index):
            # Click the closest Asian Handicap element
            if closest_index is not None and closest_index < len(asian_handicap_elements):
                target_element = asian_handicap_elements[closest_index]
                target_element.click()
                print(f"Clicked on Asian Handicap at index {closest_index}.")
                time.sleep(20)
                return True
            return False

        def main(page, all_values):
            target = 1.91
            remaining_values = all_values.copy()
            
            # Try up to 5 times to find and click the closest value
            for _ in range(5):
                closest_odd, closest_index = find_closest_index(remaining_values, target)
                
                if closest_index is not None:
                    print("Closest number to 1.91 is:", closest_odd, "at position", closest_index, "in the list.")
                    
                    asian_handicap_elements = page.query_selector_all('div[data-v-bcfe08d6].flex.w-full.items-center.justify-start.pl-3.font-bold.text-\\[\\#2F2F2F\\]')
                    if find_and_click_closest(asian_handicap_elements, closest_index):
                        bet365_values = extract_bet365_values(page)
                        if bet365_values:
                            print("Bet365 values:", bet365_values)
                            return bet365_values
                        else:
                            print(f"No Bet365 values found for index {closest_index}. Trying next closest value.")
                    else:
                        print(f"Invalid index {closest_index}. Trying next closest value.")
                
                remaining_values.pop(closest_index)
            
            print("No valid Bet365 values found after 5 attempts.")
            return None

        bet365_values = main(page, all_values)
        if bet365_values:
            handicap, value_1, value_2, payout = bet365_values
            # Update the Google Sheet with the bet values if they are found
            if not sheet.cell(club_index, 5).value:
                sheet.update_cell(club_index, 5, handicap)
            if not sheet.cell(club_index, 6).value:
                sheet.update_cell(club_index, 6, value_1)
            if not sheet.cell(club_index, 7).value:
                sheet.update_cell(club_index, 7, value_2)
            if not sheet.cell(club_index, 8).value:
                sheet.update_cell(club_index, 8, payout)
        
    context.close()
    browser.close()

with sync_playwright() as playwright:
    run(playwright, clubs, start_index, sheet)
