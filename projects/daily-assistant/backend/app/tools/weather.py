
import os
from fmiopendata.wfs import download_stored_query

async def today_weather(state):
   
    if isinstance(state, dict):
        wanted = state.get("place") or state.get("city")
        if isinstance(wanted, str) and wanted.strip():
            os.environ["DEFAULT_CITY"] = wanted.strip()

    city = os.getenv("DEFAULT_CITY", "Lappeenranta")
    result = download_stored_query("fmi::observations::weather::cities::multipointcoverage", [f"place={city}"])
    
    if not result or not getattr(result, "data", None):
        return {"result": f"No weather data found for {city}"}
    
    stations = list(result.data.keys())
    last = stations[len(stations)-1]
    station = next((s for s in result.data[last] if city.lower() in s.lower()), None)
    
    data = result.data[last][station]
    tempr = data["Air temperature"]["value"]
    return {"result": f"Temperature in {city} is {tempr} °C, wind speed is {data['Wind speed']['value']} m/s recorded at {last}"}