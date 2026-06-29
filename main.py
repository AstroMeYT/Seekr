import sqlite3
import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse
import time
import sys
import subprocess
import os
import atexit
import zipfile
import io
import re
from collections import Counter
import threading
from prompt_toolkit import PromptSession
from prompt_toolkit.patch_stdout import patch_stdout

# ==========================================
# CONFIGURATION
# ==========================================
START_URL = "https://en.wikipedia.org/wiki/Main_Page"  # Replace with your starting URL
DB_NAME = "crawler_links.db"
DELAY_BETWEEN_REQUESTS = 1.0  # Seconds to wait between requests to prevent overloading servers
TOP_1M_URL = "http://s3-us-west-1.amazonaws.com/umbrella-static/top-1m.csv.zip"
TOP_1M_FILE = "top-1m.csv"

# Proxy Configuration
# Routing traffic through local CORS Anywhere server by default
CORS_PROXY_PREFIX = "http://localhost:8080/" 

# If your proxy acts as a standard HTTP proxy, define it here:
PROXIES = {
    # "http": "http://127.0.0.1:8010",
    # "https": "http://127.0.0.1:8010",
}

DOMAIN_RANKS = {}

# --- THREADING FLAGS ---
PAUSE_EVENT = threading.Event()
PAUSE_EVENT.set()  # set() means running (not paused)
SHUTDOWN_FLAG = threading.Event()

