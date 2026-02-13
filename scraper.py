import re
from urllib.parse import urlparse, urljoin, urldefrag
from urllib.robotparser import RobotFileParser
from bs4 import BeautifulSoup
import json
from collections import Counter
import hashlib

checksums = set()
# Data structures to store the required information for the report
unique_pages = set()
longest_page = ("", 0)
common_words = Counter()
subdomains = {}

STOP_WORDS = {"i", "me", "my", "myself", "we", "our", "ours", "ourselves", "you", "your", "yours", "yourself", "yourselves",
              "he", "him", "his", "himself", "she", "her", "hers", "herself", "it", "its", "itself", "they", "them", "their",
              "theirs", "themselves", "what", "which", "who", "whom", "this", "that", "these", "those", "am", "is", "are", "was",
              "were", "be", "been", "being", "have", "has", "had", "having", "do", "does", "did", "doing", "a", "an", "the", "and",
              "but", "if", "or", "because", "as", "until", "while", "of", "at", "by", "for", "with", "about", "against", "between",
              "into", "through", "during", "before", "after", "above", "below", "to", "from", "up", "down", "in", "out", "on", "off",
              "over", "under", "again", "further", "then", "once", "here", "there", "when", "where", "why", "how", "all", "any", "both",
              "each", "few", "more", "most", "other", "some", "such", "no", "nor", "not", "only", "own", "same", "so", "than", "too", "very",
              "s", "t", "can", "will", "just", "don", "should", "now"}

CALENDAR_PATTERNS = [
    # The Events Calendar (WordPress)
    r"[?&]tribe-bar-date=\d{4}-\d{2}-\d{2}",
    r"[?&]eventDisplay=",
    r"[?&]tribe_event_display=",

    # Event views / pagination
    r"/events/(list|month|week|day)/",
    r"/events/list/page/\d+/?",
    r"/events/page/\d+/?",

    # Tag/date archives
    r"/events/tag/[^/]+/\d{4}-\d{2}",
    r"/events/tag/[^/]+/day/\d{4}-\d{2}",

    # Generic calendar paths
    r"/calendar/(page/\d+|month|week|day)/",
    r"/calendar/\d{4}/(\d{2}/(\d{2}/)?)?",
    r"/calendar/?$",

    # Date archives
    r"/events/\d{4}/\d{2}/(\d{2}/)?",
]

