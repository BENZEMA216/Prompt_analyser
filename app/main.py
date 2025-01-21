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
        ("https://nitter.privacydev.net", time.time()),
        ("https://nitter.cz", time.time()),
        ("https://nitter.unixfox.eu", time.time()),
        ("https://nitter.moomoo.me", time.time()),
        ("https://nitter.1d4.us", time.time()),
        ("https://nitter.kavin.rocks", time.time()),
        ("https://nitter.weiler.rocks", time.time()),
        ("https://nitter.sethforprivacy.com", time.time()),
        ("https://nitter.cutelab.space", time.time())
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
    
    # Very aggressive timeouts
    timeout = httpx.Timeout(5.0, connect=2.0, read=3.0)
    limits = httpx.Limits(max_keepalive_connections=5, max_connections=10)
    
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
        """Quick check if instance is responding."""
        try:
            url = f"{inst}/search?f=tweets&q=test"
            quick_timeout = httpx.Timeout(5.0, connect=2.0)
            
            async with httpx.AsyncClient(
                timeout=quick_timeout,
                headers=headers,
                verify=False,
                follow_redirects=True
            ) as client:
                logger.info(f"Testing instance {inst}...")
                response = await client.get(url)
                
                if response.status_code == 429:
                    logger.warning(f"Rate limited by {inst}")
                    return None
                    
                if response.status_code != 200:
                    logger.warning(f"Instance {inst} failed with status {response.status_code}")
                    return None
                
                if 'tweet-content' not in response.text:
                    logger.warning(f"Instance {inst} returned no tweet content")
                    return None
                
                logger.info(f"Successfully connected to {inst}")
                return inst
                
        except Exception as e:
            logger.warning(f"Instance {inst} error: {str(e)}")
            return None
    
    # Enhanced instance finding with detailed error tracking
    async def find_working_instance() -> Optional[str]:
        logger.info("Starting search for working Nitter instance...")
        total_instances = len(instances)
        failed_instances = 0
        error_summary = {}
        
        for inst in instances:
            try:
                logger.info(f"Trying instance {inst} ({failed_instances + 1}/{total_instances})")
                if result := await check_instance(inst):
                    # Update instance success time
                    timestamp = int(time.time() / 300) * 300
                    cached = get_cached_instances(timestamp)
                    updated = [(i[0], time.time() if i[0] == inst else i[1]) for i in cached]
                    get_cached_instances.cache_clear()
                    get_cached_instances(timestamp)  # Refresh cache with new times
                    logger.info(f"Successfully found working instance: {inst}")
                    return result
                failed_instances += 1
                if inst not in error_summary:
                    error_summary[inst] = "Failed instance check"
            except Exception as e:
                failed_instances += 1
                error_summary[inst] = str(e)
                logger.error(f"Error with instance {inst}: {str(e)}")
                continue
        
        # Log detailed error summary
        logger.error(f"All instances failed ({failed_instances}/{total_instances})")
        for inst, error in error_summary.items():
            logger.error(f"Instance {inst} failed with: {error}")
        return None
    
    # Find working instance with enhanced error handling
    instance = await find_working_instance()
    if not instance:
        logger.error("No working Nitter instances found. All instances failed or were unreachable.")
        raise HTTPException(
            status_code=503,
            detail="No available tweet search service found. Please try again later."
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
        
        async with httpx.AsyncClient(timeout=timeout, limits=limits, headers=headers) as client:
            response = await client.get(full_url, follow_redirects=True)
            
            if response.status_code != 200:
                raise HTTPException(
                    status_code=503,
                    detail="Tweet search service returned an error"
                )
            
            # Simple tweet extraction pattern
            tweet_pattern = r'<div class="tweet-content[^>]*>(.*?)</div>.*?<div class="tweet-stats[^>]*>.*?<span[^>]*>(\d+)</span>.*?<span[^>]*>(\d+)</span>'
            matches = list(re.finditer(tweet_pattern, response.text, re.DOTALL | re.IGNORECASE))
            
            if not matches:
                logger.warning("No tweets found in response")
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