# Comprehensive list of stop words to filter out when extracting keywords
STOP_WORDS = {
    # --- Original stop words ---
    'the', 'and', 'is', 'in', 'it', 'of', 'to', 'a', 'that', 'for', 'on', 'with', 'as', 
    'this', 'was', 'at', 'by', 'an', 'be', 'from', 'or', 'are', 'not', 'have', 'all', 
    'but', 'which', 'their', 'has', 'one', 'you', 'about', 'more', 'if', 'we', 'out', 
    'up', 'so', 'can', 'what', 'who', 'when', 'will', 'there', 'your', 'how', 'do',

    # --- Pronouns & Possessives ---
    'i', 'me', 'my', 'myself', 'we', 'us', 'our', 'ours', 'ourselves', 'you', 'your', 
    'yours', 'yourself', 'yourselves', 'he', 'him', 'his', 'himself', 'she', 'her', 
    'hers', 'herself', 'it', 'its', 'itself', 'they', 'them', 'their', 'theirs', 
    'themselves', 'what', 'which', 'who', 'whom', 'this', 'that', 'these', 'those', 
    'am', 'is', 'are', 'was', 'were', 'be', 'been', 'being', 'have', 'has', 'had', 

    # --- Auxiliary / Modal Verbs & Common Verbs ---
    'having', 'do', 'does', 'did', 'doing', 'can', 'could', 'should', 'would', 'will', 
    'ought', 'shall', 'may', 'might', 'must', 'get', 'got', 'go', 'goes', 'went', 
    'going', 'make', 'makes', 'made', 'making', 'take', 'takes', 'took', 'taking', 
    'say', 'says', 'said', 'saying', 'see', 'sees', 'saw', 'seeing', 'use', 'uses', 
    'used', 'using', 'want', 'wants', 'know', 'knows', 'known', 'think', 'thinks',

    # --- Prepositions & Conjunctions ---
    'about', 'above', 'across', 'after', 'afterwards', 'against', 'along', 
    'amid', 'among', 'amongst', 'around', 'at', 'before', 'behind', 'below', 'beneath', 
    'beside', 'between', 'beyond', 'but', 'by', 'concerning', 'despite', 'down', 'during', 
    'except', 'for', 'from', 'in', 'inside', 'into', 'like', 'near', 'of', 'off', 'on', 
    'onto', 'out', 'outside', 'over', 'past', 'regarding', 'since', 'through', 'throughout', 
    'to', 'toward', 'towards', 'under', 'underneath', 'until', 'up', 'upon', 'with', 
    'within', 'without', 'because', 'since', 'although', 'though', 'while', 'unless', 
    'except', 'whereas', 'if', 'or', 'nor', 'yet', 'so', 'and',

    # --- Time Units & Temporal Words ---
    'time', 'times', 'second', 'seconds', 'minute', 'minutes', 'hour', 'hours', 'day', 
    'days', 'week', 'weeks', 'month', 'months', 'year', 'years', 'decade', 'decades', 
    'century', 'centuries', 'millennium', 'morning', 'afternoon', 'evening', 'night', 
    'nights', 'noon', 'midnight', 'today', 'yesterday', 'tomorrow', 'now', 'then', 
    'before', 'after', 'early', 'late', 'soon', 'ago', 'present', 'past', 'future', 
    'always', 'never', 'sometimes', 'often', 'usually', 'seldom', 'rarely', 'hourly', 
    'daily', 'weekly', 'biweekly', 'fortnightly', 'monthly', 'quarterly', 'yearly', 
    'annually', 'annual', 'current', 'currently', 'recent', 'recently', 'duration', 
    'period', 'era', 'epoch', 'age', 'moment', 'meanwhile', 'clock', 'oclock',

    # --- Days of the Week ---
    'monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday', 'sunday',
    'mon', 'tue', 'wed', 'thu', 'fri', 'sat', 'sun',

    # --- Months of the Year ---
    'january', 'february', 'march', 'april', 'may', 'june', 'july', 'august', 
    'september', 'october', 'november', 'december',
    'jan', 'feb', 'mar', 'apr', 'jun', 'jul', 'aug', 'sep', 'oct', 'nov', 'dec',

    # --- Numbers & Quantitative Words ---
    'zero', 'one', 'two', 'three', 'four', 'five', 'six', 'seven', 'eight', 'nine', 
    'ten', 'eleven', 'twelve', 'thirteen', 'fourteen', 'fifteen', 'sixteen', 
    'seventeen', 'eighteen', 'nineteen', 'twenty', 'thirty', 'forty', 'fifty', 'sixty', 
    'seventy', 'eighty', 'ninety', 'hundred', 'thousand', 'million', 'billion', 
    'first', 'second', 'third', 'fourth', 'fifth', 'sixth', 'seventh', 'eighth', 
    'ninth', 'tenth', 'once', 'twice', 'thrice', 'double', 'triple', 'single', 
    'few', 'many', 'several', 'some', 'any', 'none', 'all', 'both', 'half', 'quarter', 
    'whole', 'total', 'average', 'number', 'numbers', 'amount', 'more', 'less', 
    'least', 'most', 'such', 'other', 'others', 'another', 'each', 'every',

    # --- Miscellaneous Common / Filler Words ---
    'very', 'much', 'just', 'only', 'also', 'too', 'well', 'quite', 'rather', 'somewhat', 
    'indeed', 'really', 'actually', 'maybe', 'perhaps', 'almost', 'nearly', 'completely', 
    'even', 'still', 'again', 'already', 'else', 'either', 'neither', 'whether', 'whose', 
    'here', 'there', 'where', 'everywhere', 'nowhere', 'somewhere', 'back', 'forward', 
    'left', 'right', 'upward', 'downward', 'please', 'thanks', 'thank', 'etc', 'via', 
    'per', 'vs', 'versus', 'non', 'sub', 'co', 'ex', 'self', 'new', 'old', 'good', 
    'bad', 'best', 'worst', 'high', 'low', 'great', 'big', 'small', 'page', 'pages', 
    'site', 'website', 'link', 'links', 'web', 'online', 'http', 'https', 'www', 'com', 
    'org', 'net', 'edu', 'gov', 'html', 'pdf', 'file', 'data', 'user', 'view', 'click'
}

def load_top_domains():
    """Downloads (if necessary) and loads the top 1M domains into memory."""
    global DOMAIN_RANKS
    if not os.path.exists(TOP_1M_FILE):
        print(f"[*] Downloading top 1 million domains from {TOP_1M_URL}...")
        response = requests.get(TOP_1M_URL, timeout=30)
        response.raise_for_status()
        with zipfile.ZipFile(io.BytesIO(response.content)) as z:
            z.extractall()
        print("[*] Download and extraction complete.")
    
    print("[*] Loading domain ranks into memory (this may take a few seconds)...")
    try:
        with open(TOP_1M_FILE, 'r', encoding='utf-8') as f:
            for line in f:
                parts = line.strip().split(',')
                if len(parts) == 2:
                    rank, domain = parts
                    DOMAIN_RANKS[domain.lower()] = int(rank)
        print(f"[*] Successfully loaded {len(DOMAIN_RANKS)} domain ranks.")
    except Exception as e:
        print(f"[-] Error loading top domains: {e}")

