from fastapi import HTTPException, Security, Depends
from fastapi.security.api_key import APIKeyHeader

API_KEY = "mysecureapikey"  # Replace with a secure key from environment variables
API_KEY_NAME = "X-API-Key"
api_key_header = APIKeyHeader(name=API_KEY_NAME, auto_error=True)

def get_api_key(api_key: str = Depends(api_key_header)):
    if api_key != API_KEY:
        raise HTTPException(status_code=403, detail="Could not validate API key")
    return api_key