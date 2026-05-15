from fastapi import Depends, HTTPException, status
from fastapi.security import APIKeyHeader

from .. import config

api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)


async def require_api_key(api_key: str = Depends(api_key_header)):
    if not config.API_KEY or api_key != config.API_KEY:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid API key")