def get_url_metrics(url):
    """Calculates domain rank and path depth for a given URL."""
    parsed = urlparse(url)
    
    # Calculate Depth (number of subdirectories)
    path_parts = [p for p in parsed.path.split('/') if p]
    depth = len(path_parts)
    
    # Calculate Rank
    netloc = parsed.netloc.lower().split(':')[0]  # Remove port if present
    if netloc.startswith('www.'):
        netloc = netloc[4:]
        
    # Default to 9,999,999 if the domain is not in the top 1M list
    rank = DOMAIN_RANKS.get(netloc, 9999999) 
    return rank, depth

# ==========================================
# DATABASE SETUP
# ==========================================
def setup_database():
    """Initializes the SQLite database, links table, and the FTS5 virtual table."""
    conn = sqlite3.connect(DB_NAME, timeout=30.0)
    conn.execute('PRAGMA journal_mode=WAL;')
    
    cursor = conn.cursor()
    # Create main relational table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS links (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            url TEXT UNIQUE NOT NULL,
            status TEXT DEFAULT 'pending', -- 'pending', 'crawling', 'crawled', or 'error'
            domain_rank INTEGER,
            depth INTEGER,
            page_title TEXT,
            keywords TEXT,
            crawl_depth INTEGER
        )
    ''')
    
    # Create the FTS5 Virtual Table for high-performance searching
    cursor.execute('''
        CREATE VIRTUAL TABLE IF NOT EXISTS links_fts USING fts5(
            link_id UNINDEXED,
            page_title,
            keywords,
            url
        );
    ''')
    
    # Run structural migrations safely
    migrations = [
        "ALTER TABLE links ADD COLUMN domain_rank INTEGER",
        "ALTER TABLE links ADD COLUMN depth INTEGER",
        "ALTER TABLE links ADD COLUMN page_title TEXT",
        "ALTER TABLE links ADD COLUMN keywords TEXT",
        "ALTER TABLE links ADD COLUMN crawl_depth INTEGER"
    ]
    for mig in migrations:
        try:
            cursor.execute(mig)
        except sqlite3.OperationalError:
            pass # Column already exists

    conn.commit()
    return conn

def add_url(cursor, url, parent_crawl_depth=None):
    """Adds a URL to the database if it doesn't already exist."""
    rank, path_depth = get_url_metrics(url)
    crawl_depth = 0 if parent_crawl_depth is None else parent_crawl_depth + 1
    
    try:
        cursor.execute('''
            INSERT OR IGNORE INTO links (url, status, domain_rank, depth, crawl_depth) 
            VALUES (?, 'pending', ?, ?, ?)
        ''', (url, rank, path_depth, crawl_depth))
        return cursor.rowcount > 0, rank, path_depth
    except sqlite3.Error as e:
        print(f"Database error while inserting {url}: {e}")
        return False, rank, path_depth

def get_total_links(cursor):
    """Returns the total number of links currently stored in the database."""
    cursor.execute("SELECT COUNT(*) FROM links")
    return cursor.fetchone()[0]

def get_next_url(cursor):
    """Retrieves the next pending URL from the database safely (BFS strategy)."""
    while True:
        cursor.execute('''
            SELECT url, domain_rank, depth, COALESCE(crawl_depth, 0) 
            FROM links 
            WHERE status = 'pending' 
            ORDER BY COALESCE(crawl_depth, 0) ASC, id ASC 
            LIMIT 1
        ''')
        row = cursor.fetchone()
        
        if not row:
            return (None, None, None, None)
        
        url, rank, depth, crawl_depth = row
        
        cursor.execute("UPDATE links SET status = 'crawling' WHERE url = ? AND status = 'pending'", (url,))
        
        if cursor.rowcount > 0:
            cursor.connection.commit()
            return row

def update_status(cursor, url, status, page_title=None, keywords=None):
    """Updates the status and synchronizes the virtual FTS5 search index."""
    if page_title or keywords:
        cursor.execute("UPDATE links SET status = ?, page_title = ?, keywords = ? WHERE url = ?", (status, page_title, keywords, url))
        
        # Get the row ID to maintain mapping with the FTS index
        cursor.execute("SELECT id FROM links WHERE url = ?", (url,))
        row = cursor.fetchone()
        if row:
            link_id = row[0]
            # Clean and update the FTS5 record
            cursor.execute("DELETE FROM links_fts WHERE link_id = ?", (link_id,))
            cursor.execute("INSERT INTO links_fts (link_id, page_title, keywords, url) VALUES (?, ?, ?, ?)", 
                           (link_id, page_title or "", keywords or "", url))
    else:
        cursor.execute("UPDATE links SET status = ? WHERE url = ?", (status, url))

def extract_keywords_weighted(soup, top_n=15):
    """Extracts keywords by applying tag multipliers based on HTML prominence."""
    # Prevent parsing styling or scripting elements
    for element in soup(["script", "style", "nav", "footer", "header", "aside"]):
        element.extract()
        
    words_counter = Counter()
    
    # Prominence Tag Multipliers
    tag_weights = {
        'title': 12,
        'h1': 10,
        'h2': 6,
        'h3': 4,
        'strong': 2,
        'b': 2,
        'p': 1,
        'li': 1
    }
    
    # Tally up weighted words
    for tag, weight in tag_weights.items():
        elements = soup.find_all(tag)
        for elem in elements:
            text = elem.get_text(separator=' ').lower()
            words = re.findall(r'\b[a-z]{3,15}\b', text)
            for word in words:
                if word not in STOP_WORDS:
                    words_counter[word] += weight
                    
    # General fallback for any missed tags
    fallback_text = soup.get_text(separator=' ').lower()
    fallback_words = re.findall(r'\b[a-z]{3,15}\b', fallback_text)
    for word in fallback_words:
        if word not in STOP_WORDS and word not in words_counter:
            words_counter[word] += 1
            
    most_common = words_counter.most_common(top_n)
    return ", ".join([word for word, count in most_common])

def is_english(soup):
    """Determines if a page is likely English using HTML attributes and word heuristics."""
    html_tag = soup.find('html')
    if html_tag and html_tag.has_attr('lang'):
        lang = html_tag['lang'].lower()
        if lang and not lang.startswith('en'):
            return False

    text = soup.get_text(separator=' ')
    words = set(re.findall(r'\b[a-z]{2,}\b', text.lower()))
    
    if len(words) > 20:
        overlap = len(words.intersection(STOP_WORDS))
        if overlap < 3:
            return False
            
    return True

# ==========================================
# CORS ANYWHERE SERVER SETUP
# ==========================================
cors_process = None

def cleanup_proxy():
    global cors_process
    if cors_process:
        print("\n[*] Shutting down CORS Anywhere server...")
        cors_process.terminate()

def start_cors_anywhere():
    global cors_process
    server_file = "cors_server.js"
    script_content = """
const cors_proxy = require('cors-anywhere');
const host = '127.0.0.1';
const port = 8080;
cors_proxy.createServer({
    originWhitelist: [], 
    requireHeader: [],
    removeHeaders: ['cookie', 'cookie2']
}).listen(port, host, function() {
    console.log('Running CORS Anywhere on ' + host + ':' + port);
});
"""
    if not os.path.exists(server_file):
        with open(server_file, "w") as f:
            f.write(script_content)
    
    if not os.path.exists("node_modules/cors-anywhere"):
        print("[*] Installing 'cors-anywhere' via npm. This may take a moment...")
        subprocess.run("npm install cors-anywhere", shell=True, check=True)
        
    print("[*] Starting local CORS Anywhere server on port 8080...")
    cors_process = subprocess.Popen(["node", server_file], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    atexit.register(cleanup_proxy)
    time.sleep(2)

# ==========================================
# CRAWLER LOGIC
# ==========================================
def is_valid_url(url):
    """Basic validation to ensure we only crawl HTTP/HTTPS links and avoid spider traps."""
    parsed = urlparse(url)
    
    # Block Wayback Machine / Archive.org links to save resources
    if 'web.archive.org' in parsed.netloc.lower():
        return False
        
    return bool(parsed.netloc) and bool(parsed.scheme) and parsed.scheme in ["http", "https"]

def cli_interface():
    """Background thread to handle live CLI commands while crawling."""
    print("\n" + "="*50)
    print(" 🖥️  CRAWLER CLI ACTIVE")
    print(" Commands:")
    print("  - add <url> : Instantly add & prioritize a URL")
    print("  - pause     : Suspend crawling")
    print("  - resume    : Resume crawling")
    print("  - exit/quit : Stop crawler safely")
    print("="*50 + "\n")
    
    session = PromptSession()
    
    while not SHUTDOWN_FLAG.is_set():
        try:
            # patch_stdout() safely routes all background crawler prints ABOVE your current input line!
            with patch_stdout():
                cmd = session.prompt("Crawler > ").strip()
                
            if not cmd:
                continue
                
        except (KeyboardInterrupt, EOFError):
            # Safely handle Ctrl+C or Ctrl+D pressed while typing in the prompt
            print("\n[CLI] 🛑 Initiating graceful shutdown... Please wait for current request to finish.\n")
            SHUTDOWN_FLAG.set()
            PAUSE_EVENT.set() 
            break
        except Exception as e:
            print(f"[CLI] Error: {e}")
            continue
            
        parts = cmd.split(maxsplit=1)
        action = parts[0].lower()
        
        if action == 'add' and len(parts) > 1:
            url = parts[1]
            print(f"\n[CLI] Injecting {url} into queue...")
            
            # Connect to DB locally in this thread (safe because of WAL mode)
            conn = sqlite3.connect(DB_NAME, timeout=30.0)
            cursor = conn.cursor()
            # parent_crawl_depth=-1 ensures this link evaluates to depth 0 (top priority BFS)
            added, rank, depth = add_url(cursor, url, parent_crawl_depth=-1)
            conn.commit()
            conn.close()
            
            if added:
                print(f"[CLI] [+] Successfully injected {url} at Depth 0! It will be crawled next.\n")
            else:
                print(f"[CLI] [-] {url} is already in the database.\n")
                
        elif action == 'pause':
            PAUSE_EVENT.clear()
            print("\n[CLI] ⏸️ Crawler paused. Type 'resume' to continue.\n")
            
        elif action == 'resume':
            PAUSE_EVENT.set()
            print("\n[CLI] ▶️ Crawler resumed.\n")
            
        elif action in ['quit', 'exit', 'stop']:
            print("\n[CLI] 🛑 Initiating graceful shutdown... Please wait for current request to finish.\n")
            SHUTDOWN_FLAG.set()
            PAUSE_EVENT.set() # Unpause to allow the main thread to break and exit
            break
        else:
            print("\n[CLI] ❌ Unknown command. Use: add <url>, pause, resume, exit\n")

def crawl():
    print(f"[*] Starting crawler on {START_URL}")
    print(f"[*] Saving database to {DB_NAME}")
    
    load_top_domains()
    start_cors_anywhere()
    
    conn = setup_database()
    cursor = conn.cursor()
    
    add_url(cursor, START_URL, parent_crawl_depth=None)
    conn.commit()

    # Start the CLI background thread
    cli_thread = threading.Thread(target=cli_interface, daemon=True)
    cli_thread.start()

    try:
        while not SHUTDOWN_FLAG.is_set():
            # Block here if paused via CLI
            PAUSE_EVENT.wait()
            if SHUTDOWN_FLAG.is_set():
                break
                
            current_url, current_rank, current_depth, current_crawl_depth = get_next_url(cursor)
            
            if not current_url:
                print("[*] No pending URLs found. Waiting for CLI input... (Type 'exit' to quit)")
                time.sleep(3)
                continue

            print(f"\n[~] Crawling: {current_url} [Rank: {current_rank} | Path Depth: {current_depth} | Crawl Depth: {current_crawl_depth}]")
            
            request_url = current_url
            if CORS_PROXY_PREFIX:
                request_url = CORS_PROXY_PREFIX + current_url
            
            try:
                headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) Python/Crawler'}
                response = requests.get(request_url, headers=headers, proxies=PROXIES, timeout=10)
                response.raise_for_status()
                
                soup = BeautifulSoup(response.text, 'html.parser')
                
                if not is_english(soup):
                    print(f"[!] Page does not appear to be English. Skipping.")
                    update_status(cursor, current_url, 'skipped_non_english')
                    conn.commit()
                    time.sleep(DELAY_BETWEEN_REQUESTS)
                    continue
                
                page_title = soup.title.text.strip() if soup.title else None
                if page_title:
                    print(f"    [i] Page Title: {page_title}")
                    
                keywords = extract_keywords_weighted(soup)
                if keywords:
                    print(f"    [i] Keywords: {keywords}")
                
                robots_meta = soup.find('meta', attrs={'name': lambda x: x and x.lower() == 'robots'})
                if robots_meta:
                    meta_content = robots_meta.get('content', '').lower()
                    if any(rule in meta_content for rule in ['nofollow', 'noindex', 'none']):
                        print(f"[!] Respecting meta robots tag '{meta_content}'. Skipping link extraction.")
                        update_status(cursor, current_url, 'skipped_robots_meta')
                        conn.commit()
                        time.sleep(DELAY_BETWEEN_REQUESTS)
                        continue
                
                page_links = set()
                link_attributes = ['href', 'data-href', 'data-url', 'data-link', 'action']
                js_redirect_patterns = [
                    r"(?:window\.)?location(?:.href)?\s*=\s*['\"]([^'\"]+)['\"]",
                    r"(?:window\.)?location\.(?:assign|replace)\s*\(\s*['\"]([^'\"]+)['\"]",
                    r"window\.open\s*\(\s*['\"]([^'\"]+)['\"]"
                ]
                
                for tag in soup.find_all(True):
                    raw_links = []
                    for attr in link_attributes:
                        if tag.has_attr(attr):
                            val = tag[attr]
                            if isinstance(val, list):
                                val = val[0]
                            raw_links.append(val)
                            
                    if tag.has_attr('onclick'):
                        onclick_val = tag['onclick']
                        if isinstance(onclick_val, list):
                            onclick_val = onclick_val[0]
                        for pattern in js_redirect_patterns:
                            matches = re.findall(pattern, onclick_val)
                            raw_links.extend(matches)
                            
                    for raw_link in raw_links:
                        if raw_link and not raw_link.lower().startswith(('javascript:', 'mailto:', 'tel:')):
                            full_url = urljoin(current_url, raw_link)
                            full_url = urlparse(full_url)._replace(fragment="").geturl()
                            if is_valid_url(full_url):
                                page_links.add(full_url)
                
                new_links_added = 0
                for link in page_links:
                    added, rank, depth = add_url(cursor, link, parent_crawl_depth=current_crawl_depth)
                    if added:
                        print(f"    -> Discovered: {link} [Rank: {rank} | Path Depth: {depth} | Crawl Depth: {current_crawl_depth + 1}]")
                        new_links_added += 1
                
                print(f"[+] Added {new_links_added} new unique links from this page.")
                update_status(cursor, current_url, 'crawled', page_title, keywords)
                
                total_links = get_total_links(cursor)
                print(f"[*] Total unique links in database: {total_links}")
                
            except requests.exceptions.RequestException as e:
                print(f"[-] Error fetching {current_url}: {e}")
                update_status(cursor, current_url, 'error')
            
            conn.commit()
            time.sleep(DELAY_BETWEEN_REQUESTS)

    except KeyboardInterrupt:
        print("\n[*] Crawler stopped by user (Ctrl+C).")
        SHUTDOWN_FLAG.set()
    finally:
        conn.close()

if __name__ == "__main__":
    crawl()