import requests
import json
#from backend.onyx.file_processing.html_utils import parse_html_page_basic_less_strict

def fetch_tickets():
    ticket_id = 96082
    base_url = f"https://seclore.freshdesk.com/api/v2/tickets/{ticket_id}/conversations"
    
    all_conversations = []
    page = 1
    
    while True:
        params = {
            "per_page": 30,  # Get up to 100 conversations per page
            "page": page,
        }
        
        print(f"Fetching page {page}...")
        response = requests.get(
            base_url, auth=("lBoBQJZXhcbelO1CtYrh", "Mumbai@123"), params=params
        )
        response.raise_for_status()
        
        # Check response headers for pagination info
        print(f"Response Headers for page {page}:")
        important_headers = ['link', 'x-total-count', 'x-page-count', 'x-per-page', 'x-current-page']
        for header in important_headers:
            if header in response.headers:
                print(f"{header}: {response.headers[header]}")
        
        conversations = response.json()
        
        # If no conversations returned, we've reached the end
        if not conversations or len(conversations) == 0:
            print(f"No more conversations found on page {page}")
            break
            
        all_conversations.extend(conversations)
        print(f"Found {len(conversations)} conversations on page {page}")
        
        # Check if this page has fewer conversations than requested per_page
        # This indicates it's the last page
        if len(conversations) < params["per_page"]:
            print(f"Page {page} has fewer conversations than per_page limit - this is the last page")
            break
            
        # Check for Link header which indicates more pages
        link_header = response.headers.get('link', '')
        if 'rel="next"' not in link_header:
            print("No 'next' link found in Link header - this is the last page")
            break
            
        page += 1
        print(f"Moving to page {page}")
        print("-" * 50)
    
    print(f"\nFinal Results:")
    print(f"Total pages fetched: {page}")
    print(f"Total conversations collected: {len(all_conversations)}")
    
    # Display first few conversations as sample
    if all_conversations:
        print(f"\nFirst conversation sample:")
        print(json.dumps(all_conversations[0], indent=2))
    
    return all_conversations

def main():
    fetch_tickets()
 
if __name__ == "__main__":
    main()
 
 