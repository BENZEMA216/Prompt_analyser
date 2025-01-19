from fastapi import FastAPI, HTTPException
from typing import List, Dict, Any, Optional, Tuple, Union
import httpx
import asyncio
import logging
import re
import random
from datetime import datetime, timedelta
from functools import lru_cache
import hashlib
from xml.etree import ElementTree as ET
from io import StringIO

app = FastAPI()
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Cache for storing successful responses
CACHE: Dict[str, Tuple[List[Dict[str, Any]], datetime]] = {}

async def retry_get(client: httpx.AsyncClient, url: str, max_retries: int = 3) -> Optional[httpx.Response]:
    for attempt in range(max_retries):
        try:
            delay = (2 ** attempt) * 2  # Increased exponential backoff
            if attempt > 0:
                logger.info(f"Waiting {delay} seconds before retry...")
                await asyncio.sleep(delay)
            
            logger.info(f"Attempting request to {url} (attempt {attempt + 1}/{max_retries})")
            logger.info(f"Attempting request to {url} with instance {url.split('/')[2]}")
            
            # Use longer timeout for RSS feeds
            timeout = httpx.Timeout(30.0, connect=10.0, read=20.0)
            
            response = await client.get(
                url,
                timeout=timeout,
                follow_redirects=True,
                headers={
                    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
                    'Accept': 'application/rss+xml,application/xml;q=0.9,*/*;q=0.8',
                    'Accept-Language': 'en-US,en;q=0.5',
                    'Connection': 'keep-alive'
                }
            )
            
            # Log response details for debugging
            if response.status_code != 200:
                logger.error(f"Non-200 response from {url.split('/')[2]}: {response.status_code}")
                if 'location' in response.headers:
                    logger.error(f"Redirect location: {response.headers['location']}")
                logger.error(f"Response headers: {dict(response.headers)}")
                logger.error(f"Response text: {response.text[:500]}...")
            
            # Don't raise for 429, handle it in the retry loop
            if response.status_code == 429:
                retry_after = int(response.headers.get('retry-after', delay))
                logger.warning(f"Rate limited. Waiting {retry_after} seconds...")
                await asyncio.sleep(retry_after)
                continue
                
            response.raise_for_status()
            return response
            
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

