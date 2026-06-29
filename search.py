import sqlite3
import math
import sys
import os
import re
from urllib.parse import urlparse
from flask import Flask, request, jsonify

# ==========================================
# CONFIGURATION
# ==========================================
DB_NAME = "crawler_links.db"
PORT = 5000

app = Flask(__name__)

# Inject CORS headers so frontends can easily connect without security errors
@app.after_request
def add_cors_headers(response):
    response.headers.add('Access-Control-Allow-Origin', '*')
    response.headers.add('Access-Control-Allow-Headers', 'Content-Type,Authorization')
    response.headers.add('Access-Control-Allow-Methods', 'GET,PUT,POST,DELETE,OPTIONS')
    return response

# ==========================================
# SEARCH LOGIC
# ==========================================
def connect_db():
    if not os.path.exists(DB_NAME):
        print(f"[-] Database '{DB_NAME}' not found. Please run the crawler first.")
        sys.exit(1)
    return sqlite3.connect(DB_NAME)

def extract_domain_info(url):
    """
    Extracts the core domain and the root domain to distinguish subdomains.
    E.g. "https://books.google.co.uk/books" -> core: "google", root: "google.co.uk", netloc: "books.google.co.uk"
    """
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
        
        tld_parts = []
        while len(parts) > 1 and parts[-1] in tlds:
            tld_parts.insert(0, parts.pop())
            
        core = parts[-1] if parts else ""
        root_domain = f"{core}.{'.'.join(tld_parts)}" if tld_parts else core
        
        return core, root_domain, netloc
    except Exception:
        return "", "", ""

def calculate_score(query, title, url, domain_rank, depth, keywords, fts_rank):
    """
    Calculates an incredibly precise relevance score using SQLite FTS5 matching,
    strict hierarchical domain parsing, and tangential mention penalties.
    """
    query_lower = query.lower()
    title_lower = (title or "").lower()
    url_lower = url.lower()
    keywords_lower = (keywords or "").lower()
    
    score = 0
    
    # 1. Evaluate page nesting complexity structurally
    parsed_url = urlparse(url)
    path = parsed_url.path.strip('/')
    has_query_params = bool(parsed_url.query)
    
    is_homepage = (not path or path in ('index.html', 'index.php', 'index.htm')) and not has_query_params
    url_depth = len([p for p in parsed_url.path.split('/') if p])
    decay = 1.0 / (1.0 + (url_depth * 0.4) + (1.5 if has_query_params else 0.0))

    # 2. SQLite FTS5 Relevance (Base textual match)
    fts_score = max(-fts_rank, 0.0) * 800.0
    score += fts_score * decay

    # 3. Domain & Subdomain Hierarchy Prioritization
    core_domain, root_domain, netloc = extract_domain_info(url)
    is_exact_core = (query_lower == core_domain)
    is_root_netloc = (netloc == root_domain) 
    
    if is_exact_core:
        if is_homepage and is_root_netloc:
            score += 30000
        elif is_homepage:
            score += 15000
        elif is_root_netloc:
            score += 8000
        else:
            score += 4000
            
    elif query_lower in core_domain:
        if is_homepage:
            score += 5000
        else:
            score += 1500

    # 4. Phrase & Token Matches (Decayed by depth)
    query_words = set(re.findall(r'\b\w+\b', query_lower))
    title_words = set(re.findall(r'\b\w+\b', title_lower))
    keyword_words = set(re.findall(r'\b\w+\b', keywords_lower))
    
    if query_lower in title_lower:
        score += 4000 * decay
        
    title_matches = query_words.intersection(title_words)
    score += (len(title_matches) * 1000) * decay
    
    keyword_matches = query_words.intersection(keyword_words)
    score += (len(keyword_matches) * 200) * decay

    # 5. THE TANGENTIAL PENALTY 
    has_relevant_anchor = False
    if is_exact_core or (query_lower in core_domain):
        has_relevant_anchor = True
    elif len(title_matches) > 0:
        has_relevant_anchor = True

    if not has_relevant_anchor:
        score *= 0.05

    # 6. Domain Popularity & Structure Penalties 
    safe_rank = max(domain_rank if domain_rank is not None else 9999999, 1)
    rank_penalty = math.log10(safe_rank) * 120  
    score -= rank_penalty
    
    score -= (url_depth * 100)
    if has_query_params:
        score -= 500
    
    return score

def search(query, limit=100):
    conn = connect_db()
    cursor = conn.cursor()
    
    words = re.findall(r'\b\w+\b', query)
    if not words:
        return []
        
    fts_query = " OR ".join(words)
    
    sql_query = """
        SELECT l.url, l.page_title, l.domain_rank, l.depth, l.keywords, bm25(links_fts) as fts_rank
        FROM links_fts f
        JOIN links l ON f.link_id = l.id
        WHERE links_fts MATCH ? AND l.status = 'crawled'
    """
    
    try:
        cursor.execute(sql_query, (fts_query,))
        candidates = cursor.fetchall()
    except sqlite3.Error as e:
        print(f"[-] Database error: {e}")
        return []
    finally:
        conn.close()

    scored_results = []
    for row in candidates:
        url, title, rank, depth, keywords, fts_rank = row
        score = calculate_score(query, title, url, rank, depth, keywords, fts_rank)
        
        if score > 0:
            scored_results.append({
                'score': round(score, 2),
                'title': title or "No Title",
                'url': url,
                'rank': rank if rank is not None else "Unranked",
                'depth': depth if depth is not None else "Unknown",
                'keywords': keywords if keywords else "None"
            })
        
    scored_results.sort(key=lambda x: x['score'], reverse=True)
    return scored_results[:limit]

# ==========================================
# API ENDPOINTS
# ==========================================
@app.route('/api/search', methods=['GET'])
def api_search():
    """
    Endpoint: GET /api/search?q=<query>&limit=<number>
    Returns standard JSON array of search engine results.
    """
    query = request.args.get('q', '').strip()
    limit = request.args.get('limit', 50, type=int)

    if not query:
        return jsonify({
            "query": "",
            "count": 0,
            "results": []
        }), 400

    print(f"[*] API Request: Searching for '{query}'...")
    results = search(query, limit=limit)
    
    return jsonify({
        "query": query,
        "count": len(results),
        "results": results
    })

if __name__ == "__main__":
    print("==================================================")
    print(" 🚀 Search Engine API Server Started")
    print(f" 📡 Local Endpoint: http://0.0.0.0:{PORT}/api/search")
    print("==================================================")
    
    # Run the Flask app (use host='0.0.0.0' if you want it accessible on your local network)
    app.run(host='0.0.0.0', port=PORT, debug=True)
