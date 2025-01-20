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
        "https://nitter.net",
        "https://nitter.1d4.us",
        "https://nitter.kavin.rocks",
        "https://nitter.unixfox.eu",
        "https://nitter.fdn.fr",
        "https://nitter.cz",
        "https://nitter.privacydev.net",
        "https://nitter.poast.org",
        "https://nitter.mint.lgbt",
        "https://nitter.esmailelbob.xyz"
    ]
    
    logger.info(f"Starting tweet search with query: {query}, max_results: {max_results}")
    logger.info(f"Available Nitter instances: {instances}")

    # Verify instance availability before using
    available_instances = []
    for instance in instances:
        try:
            health_check_url = f"{instance}/robots.txt"
            logger.info(f"Checking availability of {instance}")
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(health_check_url, follow_redirects=True)
                logger.info(f"Health check response from {instance}: {response.status_code}")
                
                if response.status_code == 200:
                    available_instances.append(instance)
                    logger.info(f"Instance {instance} is available")
                else:
                    logger.warning(f"Instance {instance} returned status {response.status_code}")
                    if 'location' in response.headers:
                        logger.warning(f"Redirect location: {response.headers['location']}")
        except httpx.TimeoutException:
            logger.warning(f"Instance {instance} timed out during health check")
            continue
        except httpx.HTTPError as e:
            logger.warning(f"HTTP error checking {instance}: {str(e)}")
            continue
        except Exception as e:
            logger.warning(f"Instance {instance} is not available: {str(e)}")
            continue
            
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
                        
                        # Log the HTML structure we're trying to parse
                        logger.info("HTML Structure Preview:")
                        logger.info("=" * 80)
                        logger.info(response.text[:2000])
                        logger.info("=" * 80)
                        
                        # Try multiple tweet patterns with metrics
                        tweet_patterns = [
                            r'<div class="timeline-item[^>]*>.*?<div class="tweet-content[^>]*>(.*?)</div>.*?<div class="tweet-stats">.*?<span class="tweet-stat">.*?(\d+)</span>.*?<span class="tweet-stat">.*?(\d+)</span>',
                            r'<div class="tweet-content[^>]*>(.*?)</div>.*?<div class="tweet-stats">.*?<span class="icon-retweet"></span>\s*(\d+).*?<span class="icon-heart"></span>\s*(\d+)',
                            r'<div class="timeline-item.*?<div class="tweet-content.*?>(.*?)</div>.*?<span class="icon-retweet"></span>\s*(\d+).*?<span class="icon-heart"></span>\s*(\d+)',
                            r'<div class="tweet-body.*?<div class="tweet-content.*?>(.*?)</div>.*?<div class="tweet-stats">.*?<span class="tweet-stat">.*?(\d+)</span>.*?<span class="tweet-stat">.*?(\d+)</span>'
                        ]
                        
                        matches = []
                        for pattern in tweet_patterns:
                            logger.info(f"Trying pattern: {pattern}")
                            current_matches = list(re.finditer(pattern, response.text, re.DOTALL))
                            if current_matches:
                                logger.info(f"Found {len(current_matches)} matches with pattern")
                                matches.extend(current_matches)
                                break
                            else:
                                logger.warning(f"No matches found with pattern")
                        
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
                            # Updated pattern based on actual Nitter HTML structure
                            tweet_pattern = r'<div class="timeline-item.*?<div class="tweet-content.*?>(.*?)</div>.*?<div class="tweet-stats">.*?<span class="icon-retweet"></span>\s*(\d+).*?<span class="icon-heart"></span>\s*(\d+)'
                            
                            matches = list(re.finditer(tweet_pattern, response.text, re.DOTALL))
                            logger.info(f"Found {len(matches)} potential tweets in HTML response")
                            logger.debug(f"HTML content snippet: {response.text[:500]}...")
                            
                            for match in matches:
                                if len(tweets) >= max_results:
                                    break
                                    
                                try:
                                    content = match.group(1).strip()
                                    retweets = int(match.group(2))
                                    likes = int(match.group(3))
                                    
                                    # Clean content
                                    content = re.sub(r'<[^>]+>', '', content)
                                    content = re.sub(r'\s+', ' ', content)
                                    content = content.strip()
                                    
                                    if content and len(content) > 5:
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
    try:
        tweets = await fetch_tweets(query, max_results)
        logger.info(f"Successfully fetched {len(tweets)} tweets for query: {query}")
        return {
            "status": "success",
            "results": tweets,
            "query": query,
            "count": len(tweets)
        }
    except HTTPException as e:
        logger.error(f"HTTP error during tweet search: {str(e)}")
        raise
    except Exception as e:
        logger.error(f"Unexpected error during tweet search: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Internal server error: {str(e)}"
        )

@app.get("/health")
async def health_check():
    return {"status": "healthy"}
