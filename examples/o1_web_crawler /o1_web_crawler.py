import os
from firecrawl import FirecrawlApp
import json
from dotenv import load_dotenv
from openai import OpenAI
import time
from requests.exceptions import RequestException
import signal

# ANSI color codes
class Colors:
    CYAN = '\033[96m'
    YELLOW = '\033[93m'
    GREEN = '\033[92m'
    RED = '\033[91m'
    MAGENTA = '\033[95m'
    BLUE = '\033[94m'
    RESET = '\033[0m'

def timeout_handler(signum, frame):
    raise TimeoutError("Script execution timed out")

# Load environment variables
load_dotenv()

# Retrieve API keys from environment variables
firecrawl_api_key = os.getenv("FIRECRAWL_API_KEY")
openai_api_key = os.getenv("OPENAI_API_KEY")

# Initialize the FirecrawlApp and OpenAI client
app = FirecrawlApp(api_key=firecrawl_api_key)
client = OpenAI(api_key=openai_api_key)

# Find the page that most likely contains the objective
def find_relevant_page_via_map(objective, url, app, client):
    try:
        print(f"{Colors.CYAN}Understood. The objective is: {objective}{Colors.RESET}")
        print(f"{Colors.CYAN}Initiating search on the website: {url}{Colors.RESET}")
        
        map_prompt = f"""
        The map function generates a list of URLs from a website and it accepts a search parameter. Based on the objective of: {objective}, come up with a 1-2 word search parameter that will help us find the information we need. Only respond with 1-2 words nothing else.
        """

        print(f"{Colors.YELLOW}Analyzing objective to determine optimal search parameter...{Colors.RESET}")
        completion = client.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "text",
                            "text": map_prompt
                        }
                    ]
                }
            ]
        )

        map_search_parameter = completion.choices[0].message.content
        print(f"{Colors.GREEN}Optimal search parameter identified: {map_search_parameter}{Colors.RESET}")

        print(f"{Colors.YELLOW}Mapping website using the identified search parameter...{Colors.RESET}")
        map_website = app.map_url(url, params={"search": map_search_parameter})
        print(f"{Colors.GREEN}Website mapping completed successfully.{Colors.RESET}")
        print(f"{Colors.GREEN}Located {len(map_website)} relevant links.{Colors.RESET}")
        return map_website
    except Exception as e:
        print(f"{Colors.RED}Error encountered during relevant page identification: {str(e)}{Colors.RESET}")
        return None
    
# Scrape the top 3 pages and see if the objective is met, if so return in json format else return None
def find_objective_in_top_pages(map_website, objective, app, client):
    all_vendors = []
    output_file = 'o1_web_crawler_results.json'
    
    # Load existing data if the file exists
    if os.path.exists(output_file):
        with open(output_file, 'r') as f:
            try:
                existing_data = json.load(f)
                all_vendors = existing_data.get('vendors', [])
            except json.JSONDecodeError:
                print(f"{Colors.YELLOW}Error reading existing file. Starting fresh.{Colors.RESET}")

    for link in map_website:
        try:
            print(f"{Colors.YELLOW}Initiating scrape of page: {link}{Colors.RESET}")
            scrape_result = app.scrape_url(link, params={'formats': ['markdown']})
            print(f"{Colors.GREEN}Page scraping completed successfully.{Colors.RESET}")
            
            check_prompt = f"""
            Given the following scraped content and objective, extract all vendor information in a simple and concise JSON format.
            Each vendor should be a separate object in an array.
            Include fields such as name, url, location, and description if available.

            Objective: {objective}
            Scraped content: {scrape_result['markdown']}

            Remember:
            1. Return JSON for all vendors found on the page.
            2. Keep the JSON structure as simple and flat as possible for each vendor.
            3. Do not include any explanations or markdown formatting in your response.
            """
            
            completion = client.chat.completions.create(
                model="gpt-3.5-turbo",
                messages=[
                    {
                        "role": "user",
                        "content": check_prompt
                    }
                ]
            )
            
            result = completion.choices[0].message.content
            
            try:
                vendors = json.loads(result)
                if isinstance(vendors, list):
                    all_vendors.extend(vendors)
                elif isinstance(vendors, dict) and 'vendors' in vendors:
                    all_vendors.extend(vendors['vendors'])
                print(f"{Colors.GREEN}Extracted {len(vendors)} vendors from this page.{Colors.RESET}")
                
                # Save results after each successful extraction
                with open(output_file, 'w') as f:
                    json.dump({"vendors": all_vendors}, f, indent=2)
                print(f"{Colors.GREEN}Updated results saved to {output_file}{Colors.RESET}")
                
            except json.JSONDecodeError:
                print(f"{Colors.RED}Error in parsing response. Proceeding to next page...{Colors.RESET}")
        
        except Exception as e:
            print(f"{Colors.RED}An error occurred while processing {link}: {str(e)}{Colors.RESET}")
    
    return all_vendors

# Main function to execute the process
def main():
    # Set a global timeout (e.g., 30 minutes)
    signal.signal(signal.SIGALRM, timeout_handler)
    signal.alarm(1800)  # 30 minutes in seconds

    try:
        # Get user input
        url = input(f"{Colors.BLUE}Enter the website to crawl: {Colors.RESET}")
        objective = input(f"{Colors.BLUE}Enter your objective: {Colors.RESET}")
        
        print(f"{Colors.YELLOW}Initiating web crawling process...{Colors.RESET}")
        # Find the relevant page
        map_website = find_relevant_page_via_map(objective, url, app, client)
        
        if map_website:
            print(f"{Colors.GREEN}Relevant pages identified. Proceeding with detailed analysis...{Colors.RESET}")
            # Find objective in top pages
            all_vendors = find_objective_in_top_pages(map_website, objective, app, client)
            
            if all_vendors:
                print(f"{Colors.GREEN}Objective successfully fulfilled. Total vendors extracted: {len(all_vendors)}{Colors.RESET}")
            else:
                print(f"{Colors.RED}No vendors found. Unable to fulfill the objective with the available information.{Colors.RESET}")
        else:
            print(f"{Colors.RED}No relevant pages identified. Consider refining the search parameters or trying a different website.{Colors.RESET}")
    except TimeoutError:
        print(f"{Colors.RED}Script execution timed out after 30 minutes.{Colors.RESET}")
    finally:
        signal.alarm(0)  # Cancel the alarm

if __name__ == "__main__":
    main()