TITLE_SOFT_404_PATTERNS = [
    r"\b404\b",
    r"\bnot found\b",
    r"\berror\b",
    r"\bno results\b",
    r"\bpage not found\b",
    r"\bunavailable\b",
]

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

    global longest_page
    links = []

    if not resp or resp.status != 200 or not resp.raw_response:
        return links
    
    raw = resp.raw_response

    content_type = raw.headers.get("Content-Type", "").lower()
    if "text/html" not in content_type:
        return links
    
     # Remove the fragment from the URL and add the defragmented URL to the unique_pages set 
    defraged_url, _ = urldefrag(resp.url)
    if defraged_url not in unique_pages:
        unique_pages.add(defraged_url)
    
    # parse the url to get the hostname and check if it belongs to uci.edu, if so, add it to the subdomains dictionary
    # The subdomains dictionary should have the subdomain as the key and a set of unique pages as the value.
    parsed_url = urlparse(defraged_url)
    hostname = (parsed_url.hostname or "").lower()
    if hostname.endswith("uci.edu"):
        if hostname not in subdomains:
            subdomains[hostname] = set()
        subdomains[hostname].add(defraged_url)
    
    # Skips pages that fulfill these conditions.
    # Pages with more than 5 mbs of content are too large, skip
    # Pages with less than 400 bytes of content are too small, skip
    content = raw.content
    # Large content
    if len(content) > 5000000:
        return links
    # Little content
    if len(content) < 400:
        return links
    # Exact duplicate content
    if is_exact_dupe(content):
        return links

    # make sure to pip install lxml
    # it's a better parser than html.parser
    html = BeautifulSoup(resp.raw_response.content, "lxml")
    # Check soft pages
    if is_soft_404(html):
        return links

    html_links = html.find_all("a", href=True)

    # Remove script, style, noscript, nav, and footer tags to avoid counting words in them 
    for tag in html(["script", "style", "noscript", "nav", "footer"]):
        tag.decompose()

    # Update longest_page if the current page has more words than the longest page found so far
    text = html.get_text(separator=" ", strip=True)
    words = re.findall(r"[a-zA-Z]+", text.lower())
    if len(words) > longest_page[1]:
        longest_page = (defraged_url, len(words))
    
    # Filter out stop words and update the common_words counter with the remaining words
    filter_words = [word for word in words if word not in STOP_WORDS]
    common_words.update(filter_words)

    # grabs all the hyperlinks by checking for the href element
    # skip if there's no links or self links
    # then avoids basic crawler traps
    # valid links are added into the list, then returned
    for tag in html_links:
        try:
            href = tag["href"]
            if href == "#":
                continue
            absolute_url = urljoin(url, href)
            clean_url, _ = urldefrag(absolute_url)
            links.append(clean_url)
        except Exception as e:
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
        
        # Must have hostname
        if not parsed.hostname:
            return False
        
        # Restrict domains
        allowed_domains = (".ics.uci.edu", ".cs.uci.edu", ".informatics.uci.edu", ".stat.uci.edu")
        hostname = parsed.hostname.lower()
        
        if hostname == "gitlab.ics.uci.edu":
            return False
        
        if hostname == "grape.ics.uci.edu" and "/wiki" in parsed.path.lower():
            return False
    
        if not hostname.endswith(allowed_domains):
            return False
        
        url_lower = url.lower()

        if "/~eppstein/" in parsed.path.lower() or "/~dechter/publications" in parsed.path.lower():
            return False

        # Polite crawling
        if not can_crawl(url):
            return False
        
        # Trap protections
        # length limit
        if len(url) > 250:
            return False
        
        # excessive query strings
        if parsed.query and len(parsed.query) > 100:
            return False
        
        # crawler dead ends + interaction traps
        if re.search(r"(login|logout|signin|signup|register|auth|reply|share)", url_lower):
            return False
        
        # pagination traps
        if re.search(r"(page=\d+|p=\d+)", url_lower):
            return False
        
        # calendar traps
        if is_calendar(url):
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

def can_crawl(url):
    # Ensures crawlers are polite
    # Checks robot.txt to ensure path can be crawled
    # Return True if allowed otherwise False
    parsed = urlparse(url)
    robots_url = f"{parsed.scheme}://{parsed.netloc}/robots.txt"

    rp = RobotFileParser()
    rp.set_url(robots_url)
    try:
        rp.read()
        return rp.can_fetch("*", url)
    except Exception:
        return True

def is_calendar(url):
    url_lower = url.lower()
    for pattern in CALENDAR_PATTERNS:
        if re.search(pattern, url_lower):
            return True
    return False

def is_exact_dupe(content):
    # Determines if pages have duplicate content
    # Does this through checksums hash function learned in class
    # If it's been seen before, add it to a set for future checks and return True
    # Otherwise, False
    digest = hashlib.md5(content).hexdigest()
    if digest in checksums:
        return True
    checksums.add(digest)
    return False

def is_soft_404(soup):
    # Checks if the url leads to a dead page
    # 200 status code, but contains basically no data
    title = ""
    if soup.title and soup.title.string:
        title = soup.title.string.lower()
    for pattern in TITLE_SOFT_404_PATTERNS:
        if re.search(pattern, title):
            return True
    return False

# Write the JSON report to a file named "report.json" with all extracted information
def write_json_report():
    report = {
        "Number_of_unique_pages" : len(unique_pages),

        "longest_page" : {
            "url" : longest_page[0],
            "word_count" : longest_page[1]
        },

         "top_50_words": [
            {"word": word, "count": count}
            for word, count in common_words.most_common(50)
        ],

        "subdomains" : {
            "total" : len(subdomains),
            "unique_pages_per_subdomain" : [
                {
                "subdomain" : subdomain,
                "unique_pages": len(pages)
            }
            for subdomain, pages in sorted(subdomains.items())
            ]
        }
    }
    with open("report.json", "w") as f:
        json.dump(report, f, indent=4)
