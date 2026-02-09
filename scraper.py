import re
from urllib.parse import urlparse, urljoin, urldefrag
from bs4 import BeautifulSoup

def scraper(url, resp):
    if resp.status != 200:
        return []
    
    links = extract_next_links(url, resp)
    return [link for link in links if is_valid(link)]

def extract_next_links(url, resp):
    # Implementation required.
    # url: the URL that was used to get the page
    # resp.url: the actual url of the page
    # resp.status: the status code returned by the server. 200 is OK, you got the page. Other numbers mean that there was some kind of problem.
    # resp.error: when status is not 200, you can check the error here, if needed.
    # resp.raw_response: this is where the page actually is. More specifically, the raw_response has two parts:
    #         resp.raw_response.url: the url, again
    #         resp.raw_response.content: the content of the page!
    # Return a list with the hyperlinks (as strings) scrapped from resp.raw_response.content

    links = []

    if not resp or resp.status != 200 or not resp.raw_response:
        return links
    
    raw = resp.raw_response

    content_type = raw.headers.get("Content-Type", "").lower()
    if "text/html" not in content_type:
        return links
    
    content = raw.content
    # Large content
    if len(content) > 5000000:
        return links
    # Little content
    if len(content) < 400:
        return links
    
    html = BeautifulSoup(resp.raw_response.content, 'html.parser')
    html_links = html.find_all("a", href=True)

    for tag in html_links:
        href = tag.get("href")
        if not href or href == "#":
            continue
        try:
            absolute_url = urljoin(url, href)
            clean_url, _ = urldefrag(absolute_url)
            if is_calendar(clean_url):
                continue
            if is_valid(clean_url):
                links.append(clean_url)
        except Exception as e:
            print(f"Error parsing {href}: {e}")
            continue
    return links

def is_valid(url):
    # Decide whether to crawl this url or not. 
    # If you decide to crawl it, return True; otherwise return False.
    # There are already some conditions that return False.
    try:
        parsed = urlparse(url)
        if parsed.scheme not in set(["http", "https"]):
            return False
        
        if not parsed.hostname:
            return False
        
        allowed_domains = (".ics.uci.edu", ".cs.uci.edu", ".informatics.uci.edu", ".stat.uci.edu")
        hostname = parsed.hostname.lower()
        if not hostname.endswith(allowed_domains):
            return False
            
        return not re.match(
            r".*\.(css|js|bmp|gif|jpe?g|ico"
            + r"|png|tiff?|mid|mp2|mp3|mp4"
            + r"|wav|avi|mov|mpeg|ram|m4v|mkv|ogg|ogv|pdf"
            + r"|ps|eps|tex|ppt|pptx|doc|docx|xls|xlsx|names"
            + r"|data|dat|exe|bz2|tar|msi|bin|7z|psd|dmg|iso"
            + r"|epub|dll|cnf|tgz|sha1"
            + r"|thmx|mso|arff|rtf|jar|csv"
            + r"|rm|smil|wmv|swf|wma|zip|rar|gz)$", parsed.path.lower())

    except TypeError:
        print ("TypeError for ", parsed)
        raise

# Check if the url is a calendar trap
def is_calendar():
    pass