def is_cache_valid(cache_time: datetime, max_age_minutes: int = 5) -> bool:
    """Check if cached data is still valid."""
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

    # Multiple Nitter instances with fallback
    instances = [
        "https://nitter.privacytools.io",
        "https://nitter.1d4.us",
        "https://nitter.kavin.rocks",
        "https://nitter.unixfox.eu",
        "https://nitter.poast.org",
        "https://nitter.bird.froth.zone"
    ]

    # Verify instance availability before using
    available_instances = []
    for instance in instances:
        try:
            health_check_url = f"{instance}/robots.txt"
            logger.info(f"Checking availability of {instance}")
            async with httpx.AsyncClient(timeout=5.0) as client:
                response = await client.get(health_check_url)
                if response.status_code == 200:
                    available_instances.append(instance)
                    logger.info(f"Instance {instance} is available")
        except Exception as e:
            logger.warning(f"Instance {instance} is not available: {str(e)}")
            continue

    if not available_instances:
        raise HTTPException(
            status_code=503,
            detail="No Nitter instances are currently available"
        )

    instances = available_instances
    
    # User-Agent rotation
    user_agents = [
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:89.0) Gecko/20100101 Firefox/89.0',
        'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/14.1.1 Safari/605.1.15'
    ]
    
    # Rate limit tracking
    rate_limit_reset = {}
    for instance in instances:
        if instance not in rate_limit_reset:
            rate_limit_reset[instance] = datetime.now()
    
    # Validate and encode query
    if not query:
        raise HTTPException(status_code=400, detail="Query parameter is required")
    tweets = []
    timeout = httpx.Timeout(15.0, connect=5.0, read=10.0)
    limits = httpx.Limits(max_keepalive_connections=5, max_connections=10)
    
    async with httpx.AsyncClient(timeout=timeout, limits=limits) as client:
        response = None
        for instance in instances:
            # Check rate limit
            if datetime.now() < rate_limit_reset.get(instance, datetime.now()):
                logger.warning(f"Rate limit in effect for {instance}, skipping...")
                continue
                
            # Rotate User-Agent
            headers = {'User-Agent': random.choice(user_agents)}
            client.headers = headers
            
            try:
                # Use HTML search endpoint
                params = {"f": "tweets", "q": query}
                url = f"{instance}/search"
                
                # Construct URL with proper query parameters
                full_url = url + "?" + str(httpx.QueryParams(params))
                logger.info(f"Trying HTML search from {full_url}")
                
                try:
                    response = await retry_get(client, full_url)
                    if response and response.status_code == 200:
                        logger.info(f"Successfully connected to search endpoint at {full_url}")
                        logger.debug(f"Response headers: {dict(response.headers)}")
                        
                        # Try different HTML patterns that might match Nitter's structure
                        tweet_patterns = [
                            r'<div class="timeline-item[^>]*>.*?<div class="tweet-content[^>]*>(.*?)</div>.*?<div class="tweet-stats[^>]*>.*?<span class="tweet-stat[^>]*>.*?(\d+)</span>.*?<span class="tweet-stat[^>]*>.*?(\d+)</span>',
                            r'<div class="tweet-content[^>]*>(.*?)</div>.*?<div class="tweet-stats[^>]*>.*?<span class="tweet-stat[^>]*>.*?(\d+)</span>.*?<span class="tweet-stat[^>]*>.*?(\d+)</span>',
                            r'<div class="timeline-item[^>]*>.*?<div class="tweet-content[^>]*>(.*?)</div>.*?<span class="icon-retweet"></span>\s*(\d+).*?<span class="icon-heart"></span>\s*(\d+)'
                        ]
                        
                        found_tweets = False
                        for pattern in tweet_patterns:
                            matches = re.finditer(pattern, response.text, re.DOTALL)
                            for match in matches:
                                if len(tweets) >= max_results:
                                    found_tweets = True
                                    break
                                    
                                content = match.group(1).strip()
                                try:
                                    retweets = int(match.group(2))
                                    likes = int(match.group(3))
                                except (ValueError, IndexError) as e:
                                    logger.warning(f"Failed to parse metrics: {str(e)}")
                                    retweets = 0
                                    likes = 0
                                
                                # Clean HTML tags and entities
                                content = re.sub(r'<[^>]+>', ' ', content)
                                content = re.sub(r'\s+', ' ', content)
                                content = content.replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">").replace("&quot;", '"').replace("&#39;", "'")
                                content = content.strip()
                                
                                if content:
                                    tweets.append({
                                        "content": content,
                                        "metrics": {
                                            "retweets": retweets,
                                            "likes": likes
                                        }
                                    })
                                    logger.info(f"Extracted tweet: {content[:100]}...")
                            
                            if found_tweets:
                                break
                                
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
                        retry_after = int(response.headers.get('retry-after', 60))
                        rate_limit_reset[instance] = datetime.now() + timedelta(seconds=retry_after)
                        logger.warning(f"Rate limited on {instance}, will retry after {retry_after}s")
                        continue
                        
                    if response.status_code == 200:
                        try:
                            # Parse XML response
                            tree = ET.parse(StringIO(response.text))
                            root = tree.getroot()
                            
                            # Extract tweets from RSS items
                            for item in root.findall('.//item'):
                                if len(tweets) >= max_results:
                                    break
                                    
                                # Get tweet content (remove HTML tags)
                                description_elem = item.find('description')
                                if description_elem is None or description_elem.text is None:
                                    logger.warning("Skipping item: missing description")
                                    continue
                                    
                                content: str = description_elem.text
                                content = re.sub(r'<[^>]+>', '', content)
                                content = content.strip()
                                
                                # Get metrics from title (usually contains retweet/like counts)
                                title_elem = item.find('title')
                                title: str = title_elem.text if title_elem is not None and title_elem.text is not None else ""
                                
                                # Try different metric patterns
                                metric_patterns = [
                                    r'(\d+)\s*RTs?,\s*(\d+)\s*likes?',
                                    r'(\d+)\s*Retweets?,\s*(\d+)\s*Likes?',
                                    r'RT:(\d+)\s*Like:(\d+)',
                                ]
                                
                                retweets = 0
                                likes = 0
                                for pattern in metric_patterns:
                                    metrics_match = re.search(pattern, title)
                                    if metrics_match:
                                        try:
                                            retweets = int(metrics_match.group(1))
                                            likes = int(metrics_match.group(2))
                                            break
                                        except (ValueError, IndexError) as e:
                                            logger.warning(f"Failed to parse metrics with pattern {pattern}: {str(e)}")
                                            continue
                                
                                if content:
                                    tweet_data = {
                                        "content": content,
                                        "metrics": {
                                            "retweets": retweets,
                                            "likes": likes
                                        }
                                    }
                                    tweets.append(tweet_data)
                                    logger.info(f"Extracted tweet: {tweet_data}")
                            
                            if tweets:
                                logger.info(f"Successfully extracted {len(tweets)} tweets from RSS feed")
                                break
                            else:
                                logger.warning("No tweets found in RSS feed")
                                
                        except ET.ParseError as e:
                            logger.error(f"Failed to parse RSS feed: {str(e)}")
                            continue
                        except Exception as e:
                            logger.error(f"Error processing RSS feed: {str(e)}")
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
                
        if not response or response.status_code != 200:
            raise HTTPException(
                status_code=503,
                detail="Failed to fetch tweets from all available instances"
            )
            
            # Log the first part of the response for debugging
            logger.info(f"Response preview: {response.text[:1000]}")
            
            if response and response.status_code == 200:
                # Try different HTML patterns that might match Nitter's structure
                tweet_patterns = [
                    r'<div class="timeline-item[^>]*>.*?<div class="tweet-content[^>]*>(.*?)</div>.*?<div class="tweet-stats[^>]*>.*?<span class="tweet-stat[^>]*>.*?(\d+)</span>.*?<span class="tweet-stat[^>]*>.*?(\d+)</span>',
                    r'<div class="tweet-content[^>]*>(.*?)</div>.*?<div class="tweet-stats[^>]*>.*?<span class="tweet-stat[^>]*>.*?(\d+)</span>.*?<span class="tweet-stat[^>]*>.*?(\d+)</span>',
                    r'<div class="timeline-item[^>]*>.*?<div class="tweet-content[^>]*>(.*?)</div>.*?<span class="icon-retweet"></span>\s*(\d+).*?<span class="icon-heart"></span>\s*(\d+)'
                ]
                
                found_tweets = False
                for pattern in tweet_patterns:
                    matches = re.finditer(pattern, response.text, re.DOTALL)
                    for match in matches:
                        if len(tweets) >= max_results:
                            found_tweets = True
                            break
                            
                        content = match.group(1).strip()
                        try:
                            retweets = int(match.group(2))
                            likes = int(match.group(3))
                        except (ValueError, IndexError) as e:
                            logger.warning(f"Failed to parse metrics: {str(e)}")
                            retweets = 0
                            likes = 0
                        
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
                if not found_tweets:
                    logger.error(f"No tweets found in response. Response preview: {response.text[:500]}")
                
                if found_tweets:
                    # Cache successful results
                    CACHE[cache_key] = (tweets, datetime.now())
                    return tweets  # Return immediately if we found tweets
                    
                logger.warning(f"No tweets found in response from {instance}")
                
        # If we get here, no tweets were found from any instance
        raise HTTPException(
            status_code=503,
            detail="No tweets found from any available instance"
        )

@app.get("/search")
async def search_tweets(query: str, max_results: int = 10) -> Dict[str, Any]:
    tweets = await fetch_tweets(query, max_results)
    return {"results": tweets}

@app.get("/health")
async def health_check():
    return {"status": "healthy"}
