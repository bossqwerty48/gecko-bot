#!/usr/bin/env python3
"""
Gecko Inspector - адаптированная версия для Render.com
"""
from flask import Flask, request, jsonify
from flask_cors import CORS
import cloudscraper
import re
from datetime import datetime
import json
import time
import random
from bs4 import BeautifulSoup

app = Flask(__name__)
CORS(app)

# Настройки
MIN_HTML_SIZE_KB = 200

# Статистика
request_stats = {
    'total_requests': 0,
    'successful': 0,
    'failed': 0
}

def create_cloudscraper():
    """Создаёт cloudscraper (без прокси на Render)"""
    scraper = cloudscraper.create_scraper(
        browser={'browser': 'chrome', 'platform': 'windows', 'desktop': True},
        delay=random.uniform(1, 3)
    )
    scraper.headers.update({
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
        'Accept-Language': 'ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7',
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0.0.0'
    })
    return scraper

def parse_title_for_image_info(title):
    """Парсит заголовок страницы"""
    if not title:
        return None
    
    result = {
        'raw_title': title,
        'has_jpeg': False,
        'filename': None,
        'width': None,
        'height': None,
        'dimensions': None
    }
    
    jpeg_match = re.search(r'([a-f0-9]+\.jpeg)', title, re.IGNORECASE)
    if jpeg_match:
        result['has_jpeg'] = True
        result['filename'] = jpeg_match.group(1)
    
    dimensions_match = re.search(r'\((\d+)\s*[×x]\s*(\d+)\)', title, re.IGNORECASE)
    if dimensions_match:
        result['width'] = int(dimensions_match.group(1))
        result['height'] = int(dimensions_match.group(2))
        result['dimensions'] = f"{result['width']}×{result['height']}"
    
    return result

def extract_full_html_info(html, url):
    """Извлекает информацию из HTML"""
    soup = BeautifulSoup(html, 'html.parser')
    
    title_tag = soup.find('title')
    title_text = title_tag.string if title_tag else None
    title_info = parse_title_for_image_info(title_text) if title_text else None
    
    all_jpeg_matches = re.findall(r'([a-f0-9]{32}\.jpeg)', html, re.IGNORECASE)
    unique_jpegs = list(set(all_jpeg_matches))
    
    html_size_bytes = len(html.encode('utf-8'))
    html_size_kb = html_size_bytes / 1024
    
    return {
        'title': title_text,
        'title_info': title_info,
        'all_jpeg_files': unique_jpegs,
        'html_size_bytes': html_size_bytes,
        'html_size_kb': round(html_size_kb, 2),
        'html_size_status': 'large' if html_size_kb >= MIN_HTML_SIZE_KB else 'small',
        'full_html_length': len(html),
    }

def check_page(url, max_retries=3):
    """Проверяет страницу"""
    result = {
        'url': url,
        'timestamp': datetime.now().isoformat(),
        'page_loaded': False,
        'status_code': None,
        'error': None,
        'html_analysis': None
    }
    
    request_stats['total_requests'] += 1
    
    for attempt in range(max_retries):
        try:
            scraper = create_cloudscraper()
            
            if attempt > 0:
                time.sleep(random.uniform(2, 4))
            
            response = scraper.get(url, timeout=30, allow_redirects=True)
            result['status_code'] = response.status_code
            
            if response.status_code == 200:
                result['page_loaded'] = True
                html = response.text
                result['html_analysis'] = extract_full_html_info(html, url)
                request_stats['successful'] += 1
                break
            else:
                result['error'] = f'HTTP {response.status_code}'
                
        except Exception as e:
            result['error'] = str(e)
            if attempt == max_retries - 1:
                request_stats['failed'] += 1
    
    return result

# API Endpoints

@app.route('/api/check', methods=['POST'])
def check_urls():
    data = request.get_json()
    
    if not data or 'urls' not in data:
        return jsonify({'error': 'Missing "urls" parameter'}), 400
    
    urls = data['urls']
    if not isinstance(urls, list):
        return jsonify({'error': '"urls" must be a list'}), 400
    
    results = []
    for url in urls:
        print(f"\n🔍 Checking: {url}")
        result = check_page(url)
        results.append(result)
        time.sleep(random.uniform(0.5, 1))
    
    pages_with_jpeg_in_title = sum(
        1 for r in results 
        if r.get('html_analysis') and r['html_analysis'].get('title_info') and r['html_analysis']['title_info'].get('has_jpeg')
    )
    large_html_pages = sum(
        1 for r in results 
        if r.get('html_analysis') and r['html_analysis'].get('html_size_status') == 'large'
    )
    
    return jsonify({
        'results': results,
        'statistics': {
            'total': len(results),
            'pages_loaded': sum(1 for r in results if r.get('page_loaded')),
            'pages_with_jpeg_in_title': pages_with_jpeg_in_title,
            'large_html_pages': large_html_pages,
            'min_html_size_kb': MIN_HTML_SIZE_KB
        },
        'request_stats': request_stats,
        'checked_at': datetime.now().isoformat()
    })

@app.route('/api/health', methods=['GET'])
def health():
    return jsonify({
        'status': 'ok',
        'message': 'Gecko Inspector running on Render',
        'request_stats': request_stats
    })

@app.route('/')
def index():
    return jsonify({
        'message': 'Gecko Inspector API is running!',
        'endpoints': {
            'POST /api/check': 'Check URLs for JPEG in title',
            'GET /api/health': 'Health check'
        }
    })

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)