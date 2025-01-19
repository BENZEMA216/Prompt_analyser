import asyncio
import httpx
from httpx import HTTPError, TimeoutException
import uvicorn
import multiprocessing
import time
import logging
from app.main import app

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

async def test_endpoints():
    logger = logging.getLogger(__name__)
    
    # Wait for server to start
    logger.info("Waiting for server startup...")
    time.sleep(5)  # Give more time for server startup
    
    timeout = httpx.Timeout(30.0, connect=10.0)
    limits = httpx.Limits(max_keepalive_connections=5, max_connections=10)
    
    async with httpx.AsyncClient(
        base_url="http://localhost:8000",
        timeout=timeout,
        limits=limits,
        follow_redirects=True
    ) as client:
        # Test health endpoint
        print("\nTesting health endpoint...")
        try:
            response = await client.get("/health")
            print(f"Health check response: {response.json()}")
            assert response.status_code == 200
            assert response.json()["status"] == "healthy"
        except Exception as e:
            print(f"Health check failed: {str(e)}")
            
        # Test English query
        logger.info("Testing English query...")
        try:
            logger.info("Sending request for English query: web3 blockchain")
            response = await client.get("/search", params={"query": "web3 blockchain", "max_results": 3})
            logger.info(f"Response status: {response.status_code}")
            
            response_data = None
            try:
                if response.status_code != 200:
                    logger.error(f"Error response: {response.text}")
                    raise HTTPError(f"HTTP {response.status_code}")
                
                response_data = response.json()
                logger.info(f"English query response: {response_data}")
                
                if not response_data.get("results"):
                    logger.error("No results found in response")
                    raise ValueError("No results in response data")
            except Exception as e:
                logger.error(f"Error processing response: {str(e)}")
                if response_data:
                    logger.error(f"Response data: {response_data}")
                raise
                
            logger.info(f"Found {len(response_data['results'])} tweets")
            for tweet in response_data["results"]:
                logger.info(f"Tweet content: {tweet.get('content', '')[:100]}...")
                logger.info(f"Tweet metrics: {tweet.get('metrics', {})}")
                
        except HTTPError as e:
            logger.error(f"English query HTTP error: {str(e)}")
            if hasattr(e, 'response'):
                logger.error(f"Response: {e.response.text if e.response else 'No response'}")
        except TimeoutException as e:
            logger.error(f"English query timed out: {str(e)}")
        except Exception as e:
            logger.error(f"English query failed: {str(e)}", exc_info=True)
            
        # Test Chinese query
        logger.info("\nTesting Chinese query...")
        try:
            logger.info("Sending request for Chinese query: 区块链 web3")
            response = await client.get("/search", params={"query": "区块链 web3", "max_results": 3})
            logger.info(f"Response status: {response.status_code}")
            
            response_data = None
            try:
                if response.status_code != 200:
                    logger.error(f"Error response: {response.text}")
                    raise HTTPError(f"HTTP {response.status_code}")
                
                response_data = response.json()
                logger.info(f"Chinese query response: {response_data}")
                
                if not response_data.get("results"):
                    logger.error("No results found in response")
                    raise ValueError("No results in response data")
            except Exception as e:
                logger.error(f"Error processing response: {str(e)}")
                if response_data:
                    logger.error(f"Response data: {response_data}")
                raise
                
            logger.info(f"Found {len(response_data['results'])} tweets")
            for tweet in response_data["results"]:
                logger.info(f"Tweet content: {tweet.get('content', '')[:100]}...")
                logger.info(f"Tweet metrics: {tweet.get('metrics', {})}")
                
        except HTTPError as e:
            logger.error(f"Chinese query HTTP error: {str(e)}")
            if hasattr(e, 'response'):
                logger.error(f"Response: {e.response.text if e.response else 'No response'}")
        except TimeoutException as e:
            logger.error(f"Chinese query timed out: {str(e)}")
        except Exception as e:
            logger.error(f"Chinese query failed: {str(e)}", exc_info=True)

def run_server():
    uvicorn.run(app, host="127.0.0.1", port=8000)

async def main():
    # Start server in a separate process
    server = multiprocessing.Process(target=run_server)
    server.start()
    
    try:
        await test_endpoints()
    finally:
        server.terminate()
        server.join()

if __name__ == "__main__":
    asyncio.run(main())
