from fastapi import FastAPI, HTTPException
from typing import List, Dict, Any, Optional, Tuple
import httpx
import asyncio
import logging
import re
import time
from urllib.parse import urlencode, quote_plus
from functools import lru_cache

app = FastAPI()
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Cache working instances for 5 minutes
@lru_cache(maxsize=1)
def get_cached_instances(timestamp: int = 0) -> List[Tuple[str, float]]:
    # Force cache invalidation every 5 minutes
    return [
        ("https://nitter.net", time.time()),
        ("https://nitter.1d4.us", time.time()),
        ("https://nitter.unixfox.eu", time.time()),
        ("https://nitter.moomoo.me", time.time()),
        ("https://nitter.weiler.rocks", time.time()),
        ("https://nitter.sethforprivacy.com", time.time()),
        ("https://nitter.cutelab.space", time.time()),
        ("https://nitter.freedit.eu", time.time()),
        ("https://nitter.twei.space", time.time()),
        ("https://nitter.inpt.fr", time.time())
    ]

def get_instances() -> List[str]:
    # Get timestamp rounded to 5 minute intervals
    timestamp = int(time.time() / 300) * 300
    instances = get_cached_instances(timestamp)
    # Sort by last success time, newest first
    sorted_instances = sorted(instances, key=lambda x: x[1], reverse=True)
    return [inst[0] for inst in sorted_instances]

