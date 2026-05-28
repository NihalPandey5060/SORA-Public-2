from fastapi import APIRouter, Depends, HTTPException
from models import plugins
import requests
import os
from dotenv import load_dotenv

load_dotenv()
API_KEY = os.getenv("OPENWEATHER_API_KEY")

plug_router = APIRouter(prefix="/api/plugins", tags=["plugins"])

@plug_router.get("/weather", status_code=200)
async def get_weather(plugin: plugins.OpenWeatherPlugin = Depends()):
    response = requests.get(f'https://api.openweathermap.org/data/2.5/weather?lat={plugin.lat}&lon={plugin.long}&appid={API_KEY}&units={plugin.units}&mode={plugin.mode}&lang={plugin.lang}')
    if(response.status_code != 200):
        raise HTTPException(status_code=500, detail="Error fetching weather data")
    weather_data = {}
    if plugin.mode == "json":
        weather_data = response.json()
    else:
        weather_data = response.text
    return {"message": "working_fine", "data": weather_data}