from fastapi import FastAPI, HTTPException
from typing import List, Dict, Any
import httpx
import logging
import re
from urllib.parse import quote_plus
import json

app = FastAPI()
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def fetch_tweets(query: str, max_results: int = 10) -> List[Dict[str, Any]]:
    """Fetch tweets directly from Twitter's web interface."""
    tweets: List[Dict[str, Any]] = []
    
    logger.info(f"Starting tweet search with query: {query}, max_results: {max_results}")
    
    # Optimized timeouts for Twitter's web interface
    timeout = httpx.Timeout(20.0, connect=5.0, read=15.0)
    
    # Enhanced headers to look more like a modern browser
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7',
        'Accept-Language': 'en-US,en;q=0.9,zh-CN;q=0.8,zh;q=0.7',
        'Accept-Encoding': 'gzip, deflate, br',
        'Cache-Control': 'max-age=0',
        'Connection': 'keep-alive',
        'Cookie': '_ga=GA1.1.1234567890.1234567890',
        'Dnt': '1',
        'Sec-Ch-Ua': '"Not_A Brand";v="8", "Chromium";v="120", "Google Chrome";v="120"',
        'Sec-Ch-Ua-Mobile': '?0',
        'Sec-Ch-Ua-Platform': '"Windows"',
        'Sec-Fetch-Dest': 'document',
        'Sec-Fetch-Mode': 'navigate',
        'Sec-Fetch-Site': 'none',
        'Sec-Fetch-User': '?1',
        'Upgrade-Insecure-Requests': '1'
    }
    
    try:
        # Direct X (Twitter) web search with additional parameters
        search_url = f"https://x.com/search?q={quote_plus(query)}%20-filter%3Areplies&f=live&pf=1"
        logger.info(f"Searching Twitter at: {search_url}")
        
        async with httpx.AsyncClient(timeout=timeout, headers=headers, follow_redirects=True) as client:
            response = await client.get(search_url)
            
            if response.status_code != 200:
                logger.error(f"Twitter search failed with status {response.status_code}")
                raise HTTPException(
                    status_code=503,
                    detail="Tweet search service returned an error"
                )
            
            content = response.text
            logger.info(f"Received response of {len(content)} bytes")
            # Log more details about the response
            logger.info(f"Response content length: {len(content)} bytes")
            logger.info(f"Response content preview: {content[:1000]}...")
            logger.info("Looking for tweet patterns...")
            
            # Extract tweets using x.com's HTML structure with bilingual support
            tweet_pattern = r'<article[^>]*>.*?<div[^>]*data-testid="tweetText"[^>]*>(.*?)</div>.*?<div[^>]*aria-label="(\d+)\s*(?:Retweet|转推)".*?<div[^>]*aria-label="(\d+)\s*(?:Like|喜欢)"'
            matches = list(re.finditer(tweet_pattern, content, re.DOTALL | re.IGNORECASE))
            
            if not matches:
                logger.warning("No tweets found in response")
                return []
                
            logger.info(f"Found {len(matches)} potential tweets")
            
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
        logger.error("Request timed out")
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
        return {
            "results": tweets,
            "query": query,
            "count": len(tweets)
        }
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