async def fetch_tweets(query: str, max_results: int = 10) -> List[Dict[str, Any]]:
    """Fetch tweets from Nitter with aggressive timeouts and partial results."""
    instances = get_instances()
    tweets: List[Dict[str, Any]] = []
    
    logger.info(f"Starting tweet search with query: {query}, max_results: {max_results}")
    
    # Aggressive timeouts for parallel checking
    timeout = httpx.Timeout(30.0, connect=10.0, read=20.0)
    limits = httpx.Limits(max_keepalive_connections=10, max_connections=20)
    
    # Enhanced headers to look more like a real browser
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8',
        'Accept-Language': 'en-US,en;q=0.9,zh-CN;q=0.8,zh;q=0.7',
        'Accept-Encoding': 'gzip, deflate, br',
        'Cache-Control': 'no-cache',
        'Pragma': 'no-cache',
        'Upgrade-Insecure-Requests': '1'
    }

    # Simple instance check
    async def check_instance(inst: str) -> Optional[str]:
        """Check if instance is responding with enhanced redirect and content validation."""
        try:
            url = f"{inst}/search?f=tweets&q=test"
            quick_timeout = httpx.Timeout(10.0, connect=5.0, read=5.0)
            
            async with httpx.AsyncClient(
                timeout=quick_timeout,
                headers=headers,
                verify=False,
                follow_redirects=False,  # Don't follow redirects initially
                http2=False,
                transport=httpx.AsyncHTTPTransport(retries=1)
            ) as client:
                logger.info(f"Testing instance {inst}...")
                try:
                    # First request - check for redirects
                    response = await client.get(url)
                    logger.info(f"Initial response from {inst}: status={response.status_code}")
                    
                    # Handle redirects (301, 302, 307, 308)
                    if response.status_code in {301, 302, 307, 308}:
                        redirect_url = response.headers.get('location', '')
                        logger.warning(f"Instance {inst} redirected to: {redirect_url}")
                        
                        # Strict redirect validation
                        allowed_domains = ['nitter.net', 'twitter.com']
                        if not any(domain in redirect_url.lower() for domain in allowed_domains):
                            logger.warning(f"Invalid redirect target: {redirect_url}")
                            return None
                            
                        # If redirected to another Nitter instance, update the URL
                        if 'nitter' in redirect_url.lower():
                            url = redirect_url
                    
                    # Second request - follow redirects and validate content
                    response = await client.get(url, follow_redirects=True)
                    logger.info(f"Final response from {inst}: status={response.status_code}, size={len(response.text)} bytes")
                    
                    if 200 <= response.status_code < 300:
                        content = response.text.lower()
                        logger.info(f"Content check for {inst}: length={len(content)}")
                        
                        # Extremely lenient content validation
                        if len(content) < 50:  # Bare minimum size check
                            logger.warning(f"Response too short from {inst}: {len(content)} bytes")
                            return None
                            
                        # Only check for basic tweet indicator
                        if 'tweet' not in content.lower():
                            logger.warning(f"No tweet indicator found in response from {inst}")
                            return None
                            
                        logger.info(f"Successfully validated {inst}")
                        return inst
                    else:
                        logger.warning(f"Instance {inst} returned invalid status: {response.status_code}")
                        return None
                            
                    # Log specific error cases
                    if response.status_code == 429:
                        logger.warning(f"Rate limited by {inst}")
                    elif response.status_code == 403:
                        logger.warning(f"Access forbidden by {inst}")
                    elif response.status_code == 404:
                        logger.warning(f"Not found error from {inst}")
                    elif response.status_code >= 500:
                        logger.warning(f"Server error from {inst}: {response.status_code}")
                    else:
                        logger.warning(f"Unknown error from {inst}: {response.status_code}")
                        
                    if response.text:
                        logger.warning(f"Error response from {inst}: {response.text[:200]}")
                    return None
                        
                except httpx.TimeoutException as e:
                    logger.error(f"Timeout connecting to {inst}: {str(e)}")
                    return None
                except httpx.ConnectError as e:
                    logger.error(f"Connection error for {inst}: {str(e)}")
                    return None
                except httpx.RequestError as e:
                    logger.error(f"Request error for {inst}: {str(e)}")
                    return None
                except Exception as e:
                    logger.error(f"Unexpected error checking {inst}: {str(e)}")
                    return None
                    
        except Exception as e:
            logger.error(f"Unexpected error checking {inst}: {str(e)}")
            return None
    
    # Enhanced instance finding with sequential fallback
    async def find_working_instance() -> Optional[str]:
        logger.info("Starting search for working Nitter instance...")
        total_instances = len(instances)
        failed_count = 0
        error_summary: Dict[str, str] = {}
        
        # Try instances one at a time to avoid overwhelming them
        for inst in instances:
            try:
                logger.info(f"Checking instance {inst} ({failed_count + 1}/{total_instances})")
                if result := await check_instance(inst):
                    logger.info(f"Found working instance: {inst}")
                    return inst
                failed_count += 1
                error_summary[inst] = "Failed instance check"
            except Exception as e:
                error_msg = str(e)
                logger.error(f"Error checking instance {inst}: {error_msg}")
                failed_count += 1
                error_summary[inst] = error_msg
            
            # Short delay between instances
            await asyncio.sleep(1)
        
        # Log detailed error summary
        if failed_count == total_instances:
            logger.error(f"All instances failed ({failed_count}/{total_instances})")
            for inst, error in error_summary.items():
                logger.error(f"Instance {inst} failed with: {error}")
            return None
        return None
    
    # Find working instance with parallel checking
    instance = None
    
    # Try all instances in parallel
    async def check_instance_wrapper(inst):
        try:
            return await check_instance(inst)
        except Exception as e:
            logger.error(f"Error checking {inst}: {str(e)}")
            return None
    
    # Check all instances simultaneously
    instances = get_instances()
    tasks = [check_instance_wrapper(inst) for inst in instances]
    results = await asyncio.gather(*tasks, return_exceptions=True)
    
    # Use the first working instance
    for result in results:
        if result and isinstance(result, str):
            instance = result
            break
    
    if not instance:
        logger.error("No working Nitter instances found after all retry attempts.")
        raise HTTPException(
            status_code=503,
            detail="Tweet search service is temporarily unavailable. Please try again later."
        )
    
    try:
        # Make the search request with detailed logging
        params = {
            "f": "tweets",
            "q": quote_plus(query)
        }
        url = f"{instance}/search"
        full_url = f"{url}?{urlencode(params)}"
        logger.info(f"Attempting tweet search at: {full_url}")
        
        async with httpx.AsyncClient(
                timeout=timeout,
                limits=limits,
                headers=headers,
                verify=False,
                follow_redirects=True,
                http2=False,  # Explicitly disable HTTP/2
                transport=httpx.AsyncHTTPTransport(retries=3)  # Add retries
            ) as client:
            response = await client.get(full_url)
            
            if response.status_code != 200:
                raise HTTPException(
                    status_code=503,
                    detail="Tweet search service returned an error"
                )
            
            # More lenient tweet extraction pattern with detailed logging
            logger.info(f"Response content length: {len(response.text)} bytes")
            logger.info(f"First 500 chars of response: {response.text[:500]}")
            
            # Try different tweet patterns from most specific to least specific
            tweet_patterns = [
                # Original pattern
                r'<div class="tweet-content[^>]*>(.*?)</div>.*?<div class="tweet-stats[^>]*>.*?<span[^>]*>(\d+)</span>.*?<span[^>]*>(\d+)</span>',
                # More lenient pattern - just look for tweet content
                r'<div class="tweet-content[^>]*>(.*?)</div>',
                # Super lenient pattern - any div with content
                r'<div[^>]*class="[^"]*tweet[^"]*"[^>]*>(.*?)</div>'
            ]
            
            matches = []
            for pattern in tweet_patterns:
                logger.info(f"Trying pattern: {pattern}")
                current_matches = list(re.finditer(pattern, response.text, re.DOTALL | re.IGNORECASE))
                if current_matches:
                    logger.info(f"Found {len(current_matches)} matches with pattern")
                    matches = current_matches
                    break
            
            if not matches:
                logger.warning("No tweets found with any pattern")
                # Log some HTML structure information
                structure_sample = re.sub(r'>\s+<', '><', response.text[:1000])  # Clean up whitespace
                logger.info(f"HTML structure sample: {structure_sample}")
                return []
            
            logger.info(f"Found {len(matches)} tweets")
            
            # Process matches
            for match in matches[:max_results]:
                try:
                    # Extract and clean content
                    content = match.group(1).strip()
                    content = re.sub(r'<[^>]+>', '', content)  # Remove HTML tags
                    content = re.sub(r'\s+', ' ', content)  # Normalize whitespace
                    content = content.replace('&amp;', '&').replace('&lt;', '<').replace('&gt;', '>').replace('&quot;', '"').replace('&#39;', "'")
                    content = content.strip()
                    
                    if not content or len(content) < 5:
                        continue
                    
                    # Extract metrics
                    try:
                        retweets = int(match.group(2))
                        likes = int(match.group(3))
                    except (IndexError, ValueError):
                        retweets = 0
                        likes = 0
                    
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
                    logger.error(f"Error processing tweet: {str(e)}")
                    continue
            
            return tweets
            
    except httpx.TimeoutException:
        raise HTTPException(
            status_code=503,
            detail="Request timed out"
        )
    except Exception as e:
        logger.error(f"Error fetching tweets: {str(e)}")
        raise HTTPException(
            status_code=503,
            detail="Failed to fetch tweets"
        )

@app.get("/search")
async def search_tweets(query: str, max_results: int = 10):
    """Search for tweets with the given query."""
    try:
        tweets = await fetch_tweets(query, max_results)
        return {"results": tweets, "source": "nitter"}
    except HTTPException as e:
        raise e
    except Exception as e:
        logger.error(f"Unexpected error: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail="Internal server error"
        )

@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {"status": "healthy"}
