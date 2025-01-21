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
    
    # Enhanced headers to look more like a real browser
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
        'Accept-Language': 'en-US,en;q=0.9,zh-CN;q=0.8,zh;q=0.7',
        'Accept-Encoding': 'gzip, deflate, br',
        'DNT': '1',
        'Connection': 'keep-alive',
        'Upgrade-Insecure-Requests': '1',
        'Sec-Fetch-Dest': 'document',
        'Sec-Fetch-Mode': 'navigate',
        'Sec-Fetch-Site': 'none',
        'Sec-Fetch-User': '?1',
        'Cache-Control': 'max-age=0'
    }
    
    try:
        # Direct Twitter web search
        search_url = f"https://twitter.com/search?q={quote_plus(query)}&f=live"
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
            
            # Extract tweets using a more robust pattern for Twitter's HTML structure
            tweet_pattern = r'<article[^>]*>.*?<div[^>]*>(?P<content>.*?)</div>.*?<div[^>]*>(?P<metrics>.*?)</div>.*?</article>'
            matches = list(re.finditer(tweet_pattern, content, re.DOTALL | re.IGNORECASE))
            
            if not matches:
                logger.warning("No tweets found in response")
                return []
                
            logger.info(f"Found {len(matches)} potential tweets")
            
            # Process matches
            for match in matches[:max_results]:
                try:
                    # Extract and clean content
                    content = match.group('content')
                    metrics_text = match.group('metrics')
                    
                    # Clean content
                    content = re.sub(r'<[^>]+>', '', content)
                    content = re.sub(r'\s+', ' ', content)
                    content = content.strip()
                    
                    if not content or len(content) < 10:
                        continue
                    
                    # Extract metrics with more flexible patterns
                    retweets = re.search(r'(\d+)[^\d]*(?:Retweet|RT)', metrics_text)
                    likes = re.search(r'(\d+)[^\d]*(?:Like|❤)', metrics_text)
                    
                    tweet_data = {
                        "content": content,
                        "metrics": {
                            "retweets": int(retweets.group(1)) if retweets else 0,
                            "likes": int(likes.group(1)) if likes else 0
                        }
                    }
                    
                    # Log the extracted data for debugging
                    logger.info(f"Extracted tweet: {json.dumps(tweet_data, ensure_ascii=False)[:200]}...")
                    tweets.append(tweet_data)
                    
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
    
    try:
        # Direct Twitter web search
        search_url = f"https://twitter.com/search?q={quote_plus(query)}&f=live"
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
            
            # Extract tweets using a more robust pattern for Twitter's HTML structure
            tweet_pattern = r'<article[^>]*>.*?<div[^>]*>(?P<content>.*?)</div>.*?<div[^>]*>(?P<metrics>.*?)</div>.*?</article>'
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
