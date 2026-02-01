
from apify_client import ApifyClientAsync
from dotenv import load_dotenv
from urllib.parse import urlencode
import logging
import asyncio
import os
import re

import requests
load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
)

class JobScraper:
    def __init__(self, run_config):
        self.run_config = run_config
        self.source = run_config.get("source", "seek")
        self.client = None
        if self.source != "ufl":
            self.client = ApifyClientAsync(os.getenv("APIFY_KEY"))
        
    async def scrape(self, actor=None):
        if self.source == "ufl":
            return await asyncio.to_thread(self._scrape_ufl)
        try:
            all_data = {}
            tasks = []
            searchTerms = []
            for query in self.run_config['searchTerms']:
                config = {k: v for k, v in self.run_config.items() if k != 'searchTerms'}
                config['searchTerm'] = query
                searchTerms.append(query)
                tasks.append(self.client.actor(actor).call(run_input=config))
            
            responses = await asyncio.gather(*tasks, return_exceptions=True)
            for searchTerm, response in zip(searchTerms, responses):
                if isinstance(response, Exception):
                    continue
                all_data[searchTerm] = await self._get_dataset(response)

            return all_data
        except Exception as e:
            logging.error(e)
            return []

    def _scrape_ufl(self):
        filters = self.run_config.get("filters", {})
        base_url = self.run_config.get("base_url", "https://explore.jobs.ufl.edu/en-us/filter/")
        params = []
        if filters.get("search_keyword") is not None:
            params.append(("search-keyword", filters.get("search_keyword", "")))
        for work_type in filters.get("work_types", []):
            params.append(("work-type", work_type))
        for category in filters.get("categories", []):
            params.append(("category", category))
        for location in filters.get("locations", []):
            params.append(("location", location))
        if filters.get("job_mail_subscribe_privacy"):
            params.append(("job-mail-subscribe-privacy", filters["job_mail_subscribe_privacy"]))

        query_string = urlencode(params, doseq=True)
        url = f"{base_url}?{query_string}" if query_string else base_url
        headers = {"User-Agent": self.run_config.get("user_agent", "Mozilla/5.0")}

        try:
            response = requests.get(url, headers=headers, timeout=30)
            response.raise_for_status()
        except Exception as exc:
            logging.error(f"Failed to fetch UF listing page: {exc}")
            return []

        return self._parse_ufl_listings(response.text)

    def _parse_ufl_listings(self, html_text):
        jobs = []
        for match in re.finditer(r'<a[^>]+href="(?P<link>[^"]+)"[^>]*>(?P<title>[^<]+)</a>', html_text):
            link = match.group("link")
            title = match.group("title").strip()
            if "/en-us/job/" not in link:
                continue
            job_id = link.rstrip("/").split("/")[-1]
            jobs.append(
                {
                    "id": job_id,
                    "title": title,
                    "jobLink": f"https://explore.jobs.ufl.edu{link}",
                    "location": "",
                    "category": "",
                    "work_type": "",
                }
            )
        return jobs

    async def _get_dataset(self, run):
        data = await self.client.dataset(run["defaultDatasetId"]).list_items()
        return data.items
