import httpx
import asyncio
import json
from typing import Dict, Any

async def test_endpoint(url: str, params: Dict[str, Any] = {}) -> Dict[str, Any]:
    print(f"Testing URL: {url}")
    if params:
        print(f"With params: {params}")
    
    timeout = httpx.Timeout(30.0, connect=10.0)
    try:
        async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
            try:
                print("Sending request...")
                response = await client.get(url, params=params)
                print(f"Response status: {response.status_code}")
                response.raise_for_status()
                
                data = response.json() if response.text else None
                print(f"Response data received: {bool(data)}")
                return {
                    "status": response.status_code,
                    "data": data
                }
            except httpx.TimeoutException:
                print("Request timed out after 30 seconds")
                return {"status": "timeout", "data": None}
            except httpx.HTTPError as e:
                status = e.response.status_code if hasattr(e, 'response') else str(e)
                print(f"HTTP error: {status}")
                return {"status": status, "data": None}
    except Exception as e:
        print(f"Unexpected error: {str(e)}")
        return {"status": "error", "data": str(e)}

async def main():
    base_url = "https://app-zbeshewo.fly.dev"
    
    # Test health endpoint
    print("\nTesting health endpoint...")
    health_result = await test_endpoint(f"{base_url}/health")
    print(json.dumps(health_result, indent=2))
    
    # Test English query
    print("\nTesting English query...")
    english_result = await test_endpoint(
        f"{base_url}/search",
        {"query": "web3 blockchain", "max_results": 3}
    )
    print(json.dumps(english_result, indent=2))
    
    # Test Chinese query
    print("\nTesting Chinese query...")
    chinese_result = await test_endpoint(
        f"{base_url}/search",
        {"query": "区块链 web3", "max_results": 3}
    )
    print(json.dumps(chinese_result, indent=2))

if __name__ == "__main__":
    asyncio.run(main())
