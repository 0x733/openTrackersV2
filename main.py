from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import List
import json
import httpx
from rich.console import Console
from rich.table import Table
import matplotlib.pyplot as plt
from html import unescape

@dataclass
class TrackerData:
    name: str
    date: datetime
    description: str
    categories: List[str]
    url: str
    status: bool = True

class TrackerStatus(Enum):
    OPEN = "🟢 Open"
    CLOSED = "🔴 Closed"

class WordPressAPI:
    def __init__(self, base_url: str):
        self._base_url = base_url
        self._client = self._init_client()

    def _init_client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(
            headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                "Accept": "application/json",
            },
            timeout=30.0,
            follow_redirects=True
        )

    async def fetch_posts(self) -> List[TrackerData]:
        try:
            api_url = f"{self._base_url}/wp-json/wp/v2/posts"
            params = {"tags": "93", "per_page": 100, "_embed": "true"}
            response = await self._client.get(api_url, params=params)
            response.raise_for_status()
            return [self._parse_post(post) for post in response.json()]
        except Exception as e:
            print(f"API Error: {e}")
            return []

    def _parse_post(self, post: dict) -> TrackerData:
        title = unescape(post['title']['rendered'])
        status = "is Open for Limited Signup!" in title
        name = title.replace(' is Open for Limited Signup!', '').strip()
        
        description = unescape(post['excerpt']['rendered'])
        description = description.replace('<p>', '').replace('</p>', '').strip()
        
        categories = [
            term['name']
            for term in post['_embedded']['wp:term'][0]
            if term['taxonomy'] == 'category'
        ]
        
        return TrackerData(
            name=name,
            date=datetime.fromisoformat(post['date'].replace('Z', '+00:00')),
            description=description,
            categories=categories,
            url=post['link'],
            status=status
        )

    async def close(self):
        await self._client.aclose()

class DataManager:
    def __init__(self, storage_path: Path):
        self._storage = storage_path
        self._storage.mkdir(exist_ok=True)

    async def save(self, trackers: List[TrackerData]):
        data = {
            'last_updated': datetime.now().isoformat(),
            'trackers': [self._serialize_tracker(t) for t in trackers]
        }
        current_date = datetime.now().strftime('%Y-%m-%d')
        for file in [self._storage/f'trackers_{current_date}.json', self._storage/'latest.json']:
            with open(file, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=4, ensure_ascii=False)

    def _serialize_tracker(self, tracker: TrackerData) -> dict:
        return {**{k:v for k,v in vars(tracker).items() if k != 'date'}, 'date': tracker.date.isoformat()}

    def create_visualizations(self, trackers: List[TrackerData]):
        if not trackers:
            print("No data to visualize")
            return
        
        category_stats = {}
        for tracker in trackers:
            for category in tracker.categories:
                category_stats[category] = category_stats.get(category, 0) + 1

        plt.figure(figsize=(12,6))
        plt.bar(category_stats.keys(), category_stats.values())
        plt.xticks(rotation=45, ha='right')
        plt.title('Category Distribution')
        plt.tight_layout()
        plt.savefig(self._storage/'category_distribution.png', dpi=300, bbox_inches='tight')
        plt.close()

        plt.figure(figsize=(10,10))
        plt.pie(category_stats.values(), labels=category_stats.keys(), autopct='%1.1f%%')
        plt.title('Category Percentage')
        plt.savefig(self._storage/'category_percentage.png', dpi=300, bbox_inches='tight')
        plt.close()

class TrackerMonitor:
    def __init__(self):
        self._api = WordPressAPI("https://opentrackers.org")
        self._data_dir = Path("data")
        self._console = Console()
        self._data_manager = DataManager(self._data_dir)

    async def run(self):
        try:
            trackers = await self._api.fetch_posts()
            if not trackers:
                self._console.print("[yellow]No trackers found[/yellow]")
                return

            await self._data_manager.save(trackers)
            self._data_manager.create_visualizations(trackers)
            self._display_results(trackers)
            await self._create_markdown_report(trackers)
            
        except Exception as e:
            print(f"Error in main run: {e}")
        finally:
            await self._api.close()

    def _display_results(self, trackers: List[TrackerData]):
        table = Table(show_header=True, header_style="bold magenta")
        table.add_column("Tracker", style="cyan")
        table.add_column("Categories", style="green")
        table.add_column("Date", style="yellow")
        table.add_column("Status", style="bold")
        
        for tracker in sorted(trackers, key=lambda x: x.date, reverse=True):
            table.add_row(
                tracker.name,
                ', '.join(tracker.categories),
                tracker.date.strftime('%Y-%m-%d'),
                TrackerStatus.OPEN.value if tracker.status else TrackerStatus.CLOSED.value
            )
            
        self._console.print(table)

    async def _create_markdown_report(self, trackers: List[TrackerData]):
        category_stats = {}
        for tracker in trackers:
            for category in tracker.categories:
                category_stats[category] = category_stats.get(category, 0) + 1

        markdown = f"""# Tracker Status Report
> Last Updated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

## Statistics
- Total Active Trackers: {len(trackers)}
- Total Categories: {len(category_stats)}

## Category Distribution
![Distribution](./category_distribution.png)
![Percentage](./category_percentage.png)

## Active Trackers
| Tracker | Categories | Open Date | Status |
|---------|------------|-----------|--------|\n"""

        for tracker in sorted(trackers, key=lambda x: x.date, reverse=True):
            markdown += f"| {tracker.name} | {', '.join(tracker.categories)} | {tracker.date.strftime('%Y-%m-%d')} | {TrackerStatus.OPEN.value if tracker.status else TrackerStatus.CLOSED.value} |\n"

        with open(self._data_dir/'README.md', 'w', encoding='utf-8') as f:
            f.write(markdown)

if __name__ == "__main__":
    import asyncio
    asyncio.run(TrackerMonitor().run())