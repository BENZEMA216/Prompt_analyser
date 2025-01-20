from fastapi import FastAPI, HTTPException
from typing import List, Dict, Any, Optional, Tuple, Union
import httpx
import asyncio
import logging
import re
import random
import ssl
from datetime import datetime, timedelta
from functools import lru_cache
import hashlib
from xml.etree import ElementTree as ET
from io import StringIO
from urllib.parse import urlencode, quote_plus

app = FastAPI()
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Define user agents for rotation globally
user_agents = [
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:121.0) Gecko/20100101 Firefox/121.0',
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.2.1 Safari/605.1.15',
    'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Edge/120.0.0.0 Safari/537.36'
]

# Cache for storing successful responses
CACHE: Dict[str, Tuple[List[Dict[str, Any]], datetime]] = {}

async def retry_get(client: httpx.AsyncClient, url: str, max_retries: int = 3) -> Optional[httpx.Response]:
    instance = url.split('/')[2]
    user_agents = [
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:89.0) Gecko/20100101 Firefox/89.0',
        'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/14.1.1 Safari/605.1.15'
    ]
    
    for attempt in range(max_retries):
        try:
            delay = min((2 ** attempt) * 2, 30)  # Cap max delay at 30 seconds
            if attempt > 0:
                logger.info(f"Waiting {delay} seconds before retry for {instance}...")
                await asyncio.sleep(delay)
            
            logger.info(f"Attempting request to {instance} (attempt {attempt + 1}/{max_retries})")
            
            # Rotate User-Agent for each attempt
            current_user_agent = user_agents[attempt % len(user_agents)]
            
            # Use shorter timeouts to fail fast
            timeout = httpx.Timeout(15.0, connect=5.0, read=10.0)
            
            response = await client.get(
                url,
                timeout=timeout,
                follow_redirects=True,
                headers={
                    'User-Agent': current_user_agent,
                    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
                    'Accept-Language': 'en-US,en;q=0.5',
                    'Connection': 'keep-alive',
                    'Cache-Control': 'no-cache'
                }
            )
            
            # Log response details for debugging
            if response.status_code != 200:
                logger.error(f"Non-200 response from {url.split('/')[2]}: {response.status_code}")
                if 'location' in response.headers:
                    logger.error(f"Redirect location: {response.headers['location']}")
                logger.error(f"Response headers: {dict(response.headers)}")
                logger.error(f"Response text: {response.text[:500]}...")
            
            # Handle various response status codes
            if response.status_code == 200:
                logger.info(f"Successfully received response from {instance}")
                return response
            elif response.status_code == 429:
                retry_after = min(int(response.headers.get('retry-after', delay)), 30)
                logger.warning(f"Rate limited by {instance}. Waiting {retry_after} seconds...")
                await asyncio.sleep(retry_after)
                continue
            elif response.status_code in [502, 503, 504]:
                logger.warning(f"{instance} returned {response.status_code}, may be temporarily unavailable")
                raise httpx.HTTPError(f"Service unavailable: {response.status_code}")
            else:
                logger.error(f"Unexpected status code {response.status_code} from {instance}")
                response.raise_for_status()
                
            return None
            
        except httpx.TimeoutException:
            logger.warning(f"Timeout on attempt {attempt + 1} for {url}")
            if attempt == max_retries - 1:
                raise
        except httpx.HTTPError as e:
            logger.error(f"HTTP error on attempt {attempt + 1} for {url}: {str(e)}")
            if attempt == max_retries - 1:
                raise

def get_cache_key(query: str, max_results: int) -> str:
    """Generate a cache key from the query parameters."""
    return hashlib.md5(f"{query}:{max_results}".encode()).hexdigest()

def is_cache_valid(cache_time: datetime, max_age_minutes: int = 30) -> bool:
    """Check if cached data is still valid with longer cache time."""
    return datetime.now() - cache_time < timedelta(minutes=max_age_minutes)

