from fastapi import FastAPI, HTTPException
from typing import List, Dict, Any, Optional
import httpx
import asyncio
import logging
import re
from urllib.parse import urlencode, quote_plus

app = FastAPI()
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def fetch_tweets(query: str, max_results: int = 10) -> List[Dict[str, Any]]:
    """Fetch tweets from Nitter with simplified error handling and request logic."""
    # List of Nitter instances to try
    instances = [
        "https://nitter.privacydev.net",
        "https://nitter.snopyta.org",
        "https://nitter.moomoo.me",
        "https://nitter.weiler.rocks",
        "https://nitter.sethforprivacy.com"
    ]
    instance = None  # Will be set to working instance
    tweets: List[Dict[str, Any]] = []
    
    logger.info(f"Starting tweet search with query: {query}, max_results: {max_results}")
    
    # Use more lenient timeouts
    timeout = httpx.Timeout(30.0, connect=10.0, read=20.0)
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
    async def check_instance() -> bool:
        """Quick check if instance is responding."""
        try:
            url = f"{instance}/search?f=tweets&q=test"
            timeout = httpx.Timeout(10.0, connect=5.0)
            
            async with httpx.AsyncClient(
                timeout=timeout,
                headers=headers,
                verify=False,  # Disable SSL verification temporarily
                follow_redirects=True,
                http2=True
            ) as client:
                logger.info(f"Testing instance {instance}...")
                response = await client.get(url)
                
                if response.status_code != 200:
                    logger.warning(f"Instance {instance} failed with status {response.status_code}")
                    if response.status_code == 302:
                        logger.warning(f"Redirect location: {response.headers.get('location', 'unknown')}")
                    return False
                
                if 'tweet-content' not in response.text:
                    logger.warning(f"Instance {instance} returned no tweet content")
                    return False
                
                logger.info(f"Successfully connected to {instance}")
                return True
                
        except httpx.TimeoutException as e:
            logger.warning(f"Instance {instance} timed out: {str(e)}")
            return False
        except httpx.HTTPError as e:
            logger.warning(f"Instance {instance} HTTP error: {str(e)}")
            return False
        except Exception as e:
            logger.warning(f"Instance {instance} error: {str(e)}")
            return False
                
        except Exception as e:
            logger.warning(f"Instance check failed: {str(e)}")
            return False
    
    # Quick parallel instance checks
    async def verify_instance():
        """Verify instance with one retry."""
        try:
            if await check_instance():
                return True
            # One retry after a short delay
            await asyncio.sleep(1)
            return await check_instance()
        except Exception as e:
            logger.warning(f"Instance verification failed: {str(e)}")
            return False
            
    # Try each instance until we find one that works
    for inst in instances:
        instance = inst
        logger.info(f"Trying Nitter instance: {instance}")
        if await verify_instance():
            logger.info(f"Successfully connected to {instance}")
            break
    else:
        logger.error("All Nitter instances failed")
        raise HTTPException(
            status_code=503,
            detail="Tweet search service is currently unavailable"
        )
        
    try:
        # Make the search request
        params = {
            "f": "tweets",
            "q": quote_plus(query)
        }
        url = f"{instance}/search"
        full_url = f"{url}?{urlencode(params)}"
        logger.info(f"Searching tweets at: {full_url}")
        
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
