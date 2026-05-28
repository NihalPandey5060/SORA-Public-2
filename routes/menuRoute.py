from fastapi import APIRouter, Depends, HTTPException, status # type: ignore 
from db import get_db
from model import MenuItem
import redis # type: ignore
import json
from typing import Optional
redis_client: Optional[redis.Redis] = None

CACHE_TTL = 3600 


menu_router = APIRouter(prefix="/api/menu", tags=["menu"]) 

@menu_router.get("/")
async def get_menu(db=Depends(get_db)):
    cache_key = "menu:all"

    if redis_client:
        try:
            cached_data = redis_client.get(cache_key)
            if cached_data:
                return json.loads(cached_data.decode('utf-8'))
        except Exception as e:
            print(f"Redis cache read error: {e}")
    

    menu_items = db.query(MenuItem).all()
    
    result = [
        {
            "id": item.id,
            "category": item.category,
            "name": item.name,
            "price": item.price,
            "description": item.description
        }
        for item in menu_items
    ]
    

    if redis_client:
        try:
            redis_client.setex(cache_key, CACHE_TTL, json.dumps(result))
        except Exception as e:
            print(f"Redis cache write error: {e}")
    
    return result 