async def fetch_tweets(query: str, max_results: int = 10) -> List[Dict[str, Any]]:
    # Check cache first
    cache_key = get_cache_key(query, max_results)
    if cache_key in CACHE:
        tweets, cache_time = CACHE[cache_key]
        if is_cache_valid(cache_time):
            logger.info("Returning cached results")
            return tweets
        else:
            logger.info("Cache expired, fetching fresh results")
            del CACHE[cache_key]

    # Focus on most reliable Nitter instances
    instances = [
        "https://nitter.net",  # Primary instance
        "https://nitter.cz",   # Backup instance
        "https://nitter.foss.wtf",  # Additional backup
    ]
    
    logger.info(f"Starting tweet search with query: {query}, max_results: {max_results}")
    logger.info(f"Using primary Nitter instances: {instances}")

    # Enhanced instance availability check that verifies tweet content access
    async def check_instance(instance: str) -> bool:
        try:
            url = f"{instance}/search?f=tweets&q=test"
            timeout = httpx.Timeout(30.0, connect=15.0)  # Increased timeouts
            headers = {
                'User-Agent': random.choice(user_agents),
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
                'Accept-Language': 'en-US,en;q=0.5',
                'Cache-Control': 'no-cache',
                'Connection': 'keep-alive',
                'Upgrade-Insecure-Requests': '1',
                'DNT': '1'
            }
            
            # Shorter delay to speed up instance checks
            await asyncio.sleep(random.uniform(1.0, 2.0))
            
            async with httpx.AsyncClient(
                timeout=timeout,
                limits=httpx.Limits(max_keepalive_connections=10, max_connections=20),
                verify=False,  # Allow self-signed certificates
                headers=headers,
                follow_redirects=True
            ) as client:
                try:
                    response = await client.get(url)
                    logger.info(f"Response from {instance}: status={response.status_code}, url={response.url}")
                    
                    # More forgiving status code checks
                    if response.status_code == 429:
                        retry_after = min(int(response.headers.get('Retry-After', '5')), 10)
                        logger.warning(f"Rate limited by {instance}, waiting {retry_after}s")
                        await asyncio.sleep(retry_after)
                        return False
                    
                    if response.status_code not in [200, 201, 202]:
                        logger.warning(f"Instance {instance} returned status {response.status_code}")
                        return False
                    
                    # Less strict auth check - only look for explicit auth/login pages
                    final_url = str(response.url).lower()
                    if '/auth/' in final_url or '/login' in final_url:
                        logger.warning(f"Instance {instance} requires authentication")
                        return False
                    
                    # Simplified content verification - check for any tweet-related content
                    html_content = response.text.lower()
                    content_markers = [
                        'tweet-content',
                        'timeline-item',
                        'tweet-body',
                        'tweet-link',
                        'tweet',
                        'timeline'
                    ]
                    
                    # Check if we got any tweet-related content
                    for marker in content_markers:
                        if marker in html_content:
                            logger.info(f"Found tweet marker '{marker}' in {instance}")
                            return True
                    
                    # If we got HTML but no tweet markers, log the content for debugging
                    if '<html' in html_content:
                        logger.warning(f"Got HTML from {instance} but no tweet markers found")
                        logger.debug(f"Content preview: {html_content[:500]}")
                    else:
                        logger.warning(f"No HTML content found in {instance} response")
                    
                    return False
                    
                except httpx.TimeoutException:
                    logger.warning(f"Timeout connecting to {instance}")
                    return False
                except httpx.ConnectError:
                    logger.warning(f"Connection error for {instance}")
                    return False
                except Exception as e:
                    logger.warning(f"Request failed for {instance}: {str(e)}")
                    return False
                
        except Exception as e:
            logger.warning(f"Instance check failed for {instance}: {str(e)}")
            return False
    
    # Quick parallel instance checks
    async def check_all_instances():
        """Check instances sequentially with retries for better reliability."""
        available = []
        for instance in instances:
            # Try each instance up to 3 times
            for attempt in range(3):
                try:
                    if await check_instance(instance):
                        available.append(instance)
                        break
                    await asyncio.sleep(1)  # Short delay between attempts
                except Exception as e:
                    logger.warning(f"Attempt {attempt + 1} failed for {instance}: {str(e)}")
                    if attempt < 2:  # Only sleep if we're going to retry
                        await asyncio.sleep(2 ** attempt)  # Exponential backoff
        return available
    
    available_instances = await check_all_instances()
    if not available_instances:
        logger.warning("No instances available on first try, retrying once with delay")
        await asyncio.sleep(2)
        available_instances = await check_all_instances()
    
    logger.info(f"Found {len(available_instances)} available instances: {available_instances}")
            
    logger.info(f"Available instances after health check: {available_instances}")

    if not available_instances:
        logger.error("No Nitter instances are available after health check")
        raise HTTPException(
            status_code=503,
            detail="No Nitter instances are currently available. Please try again later."
        )

    # Update instances list with only available ones
    instances = available_instances
    logger.info(f"Using available instances: {instances}")
    
    # Use the globally defined user agents
    
    # Enhanced rate limit tracking with longer cache
    rate_limit_reset = {}
    instance_failures = {}  # Track consecutive failures per instance
    
    # Validate and encode query
    if not query:
        raise HTTPException(status_code=400, detail="Query parameter is required")
    tweets = []
    
    # Longer timeouts and more connections for reliability
    timeout = httpx.Timeout(30.0, connect=10.0, read=20.0)
    limits = httpx.Limits(max_keepalive_connections=10, max_connections=20)
    
    # Shuffle instances for better load distribution
    random.shuffle(instances)
    
    async with httpx.AsyncClient(timeout=timeout, limits=limits) as client:
        response = None
        # Add initial delay before starting requests
        await asyncio.sleep(random.uniform(1, 3))
        
        for instance in instances:
            # Add delay between instance requests
            await asyncio.sleep(random.uniform(3, 7))
            # Enhanced rate limit and failure handling
            current_time = datetime.now()
            
            # Enhanced rate limit handling with dynamic backoff
            if instance in rate_limit_reset:
                reset_time = rate_limit_reset[instance]
                if current_time < reset_time:
                    wait_time = (reset_time - current_time).total_seconds()
                    if wait_time <= 5:  # If less than 5 seconds left, just wait it out
                        logger.info(f"Short rate limit wait for {instance}, waiting {wait_time:.1f}s")
                        await asyncio.sleep(wait_time)
                    else:
                        logger.warning(f"Rate limit in effect for {instance}, skipping... (resets in {wait_time:.1f}s)")
                        continue
                
            # More forgiving failure handling
            failure_count = instance_failures.get(instance, 0)
            if failure_count > 2:  # More forgiving threshold
                backoff_time = min(2 ** failure_count, 30)  # Cap at 30 seconds
                logger.warning(f"Instance {instance} has failed {failure_count} times, backing off for {backoff_time}s")
                await asyncio.sleep(backoff_time)
                instance_failures[instance] = max(0, failure_count - 2)  # Reduce failure count more aggressively
                
            # Add detailed logging
            logger.info(f"Trying instance {instance} (failures: {failure_count})")
                
            # Rotate User-Agent
            headers = {'User-Agent': random.choice(user_agents)}
            client.headers = headers
            
            try:
                # Enhanced search parameters
                # Enhanced search parameters with better encoding
                encoded_query = quote_plus(query)
                params = {
                    "f": "tweets",
                    "q": encoded_query,
                    "s": "recent",  # Sort by recent to ensure fresh results
                    "e": "on",      # Extended mode
                    "m": "live",    # Live mode for better results
                    "l": "",        # No language restriction
                    "src": "typed_query"  # Indicate typed query
                }
                logger.info(f"Search parameters: {params}")
                url = f"{instance}/search"
                
                # Enhanced headers to better mimic a browser
                headers = {
                    'User-Agent': random.choice(user_agents),
                    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
                    'Accept-Language': 'en-US,en;q=0.5',
                    'Accept-Encoding': 'gzip, deflate',
                    'Connection': 'keep-alive',
                    'Upgrade-Insecure-Requests': '1',
                    'Cache-Control': 'no-cache',
                    'Pragma': 'no-cache'
                }
                
                # Properly encode query parameters using urllib.parse
                try:
                    encoded_params = urlencode(params, quote_via=quote_plus)
                    full_url = f"{url}?{encoded_params}"
                    logger.info(f"Trying HTML search from {full_url}")
                    
                    # First get the search page to establish session
                    init_response = await client.get(url, headers=headers, follow_redirects=True)
                    
                    # Enhanced authentication and error page detection
                    auth_markers = [
                        "authentication", "login", "sign in", "error", "blocked", 
                        "unavailable", "try again", "captcha", "verify", "too many requests",
                        "rate limit", "maintenance", "temporarily", "unavailable"
                    ]
                    init_response_lower = init_response.text.lower()
                    
                    # Check final URL after redirects
                    final_url = str(init_response.url)
                    if not final_url.startswith(instance):
                        logger.warning(f"Instance {instance} redirected to {final_url}")
                        continue
                        
                    if any(marker in init_response_lower for marker in auth_markers):
                        logger.warning(f"Instance {instance} requires authentication or returned an error page")
                        continue
                        
                    # Check response content type
                    content_type = init_response.headers.get('content-type', '').lower()
                    if not ('text/html' in content_type or 'application/xhtml+xml' in content_type):
                        logger.warning(f"Instance {instance} returned unexpected content type: {content_type}")
                        continue
                        
                    if init_response.status_code == 200:
                        # Extract any potential CSRF token or session data from the search form
                        search_html = init_response.text
                        logger.info(f"Initial search page response length: {len(search_html)}")
                        
                        # Now perform the actual search with additional headers
                        search_headers = headers.copy()
                        search_headers.update({
                            'Referer': url,
                            'Origin': instance,
                            'DNT': '1',
                            'Sec-Fetch-Dest': 'document',
                            'Sec-Fetch-Mode': 'navigate',
                            'Sec-Fetch-Site': 'same-origin',
                            'Sec-Fetch-User': '?1'
                        })
                        
                        # Try both GET and POST methods
                        for method in ['GET', 'POST']:
                            try:
                                if method == 'GET':
                                    response = await client.get(
                                        full_url,
                                        headers=search_headers,
                                        cookies=init_response.cookies,
                                        follow_redirects=True,
                                        timeout=httpx.Timeout(30.0, connect=10.0, read=20.0)
                                    )
                                else:
                                    response = await client.post(
                                        url,
                                        headers=search_headers,
                                        cookies=init_response.cookies,
                                        data=params,
                                        follow_redirects=True,
                                        timeout=10.0
                                    )
                                
                                if response.status_code == 200 and 'tweet-content' in response.text:
                                    logger.info(f"Successfully got tweets using {method} method")
                                    break
                            except Exception as e:
                                logger.warning(f"Failed with {method} method: {str(e)}")
                                continue
                    if response and response.status_code == 200:
                        logger.info(f"Successfully connected to search endpoint at {full_url}")
                        logger.debug(f"Response headers: {dict(response.headers)}")
                        
                        # Log the HTML structure we're trying to parse
                        logger.info("HTML Structure Preview:")
                        logger.info("=" * 80)
                        logger.info(f"Response from {instance}:")
                        logger.info(f"Status code: {response.status_code}")
                        logger.info(f"Content type: {response.headers.get('content-type', 'unknown')}")
                        logger.info(f"Content length: {len(response.text)} bytes")
                        logger.info("-" * 40)
                        logger.info("First 2000 characters of response:")
                        logger.info(response.text[:2000])
                        logger.info("-" * 40)
                        logger.info("Looking for tweet-content divs...")
                        tweet_divs = re.findall(r'<div class="tweet-content[^>]*>.*?</div>', response.text, re.DOTALL)
                        logger.info(f"Found {len(tweet_divs)} potential tweet divs")
                        if tweet_divs:
                            logger.info("First tweet div found:")
                            logger.info(tweet_divs[0][:200])
                        logger.info("=" * 80)
                        
                        # Single, reliable tweet pattern for better extraction
                        tweet_pattern = r'<div class="timeline-item[^>]*>.*?<div class="tweet-content[^>]*>(.*?)</div>.*?<div class="tweet-stats[^>]*>.*?<span class="tweet-stat[^>]*>.*?(\d+)</span>.*?<span class="tweet-stat[^>]*>.*?(\d+)</span>'
                        logger.info("Using optimized tweet extraction pattern")
                        
                        # Debug: Log HTML structure
                        logger.info("Analyzing HTML response structure...")
                        logger.info(f"Response length: {len(response.text)} bytes")
                        logger.info(f"First 500 chars: {response.text[:500]}")
                        
                        # Look for key HTML elements
                        key_elements = ['tweet-content', 'timeline-item', 'tweet-stats']
                        for element in key_elements:
                            count = response.text.count(element)
                            logger.info(f"Found {count} occurrences of '{element}'")
                        
                        # Multiple tweet patterns with more flexible matching
                        tweet_patterns = [
                            # Pattern 1: Most flexible timeline format
                            r'<div[^>]*class="[^"]*tweet[^"]*"[^>]*>.*?<div[^>]*class="[^"]*tweet-content[^"]*"[^>]*>(.*?)</div>.*?<div[^>]*class="[^"]*tweet-stats[^"]*"[^>]*>.*?(\d+)[^<]*(?:retweet|RT).*?(\d+)[^<]*(?:like|♥)',
                            # Pattern 2: Basic content with stats nearby
                            r'<div[^>]*class="[^"]*tweet-content[^"]*"[^>]*>(.*?)</div>(?:[^<]*<[^>]*>){0,50}?(?:(\d+)\s*(?:RT|retweet).*?(\d+)\s*(?:like|♥)|(\d+)\s*(?:like|♥).*?(\d+)\s*(?:RT|retweet))',
                            # Pattern 3: Minimal format with nearby numbers
                            r'<div[^>]*class="[^"]*tweet[^"]*"[^>]*>(?:[^<]*<[^>]*>)*?([^<]+)(?:[^<]*<[^>]*>){0,30}?(\d+)(?:[^<]*<[^>]*>){0,10}?(\d+)',
                        ]
                        
                        all_matches = []
                        for idx, pattern in enumerate(tweet_patterns, 1):
                            logger.info(f"Trying pattern {idx}...")
                            matches = list(re.finditer(pattern, response.text, re.DOTALL | re.IGNORECASE))
                            if matches:
                                logger.info(f"Pattern {idx} found {len(matches)} matches")
                                all_matches.extend(matches)
                                # Log first match details
                                match = matches[0]
                                logger.info(f"Sample match groups: {[match.group(i) for i in range(len(match.groups()) + 1)]}")
                                break
                            else:
                                logger.info(f"Pattern {idx} found no matches")
                        else:
                            logger.warning("No tweet matches found")
                            # Log HTML structure for debugging
                            logger.debug("HTML preview:")
                            logger.debug(response.text[:500])
                                
                        # Log HTML structure if no matches found with any pattern
                        if not matches:
                            logger.error("No matches found with any pattern. HTML structure:")
                            logger.error("=" * 80)
                            logger.error(response.text[:2000])
                            logger.error("=" * 80)
                        
                        found_tweets = False
                        
                        for match in matches:
                            if len(tweets) >= max_results:
                                found_tweets = True
                                logger.info(f"Reached max_results limit of {max_results}")
                                break
                                
                            try:
                                raw_content = match.group(1).strip()
                                logger.info(f"Raw tweet content found: {raw_content[:200]}")
                                
                                # Look for specific HTML markers that indicate this isn't a real tweet
                                if any(marker in raw_content.lower() for marker in ['no results', 'try again', 'error']):
                                    logger.warning("Skipping content that appears to be an error message")
                                    continue
                                    
                                # Validate content before processing
                                if not raw_content or len(raw_content) < 5:
                                    logger.warning("Skipping too short content")
                                    continue
                            except Exception as e:
                                logger.error(f"Error extracting content from match: {str(e)}")
                                continue
                            
                            # More thorough content cleaning
                            try:
                                # First remove nested tags if any
                                content = re.sub(r'<(?!/?div)[^>]+>', '', raw_content)
                                # Then remove any remaining HTML
                                content = re.sub(r'<[^>]+>', '', content)
                                # Normalize whitespace
                                content = re.sub(r'\s+', ' ', content)
                                # Handle common HTML entities
                                entities = {
                                    '&amp;': '&',
                                    '&lt;': '<',
                                    '&gt;': '>',
                                    '&quot;': '"',
                                    '&#39;': "'",
                                    '&nbsp;': ' ',
                                    '&ndash;': '-',
                                    '&mdash;': '—'
                                }
                                for entity, char in entities.items():
                                    content = content.replace(entity, char)
                                content = content.strip()
                                
                                logger.info(f"Cleaned content: {content[:200]}")
                                
                                if not content or len(content) < 5:
                                    logger.warning("Content too short after cleaning")
                                    continue
                            except Exception as e:
                                logger.error(f"Error cleaning content: {str(e)}")
                                continue
                            
                            # Look for metrics in surrounding context
                            context_start = max(0, match.start() - 200)
                            context_end = min(len(response.text), match.end() + 200)
                            context = response.text[context_start:context_end]
                            
                            retweets = 0
                            likes = 0
                            
                            # Try multiple metric patterns
                            rt_patterns = [
                                r'(\d+)\s*Retweets?',
                                r'(\d+)\s*RT',
                                r'icon-retweet[^>]*></span>\s*(\d+)',
                                r'retweet.*?(\d+)'
                            ]
                            
                            like_patterns = [
                                r'(\d+)\s*Likes?',
                                r'(\d+)\s*Like',
                                r'icon-heart[^>]*></span>\s*(\d+)',
                                r'like.*?(\d+)'
                            ]
                            
                            for pattern in rt_patterns:
                                rt_match = re.search(pattern, context, re.I)
                                if rt_match:
                                    try:
                                        retweets = int(rt_match.group(1))
                                        logger.info(f"Found retweets: {retweets}")
                                        break
                                    except (ValueError, IndexError):
                                        continue
                                        
                            for pattern in like_patterns:
                                like_match = re.search(pattern, context, re.I)
                                if like_match:
                                    try:
                                        likes = int(like_match.group(1))
                                        logger.info(f"Found likes: {likes}")
                                        break
                                    except (ValueError, IndexError):
                                        continue
                            
                            tweet_data = {
                                "content": content,
                                "metrics": {
                                    "retweets": retweets,
                                    "likes": likes
                                }
                            }
                            tweets.append(tweet_data)
                            logger.info(f"Successfully extracted tweet: {content[:100]}...")
                            found_tweets = True
                            
                            # Don't break here, collect all available tweets up to max_results
                                
                        if not found_tweets:
                            logger.warning(f"No tweets found in response from {instance}")
                    else:
                        logger.warning(f"Failed to get search results from {full_url}: {response.status_code if response else 'No response'}")
                except Exception as e:
                    logger.error(f"Error fetching search results from {full_url}: {str(e)}")
                    continue
                
                if response:
                    # Log the response content for debugging
                    logger.info(f"Response from {instance} RSS (status {response.status_code}):")
                    logger.info("=" * 80)
                    logger.info(response.text[:5000].replace("  ", ""))  # Remove extra spaces for cleaner logging
                    logger.info("=" * 80)
                    
                    if response.status_code == 429:
                        # Update rate limit reset time
                        retry_after = min(int(response.headers.get('retry-after', 15)), 30)  # Cap at 30 seconds
                        rate_limit_reset[instance] = datetime.now() + timedelta(seconds=retry_after)
                        instance_failures[instance] = instance_failures.get(instance, 0) + 1
                        logger.warning(f"Rate limited on {instance}, will retry after {retry_after}s (failure count: {instance_failures[instance]})")
                        # Log response details for debugging
                        logger.info(f"Response headers from {instance}: {dict(response.headers)}")
                        logger.info(f"Response content preview: {response.text[:500]}")
                        # Try next instance instead of continuing
                        break
                        
                    if response.status_code == 200:
                        try:
                            # Log response info for debugging
                            logger.info(f"Response from {instance} (status {response.status_code}):")
                            logger.info(f"Content length: {len(response.text)} bytes")
                            
                            # Single, reliable pattern for tweet extraction
                            tweet_pattern = r'<div class="timeline-item[^>]*>.*?<div class="tweet-content[^>]*>(.*?)</div>.*?<div class="tweet-stats[^>]*>.*?<span[^>]*>(\d+)</span>.*?<span[^>]*>(\d+)</span>'
                            matches = list(re.finditer(tweet_pattern, response.text, re.DOTALL | re.IGNORECASE))
                            
                            if not matches:
                                logger.warning(f"No tweets found in response from {instance}")
                                logger.info("HTML Structure Analysis:")
                                timeline_pattern = '<div class="timeline-item"[^>]*>'
                                content_pattern = '<div class="tweet-content"[^>]*>'
                                logger.info(f'- timeline-items: {len(re.findall(timeline_pattern, response.text))}')
                                logger.info(f'- tweet-content divs: {len(re.findall(content_pattern, response.text))}')
                                logger.info("First 1000 chars of response:")
                                logger.info(response.text[:1000] if response.text else "Empty response")
                                continue  # Try next instance
                                
                            logger.info(f"Found {len(matches)} tweets")
                            
                            for match in matches:
                                if len(tweets) >= max_results:
                                    break
                                    
                                try:
                                    # Extract and clean content
                                    content = match.group(1)
                                    content = re.sub(r'<[^>]+>', '', content)  # Remove HTML tags
                                    content = re.sub(r'&\w+;', lambda e: {
                                        '&amp;': '&',
                                        '&lt;': '<',
                                        '&gt;': '>',
                                        '&quot;': '"',
                                        '&#39;': "'",
                                        '&nbsp;': ' '
                                    }.get(e.group(), e.group()), content)  # Handle entities
                                    content = re.sub(r'\s+', ' ', content)  # Normalize whitespace
                                    content = content.strip()
                                    
                                    # Skip if content is too short or contains error messages
                                    if not content or len(content) < 5 or any(x in content.lower() for x in ['no results', 'error', 'try again']):
                                        continue
                                        
                                    # Extract metrics
                                    retweets = int(match.group(2))
                                    likes = int(match.group(3))
                                    
                                    tweet_data = {
                                        "content": content,
                                        "metrics": {
                                            "retweets": retweets,
                                            "likes": likes
                                        }
                                    }
                                    tweets.append(tweet_data)
                                    logger.info(f"Extracted tweet: {content[:100]}...")
                                except Exception as e:
                                    logger.error(f"Error processing tweet match: {str(e)}")
                                    continue
                            
                            if tweets:
                                logger.info(f"Successfully extracted {len(tweets)} tweets")
                                break
                            else:
                                logger.warning("No tweets found in response")
                                
                        except Exception as e:
                            logger.error(f"Error processing response: {str(e)}")
                            continue
                    
            except httpx.ConnectError as e:
                if "Name or service not known" in str(e):
                    logger.error(f"DNS resolution failed for {instance}, skipping...")
                else:
                    logger.error(f"Connection error with {instance}: {str(e)}")
                continue
            except Exception as e:
                logger.error(f"Unexpected error with {instance}: {str(e)}")
                continue
                
        # Only raise 503 if we've tried all instances and none worked
        if not tweets:
            logger.warning("No tweets found from any instance, trying alternative patterns")
            
            # Try different HTML patterns that might match Nitter's structure
            tweet_patterns = [
                # Pattern 1: Most permissive timeline item
                r'<div[^>]*timeline-item[^>]*>.*?<div[^>]*tweet-content[^>]*>(.*?)</div>.*?<div[^>]*tweet-stats[^>]*>.*?<span[^>]*>.*?(\d+)</span>.*?<span[^>]*>.*?(\d+)</span>',
                # Pattern 2: Flexible tweet content with stats
                r'<div[^>]*tweet-content[^>]*>(.*?)</div>.*?<div[^>]*tweet-stats[^>]*>.*?<span[^>]*>.*?(\d+)</span>.*?<span[^>]*>.*?(\d+)</span>',
                # Pattern 3: Any content with icon stats
                r'<div[^>]*>(.*?)</div>.*?<span[^>]*icon-retweet[^>]*></span>\s*(\d+).*?<span[^>]*icon-heart[^>]*></span>\s*(\d+)',
                # Pattern 4: Basic content with any stats
                r'<div[^>]*tweet-content[^>]*>(.*?)</div>.*?(\d+)[^<]*</span>.*?(\d+)[^<]*</span>',
                # Pattern 5: Most basic content match
                r'<div[^>]*tweet-content[^>]*>(.*?)</div>'
            ]
                
            if response and response.status_code == 200:
                found_tweets = False
                for pattern in tweet_patterns:
                    matches = re.finditer(pattern, response.text, re.DOTALL)
                    for match in matches:
                        if len(tweets) >= max_results:
                            found_tweets = True
                            break
                            
                        content = match.group(1).strip()
                        # Look for metrics in surrounding context
                        context_start = max(0, match.start() - 200)
                        context_end = min(len(response.text), match.end() + 200)
                        context = response.text[context_start:context_end]
                        
                        # Try to find retweets and likes in the context
                        retweets = 0
                        likes = 0
                        
                        # Log the context for debugging
                        logger.info("Tweet Context:")
                        logger.info("-" * 40)
                        logger.info(context)
                        logger.info("-" * 40)
                        
                        rt_match = re.search(r'<span class="icon-retweet"></span>\s*(\d+)', context)
                        if rt_match:
                            try:
                                retweets = int(rt_match.group(1))
                                logger.info(f"Found retweets: {retweets}")
                            except (ValueError, IndexError):
                                pass
                                
                        like_match = re.search(r'<span class="icon-heart"></span>\s*(\d+)', context)
                        if like_match:
                            try:
                                likes = int(like_match.group(1))
                                logger.info(f"Found likes: {likes}")
                            except (ValueError, IndexError):
                                pass
                        
                        # Clean HTML tags and entities more thoroughly
                        content = re.sub(r'<[^>]+>', ' ', content)  # Replace tags with space instead of empty string
                        content = re.sub(r'\s+', ' ', content)  # Normalize whitespace
                        content = content.replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">").replace("&quot;", '"').replace("&#39;", "'")
                        content = content.strip()
                        
                        if content:  # Only append if content is not empty
                            tweets.append({
                                "content": content,
                                "metrics": {
                                    "retweets": retweets,
                                    "likes": likes
                                }
                            })
                            found_tweets = True
                    
                    if found_tweets:
                        break
                        
                # Add debug logging
                if not found_tweets and response and response.status_code == 200:
                    logger.error(f"No tweets found in response. Response preview: {response.text[:500]}")
                
                if found_tweets:
                    # Cache successful results
                    CACHE[cache_key] = (tweets, datetime.now())
                    return tweets  # Return immediately if we found tweets
                    
                logger.warning(f"No tweets found in response from {instance}")
                
        # If we get here and still have no tweets, return an empty list instead of error
        if not tweets:
            logger.warning("No tweets found from any instance after trying all patterns")
            return []
        return tweets

@app.get("/search")
async def search_tweets(query: str, max_results: int = 10) -> Dict[str, Any]:
    try:
        tweets = await fetch_tweets(query, max_results)
        logger.info(f"Successfully fetched {len(tweets)} tweets for query: {query}")
        
        # Return success even with empty results, just indicate no tweets found
        status = "success" if tweets else "no_results"
        message = f"Found {len(tweets)} tweets" if tweets else "No tweets found for the given query"
        
        return {
            "status": status,
            "message": message,
            "results": tweets,
            "query": query,
            "count": len(tweets)
        }
    except Exception as e:
        logger.error(f"Unexpected error during tweet search: {str(e)}")
        return {
            "status": "error",
            "message": "Failed to fetch tweets, please try again later",
            "results": [],
            "query": query,
            "count": 0
        }

@app.get("/health")
async def health_check():
    return {"status": "healthy"}
