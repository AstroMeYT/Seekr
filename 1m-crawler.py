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
DB_NAME = "crawler_links.db"
DELAY_BETWEEN_REQUESTS = 1.0  
TOP_1M_URL = "http://s3-us-west-1.amazonaws.com/umbrella-static/top-1m.csv.zip"
TOP_1M_FILE = "top-1m.csv"
PROGRESS_FILE = "top_1m_progress.txt"

CORS_PROXY_PREFIX = "http://localhost:8080/" 
PROXIES = {}
DOMAIN_RANKS = {}

# --- THREADING FLAGS ---
PAUSE_EVENT = threading.Event()
PAUSE_EVENT.set()
SHUTDOWN_FLAG = threading.Event()

STOP_WORDS = {
    'the', 'and', 'is', 'in', 'it', 'of', 'to', 'a', 'that', 'for', 'on', 'with', 'as', 
    'this', 'was', 'at', 'by', 'an', 'be', 'from', 'or', 'are', 'not', 'have', 'all', 
    'but', 'which', 'their', 'has', 'one', 'you', 'about', 'more', 'if', 'we', 'out', 
    'up', 'so', 'can', 'what', 'who', 'when', 'will', 'there', 'your', 'how', 'do',
    'i', 'me', 'my', 'myself', 'we', 'us', 'our', 'ours', 'ourselves', 'you', 'your', 
    'yours', 'yourself', 'yourselves', 'he', 'him', 'his', 'himself', 'she', 'her', 
    'hers', 'herself', 'it', 'its', 'itself', 'they', 'them', 'their', 'theirs', 
    'themselves', 'what', 'which', 'who', 'whom', 'this', 'that', 'these', 'those', 
    'am', 'is', 'are', 'was', 'were', 'be', 'been', 'being', 'have', 'has', 'had', 
    'having', 'do', 'does', 'did', 'doing', 'can', 'could', 'should', 'would', 'will', 
    'ought', 'shall', 'may', 'might', 'must', 'get', 'got', 'go', 'goes', 'went', 
    'going', 'make', 'makes', 'made', 'making', 'take', 'takes', 'took', 'taking', 
    'say', 'says', 'said', 'saying', 'see', 'sees', 'saw', 'seeing', 'use', 'uses', 
    'used', 'using', 'want', 'wants', 'know', 'knows', 'known', 'think', 'thinks',
    'about', 'above', 'across', 'after', 'afterwards', 'against', 'along', 
    'amid', 'among', 'amongst', 'around', 'at', 'before', 'behind', 'below', 'beneath', 
    'beside', 'between', 'beyond', 'but', 'by', 'concerning', 'despite', 'down', 'during', 
    'except', 'for', 'from', 'in', 'inside', 'into', 'like', 'near', 'of', 'off', 'on', 
    'onto', 'out', 'outside', 'over', 'past', 'regarding', 'since', 'through', 'throughout', 
    'to', 'toward', 'towards', 'under', 'underneath', 'until', 'up', 'upon', 'with', 
    'within', 'without', 'because', 'since', 'although', 'though', 'while', 'unless', 
    'except', 'whereas', 'if', 'or', 'nor', 'yet', 'so', 'and',
    'time', 'times', 'second', 'seconds', 'minute', 'minutes', 'hour', 'hours', 'day', 
    'days', 'week', 'weeks', 'month', 'months', 'year', 'years', 'decade', 'decades', 
    'century', 'centuries', 'millennium', 'morning', 'afternoon', 'evening', 'night', 
    'nights', 'noon', 'midnight', 'today', 'yesterday', 'tomorrow', 'now', 'then', 
    'before', 'after', 'early', 'late', 'soon', 'ago', 'present', 'past', 'future', 
    'always', 'never', 'sometimes', 'often', 'usually', 'seldom', 'rarely', 'hourly', 
    'daily', 'weekly', 'biweekly', 'fortnightly', 'monthly', 'quarterly', 'yearly', 
    'annually', 'annual', 'current', 'currently', 'recent', 'recently', 'duration', 
    'period', 'era', 'epoch', 'age', 'moment', 'meanwhile', 'clock', 'oclock',
    'monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday', 'sunday',
    'mon', 'tue', 'wed', 'thu', 'fri', 'sat', 'sun',
    'january', 'february', 'march', 'april', 'may', 'june', 'july', 'august', 
    'september', 'october', 'november', 'december',
    'jan', 'feb', 'mar', 'apr', 'jun', 'jul', 'aug', 'sep', 'oct', 'nov', 'dec',
    'zero', 'one', 'two', 'three', 'four', 'five', 'six', 'seven', 'eight', 'nine', 
    'ten', 'eleven', 'twelve', 'thirteen', 'fourteen', 'fifteen', 'sixteen', 
    'seventeen', 'eighteen', 'nineteen', 'twenty', 'thirty', 'forty', 'fifty', 'sixty', 
    'seventy', 'eighty', 'ninety', 'hundred', 'thousand', 'million', 'billion', 
    'first', 'second', 'third', 'fourth', 'fifth', 'sixth', 'seventh', 'eighth', 
    'ninth', 'tenth', 'once', 'twice', 'thrice', 'double', 'triple', 'single', 
    'few', 'many', 'several', 'some', 'any', 'none', 'all', 'both', 'half', 'quarter', 
    'whole', 'total', 'average', 'number', 'numbers', 'amount', 'more', 'less', 
    'least', 'most', 'such', 'other', 'others', 'another', 'each', 'every',
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

# ==========================================
# HELPER FUNCTIONS
# ==========================================
def load_top_domains():
    global DOMAIN_RANKS
    top_domains_list = []
    
    if not os.path.exists(TOP_1M_FILE):
        print(f"[*] Downloading top 1 million domains from {TOP_1M_URL}...")
        response = requests.get(TOP_1M_URL, timeout=30)
        response.raise_for_status()
        with zipfile.ZipFile(io.BytesIO(response.content)) as z:
            z.extractall()
        print("[*] Download and extraction complete.")
    
    try:
        with open(TOP_1M_FILE, 'r', encoding='utf-8') as f:
            for line in f:
                parts = line.strip().split(',')
                if len(parts) == 2:
                    rank, domain = parts
                    domain = domain.lower()
                    DOMAIN_RANKS[domain] = int(rank)
                    top_domains_list.append((int(rank), domain))
        return sorted(top_domains_list, key=lambda x: x[0])
    except Exception as e:
        print(f"[-] Error loading top domains: {e}")
        return []

def get_progress():
    if os.path.exists(PROGRESS_FILE):
        try:
            with open(PROGRESS_FILE, 'r') as f:
                return int(f.read().strip())
        except ValueError:
            return 0
    return 0

def save_progress(rank):
    with open(PROGRESS_FILE, 'w') as f:
        f.write(str(rank))

def extract_core_domain(url):
    try:
        netloc = urlparse(url).netloc.lower().split(':')[0]
        if netloc.startswith('www.'):
            netloc = netloc[4:]
        parts = netloc.split('.')
        tlds = {
            'com', 'co', 'org', 'net', 'gov', 'edu', 'ac', 'mil', 'int',
            'uk', 'ca', 'au', 'jp', 'de', 'fr', 'cn', 'ru', 'us', 'it', 'nl', 'se', 'no', 'es',
            'info', 'biz', 'name', 'xyz', 'online', 'io', 'me', 'tv', 'cc', 'app'
        }
        while len(parts) > 1 and parts[-1] in tlds:
            parts.pop()
        return parts[-1] if parts else ""
    except Exception:
        return ""

def get_url_metrics(url):
    parsed = urlparse(url)
    path_parts = [p for p in parsed.path.split('/') if p]
    depth = len(path_parts)
    
    netloc = parsed.netloc.lower().split(':')[0]
    if netloc.startswith('www.'):
        netloc = netloc[4:]
        
    rank = DOMAIN_RANKS.get(netloc, 9999999) 
    return rank, depth

def is_valid_url(url):
    parsed = urlparse(url)
    
    # Block Wayback Machine / Archive.org links to save resources
    if 'web.archive.org' in parsed.netloc.lower():
        return False
        
    return bool(parsed.netloc) and bool(parsed.scheme) and parsed.scheme in ["http", "https"]

def is_english(soup):
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

def extract_keywords_weighted(soup, top_n=15):
    for element in soup(["script", "style", "nav", "footer", "header", "aside"]):
        element.extract()
        
    words_counter = Counter()
    tag_weights = {'title': 12, 'h1': 10, 'h2': 6, 'h3': 4, 'strong': 2, 'b': 2, 'p': 1, 'li': 1}
    
    for tag, weight in tag_weights.items():
        elements = soup.find_all(tag)
        for elem in elements:
            text = elem.get_text(separator=' ').lower()
            words = re.findall(r'\b[a-z]{3,15}\b', text)
            for word in words:
                if word not in STOP_WORDS:
                    words_counter[word] += weight
                    
    fallback_text = soup.get_text(separator=' ').lower()
    fallback_words = re.findall(r'\b[a-z]{3,15}\b', fallback_text)
    for word in fallback_words:
        if word not in STOP_WORDS and word not in words_counter:
            words_counter[word] += 1
            
    most_common = words_counter.most_common(top_n)
    return ", ".join([word for word, count in most_common])

# ==========================================
# DATABASE LOGIC
# ==========================================
def setup_database():
    conn = sqlite3.connect(DB_NAME, timeout=30.0)
    conn.execute('PRAGMA journal_mode=WAL;')
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS links (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            url TEXT UNIQUE NOT NULL,
            status TEXT DEFAULT 'pending',
            domain_rank INTEGER,
            depth INTEGER,
            page_title TEXT,
            keywords TEXT,
            crawl_depth INTEGER
        )
    ''')
    cursor.execute('''
        CREATE VIRTUAL TABLE IF NOT EXISTS links_fts USING fts5(
            link_id UNINDEXED, page_title, keywords, url
        );
    ''')
    conn.commit()
    return conn

def add_url(cursor, url, parent_crawl_depth=None):
    rank, path_depth = get_url_metrics(url)
    crawl_depth = 0 if parent_crawl_depth is None else parent_crawl_depth + 1
    try:
        cursor.execute('''
            INSERT OR IGNORE INTO links (url, status, domain_rank, depth, crawl_depth) 
            VALUES (?, 'pending', ?, ?, ?)
        ''', (url, rank, path_depth, crawl_depth))
        return cursor.rowcount > 0, rank, path_depth
    except sqlite3.Error:
        return False, rank, path_depth

def update_status(cursor, url, status, page_title=None, keywords=None):
    if page_title or keywords:
        cursor.execute("UPDATE links SET status = ?, page_title = ?, keywords = ? WHERE url = ?", (status, page_title, keywords, url))
        cursor.execute("SELECT id FROM links WHERE url = ?", (url,))
        row = cursor.fetchone()
        if row:
            link_id = row[0]
            cursor.execute("DELETE FROM links_fts WHERE link_id = ?", (link_id,))
            cursor.execute("INSERT INTO links_fts (link_id, page_title, keywords, url) VALUES (?, ?, ?, ?)", 
                           (link_id, page_title or "", keywords or "", url))
    else:
        cursor.execute("UPDATE links SET status = ? WHERE url = ?", (status, url))

# ==========================================
# CORS PROXY LOGIC
# ==========================================
cors_process = None
def cleanup_proxy():
    global cors_process
    if cors_process:
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
}).listen(port, host, function() {});
"""
    if not os.path.exists(server_file):
        with open(server_file, "w") as f:
            f.write(script_content)
    if not os.path.exists("node_modules/cors-anywhere"):
        subprocess.run("npm install cors-anywhere", shell=True, check=True)
        
    cors_process = subprocess.Popen(["node", server_file], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    atexit.register(cleanup_proxy)
    time.sleep(2)

# ==========================================
# CLI INTERFACE LOGIC
# ==========================================
def cli_interface():
    """Background thread to handle live CLI commands while crawling."""
    print("\n" + "="*50)
    print(" 🖥️  DEEP CRAWLER CLI ACTIVE")
    print(" Commands:")
    print("  - add <url> : Instantly add & prioritize a URL (Global Queue)")
    print("  - pause     : Suspend crawling")
    print("  - resume    : Resume crawling")
    print("  - exit/quit : Stop crawler safely")
    print("="*50 + "\n")
    
    session = PromptSession()
    
    while not SHUTDOWN_FLAG.is_set():
        try:
            with patch_stdout():
                cmd = session.prompt("DeepCrawler > ").strip()
                
            if not cmd:
                continue
                
        except (KeyboardInterrupt, EOFError):
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
            print(f"\n[CLI] Injecting {url} into global queue...")
            
            conn = sqlite3.connect(DB_NAME, timeout=30.0)
            cursor = conn.cursor()
            added, rank, depth = add_url(cursor, url, parent_crawl_depth=-1)
            conn.commit()
            conn.close()
            
            if added:
                print(f"[CLI] [+] Successfully injected {url} at Depth 0! Main crawler will pick it up.\n")
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
            PAUSE_EVENT.set()
            break
        else:
            print("\n[CLI] ❌ Unknown command. Use: add <url>, pause, resume, exit\n")


# ==========================================
# DEEP CRAWL LOGIC
# ==========================================
def crawl_top_1m():
    print("=========================================")
    print("      Top 1M Domain Deep-Crawler")
    print("=========================================")
    
    top_domains = load_top_domains()
    start_cors_anywhere()
    
    conn = setup_database()
    cursor = conn.cursor()
    
    last_rank_processed = get_progress()
    print(f"[*] Resuming from Top 1M Rank: {last_rank_processed + 1}")

    # Start the CLI background thread
    cli_thread = threading.Thread(target=cli_interface, daemon=True)
    cli_thread.start()

    try:
        for rank, domain in top_domains:
            if SHUTDOWN_FLAG.is_set():
                break
            PAUSE_EVENT.wait()
            
            if rank <= last_rank_processed:
                continue
                
            print(f"\n" + "="*50)
            print(f"[*] INDEXING TARGET #{rank}: {domain.upper()}")
            print("="*50)
            
            start_url = f"https://www.{domain}"
            core_target_domain = extract_core_domain(start_url)
            
            # Local domain-specific queue for BFS
            local_queue = [(start_url, 0)]
            visited_in_session = set()
            
            while local_queue:
                if SHUTDOWN_FLAG.is_set():
                    break
                PAUSE_EVENT.wait()
                
                current_url, current_crawl_depth = local_queue.pop(0)
                
                if current_url in visited_in_session:
                    continue
                visited_in_session.add(current_url)
                
                if current_crawl_depth > 3:
                    continue
                    
                # Synchronize with the main database (prevents stepping on normal crawler's toes)
                add_url(cursor, current_url, parent_crawl_depth=(current_crawl_depth - 1))
                
                cursor.execute("SELECT status FROM links WHERE url = ?", (current_url,))
                db_status = cursor.fetchone()
                
                if db_status and db_status[0] in ['crawled', 'crawling']:
                    # Already handled by a previous session or by the normal crawler script!
                    continue
                    
                cursor.execute("UPDATE links SET status = 'crawling' WHERE url = ?", (current_url,))
                conn.commit()
                
                print(f"  [~] Deep Crawl (Depth {current_crawl_depth}/3): {current_url}")
                
                request_url = CORS_PROXY_PREFIX + current_url
                
                try:
                    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) Nexus-DeepBot'}
                    response = requests.get(request_url, headers=headers, proxies=PROXIES, timeout=10)
                    response.raise_for_status()
                    
                    soup = BeautifulSoup(response.text, 'html.parser')
                    
                    if not is_english(soup):
                        update_status(cursor, current_url, 'skipped_non_english')
                        conn.commit()
                        time.sleep(DELAY_BETWEEN_REQUESTS)
                        continue
                        
                    page_title = soup.title.text.strip() if soup.title else None
                    keywords = extract_keywords_weighted(soup)
                    
                    # Extract links
                    page_links = set()
                    for tag in soup.find_all(True, href=True):
                        raw_link = tag['href']
                        if raw_link and not raw_link.lower().startswith(('javascript:', 'mailto:', 'tel:')):
                            full_url = urljoin(current_url, raw_link)
                            full_url = urlparse(full_url)._replace(fragment="").geturl()
                            if is_valid_url(full_url):
                                page_links.add(full_url)
                                
                    new_internal = 0
                    new_external = 0
                    
                    for link in page_links:
                        link_core = extract_core_domain(link)
                        
                        # Add to DB globally so normal crawler can see it
                        added, _, _ = add_url(cursor, link, parent_crawl_depth=current_crawl_depth)
                        
                        if link_core == core_target_domain:
                            new_internal += 1
                            if current_crawl_depth < 3:
                                local_queue.append((link, current_crawl_depth + 1))
                        else:
                            new_external += 1
                            
                    update_status(cursor, current_url, 'crawled', page_title, keywords)
                    print(f"      -> Success! Found {new_internal} internal, {new_external} external links.")
                    
                except requests.exceptions.RequestException as e:
                    print(f"      [-] Failed: {e}")
                    update_status(cursor, current_url, 'error')
                    
                conn.commit()
                time.sleep(DELAY_BETWEEN_REQUESTS)

            if SHUTDOWN_FLAG.is_set():
                break

            # Domain fully processed up to depth 3
            save_progress(rank)
            print(f"[*] Completed indexing for {domain}. Progress saved.")

    except KeyboardInterrupt:
        print("\n[*] Deep Crawler stopped by user (Ctrl+C). Progress saved safely.")
        SHUTDOWN_FLAG.set()
    finally:
        conn.close()

if __name__ == "__main__":
    crawl_top_1m()