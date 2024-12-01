import aiohttp
import asyncio
import os
from configs import *
#from configs import SITE, API

####################  Tnlink  ####################

async def get_short(link):
    
    if not (API and SITE):
        return link
    
    https = link.split(":")[0]
    if "http" == https:
        https = "https"
        link = link.replace("http", https)
    url = f'https://{SITE}/api'
    params = {'api': API,
              'url': link,
              }

    async with aiohttp.ClientSession() as session:
        async with session.get(url, params=params, raise_for_status=True, ssl=False) as response:
            data = await response.json()
            if data["status"] == "success":
                return data['shortenedUrl']
            else:
                return f"Error: {data['message']}"
