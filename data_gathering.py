"""Data Gathering - Collect Historical NHL Data from 2020 to Present.

This script fetches all necessary NHL data for modeling:
- Game schedules and results (2020-today)
- Team statistics by season
- Player statistics (skaters and goalies)
- Standings data
- Game-level details for prediction features

Rate limited to avoid overloading the API.
"""
import json
import time
from pathlib import Path
from datetime import datetime, date, timedelta
from typing import List, Dict, Optional
import httpx

# Data storage directory
DATA_DIR = Path("data_files/historical")
CACHE_DIR = Path("data_files/cache")

# NHL API endpoints
BASE_WEB_API = "https://api-web.nhle.com/v1"
BASE_STATS_API = "https://api.nhle.com/stats/rest/en"

# Rate limiting
REQUEST_DELAY = 0.5  # 500ms between requests (2 req/sec)
BATCH_DELAY = 5.0    # 5s between batches

# NHL seasons (season ID format: YYYYYYYY for 2020-21 = 20202021)
SEASONS = {
    "2019-20": "20192020",  # Shortened COVID season
    "2020-21": "20202021",  # COVID season (56 games)
    "2021-22": "20212022",  # Return to 82 games
    "2022-23": "20222023",
    "2023-24": "20232024",
    "2024-25": "20242025",
    "2025-26": "20252026",  # Current season
}

# Game states that mean the result is final (FINAL = just ended, OFF = official)
FINAL_STATES = {"FINAL", "OFF"}


class DataGatherer:
    """Gather historical NHL data for modeling."""
    
    def __init__(self):
        """Initialize data gatherer."""
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        self.session = httpx.Client(timeout=30.0, follow_redirects=True)
        self.request_count = 0
    
    def __del__(self):
        """Clean up HTTP session."""
        if hasattr(self, 'session'):
            self.session.close()
    
    def _fetch(self, url: str, cache_key: Optional[str] = None, refresh: bool = False) -> Dict:
        """
        Fetch data with rate limiting and optional caching.
        
        Args:
            url: Full URL to fetch
            cache_key: Optional cache filename (without extension)
            refresh: If True, skip reading the cache but still write the new response
        
        Returns:
            JSON response as dictionary
        """
        # Check cache first
        if cache_key and not refresh:
            cache_file = CACHE_DIR / f"{cache_key}.json"
            if cache_file.exists():
                print(f"  📦 Using cached: {cache_key}")
                return json.loads(cache_file.read_text())
        
        # Rate limiting
        time.sleep(REQUEST_DELAY)
        
        try:
            print(f"  🌐 Fetching: {url}")
            response = self.session.get(url)
            response.raise_for_status()
            data = response.json()
            
            # Cache if requested
            if cache_key:
                cache_file = CACHE_DIR / f"{cache_key}.json"
                cache_file.write_text(json.dumps(data, indent=2))
            
            self.request_count += 1
            
            # Batch delay every 10 requests
            if self.request_count % 10 == 0:
                print(f"  ⏸️  Batch delay ({self.request_count} requests)...")
                time.sleep(BATCH_DELAY)
            
            return data
            
        except httpx.HTTPStatusError as e:
            print(f"  ❌ HTTP {e.response.status_code}: {url}")
            return {}
        except Exception as e:
            print(f"  ❌ Error: {e}")
            return {}
    
    # =========================================================================
    # Season-Level Data
    # =========================================================================
    
    def gather_season_data(self, season_name: str, season_id: str) -> None:
        """
        Gather all data for a specific season.
        
        Args:
            season_name: Display name (e.g., "2023-24")
            season_id: API season ID (e.g., "20232024")
        """
        print(f"\n{'='*60}")
        print(f"📅 Gathering data for {season_name} season")
        print(f"{'='*60}")
        
        season_dir = DATA_DIR / season_name
        season_dir.mkdir(parents=True, exist_ok=True)
        
        # 1. Team statistics
        self._gather_team_stats(season_id, season_dir)
        
        # 2. Skater statistics
        self._gather_skater_stats(season_id, season_dir)
        
        # 3. Goalie statistics
        self._gather_goalie_stats(season_id, season_dir)
        
        # 4. Game schedules and results
        self._gather_season_games(season_name, season_id, season_dir)
        
        print(f"\n✅ Completed {season_name} season data")
    
    def _gather_team_stats(self, season_id: str, season_dir: Path) -> None:
        """Gather team statistics for season."""
        print("\n📊 Fetching team statistics...")
        
        url = f"{BASE_STATS_API}/team/summary?cayenneExp=seasonId={season_id}"
        data = self._fetch(url, cache_key=f"team_stats_{season_id}")
        
        if data and "data" in data:
            output_file = season_dir / "team_stats.json"
            output_file.write_text(json.dumps(data["data"], indent=2))
            print(f"  ✅ Saved {len(data['data'])} teams")
    
    def _gather_skater_stats(self, season_id: str, season_dir: Path) -> None:
        """Gather skater statistics for season."""
        print("\n🏒 Fetching skater statistics...")
        
        # Get top 500 skaters by points
        url = (
            f"{BASE_STATS_API}/skater/summary"
            f"?limit=500&cayenneExp=seasonId={season_id}"
            f"&sort=points&direction=DESC"
        )
        data = self._fetch(url, cache_key=f"skater_stats_{season_id}")
        
        if data and "data" in data:
            output_file = season_dir / "skater_stats.json"
            output_file.write_text(json.dumps(data["data"], indent=2))
            print(f"  ✅ Saved {len(data['data'])} skaters")
    
    def _gather_goalie_stats(self, season_id: str, season_dir: Path) -> None:
        """Gather goalie statistics for season."""
        print("\n🥅 Fetching goalie statistics...")
        
        # Get top 100 goalies by games played
        url = (
            f"{BASE_STATS_API}/goalie/summary"
            f"?limit=100&cayenneExp=seasonId={season_id}"
            f"&sort=gamesPlayed&direction=DESC"
        )
        data = self._fetch(url, cache_key=f"goalie_stats_{season_id}")
        
        if data and "data" in data:
            output_file = season_dir / "goalie_stats.json"
            output_file.write_text(json.dumps(data["data"], indent=2))
            print(f"  ✅ Saved {len(data['data'])} goalies")
    
    def _gather_season_games(
        self, 
        season_name: str, 
        season_id: str, 
        season_dir: Path
    ) -> None:
        """
        Gather all games for a season by walking the weekly schedule windows.
        
        Args:
            season_name: Display name (e.g., "2023-24")
            season_id: API season ID
            season_dir: Directory to save data
        """
        print("\n🗓️  Fetching game schedules...")
        
        # Determine season date range
        start_date, end_date = self._get_season_dates(season_name)
        
        games_file = season_dir / "games.json"
        
        # Load existing games if resuming. Older files hold one row per weekly
        # schedule window a game appeared in, so collapse them to one per game_id.
        games_by_id: Dict[int, Dict] = {}
        if games_file.exists():
            existing_games = json.loads(games_file.read_text())
            for existing in existing_games:
                self._upsert_game(games_by_id, existing)
            print(f"  📂 Found {len(existing_games)} existing rows ({len(games_by_id)} unique games)")
        
        current_date = start_date
        windows_processed = 0
        
        # Each schedule request returns a week of games starting at the requested
        # date, so follow the API's nextStartDate instead of asking day by day.
        while current_date <= end_date:
            date_str = current_date.strftime("%Y-%m-%d")
            
            url = f"{BASE_WEB_API}/schedule/{date_str}"
            cache_key = f"schedule_{date_str}"
            schedule = self._fetch(url, cache_key=cache_key)
            
            # A cached week saved before its games finished has stale scores
            if schedule and self._has_unfinished_past_games(schedule):
                schedule = self._fetch(url, cache_key=cache_key, refresh=True) or schedule
            
            # Extract games, dated by each game's own schedule day
            if schedule and "gameWeek" in schedule:
                for game_info in self._games_from_schedule(schedule, season_name):
                    self._upsert_game(games_by_id, game_info)
            
            windows_processed += 1
            
            # Save progress every 10 windows
            if windows_processed % 10 == 0:
                self._save_games(games_file, games_by_id)
                print(f"  💾 Progress saved: {len(games_by_id)} games")
            
            current_date = self._next_window_start(schedule, current_date)
        
        # Final save
        self._save_games(games_file, games_by_id)
        print(f"  ✅ Saved {len(games_by_id)} unique games")
    
    @staticmethod
    def _games_from_schedule(schedule: Dict, season_name: str) -> List[Dict]:
        """Convert a schedule response into game rows dated by each game's own day."""
        games = []
        for game_week in schedule.get("gameWeek", []):
            game_day = game_week.get("date")
            if not game_day:
                continue
            for game in game_week.get("games", []):
                # Only regular season games
                if game.get("gameType") != 2:
                    continue
                game_info = {
                    "game_id": game["id"],
                    "date": game_day,
                    "season": season_name,
                    "start_time": game.get("startTimeUTC"),
                    "home_team": game["homeTeam"]["abbrev"],
                    "away_team": game["awayTeam"]["abbrev"],
                    "home_score": game["homeTeam"].get("score"),
                    "away_score": game["awayTeam"].get("score"),
                    "game_state": game.get("gameState"),
                    "venue": game.get("venue", {}).get("default"),
                }
                
                # Add derived fields only once the result is final
                if game_info["home_score"] is not None and game_info["game_state"] in FINAL_STATES:
                    game_info["home_won"] = game_info["home_score"] > game_info["away_score"]
                    game_info["total_goals"] = game_info["home_score"] + game_info["away_score"]
                    game_info["margin"] = game_info["home_score"] - game_info["away_score"]
                    last_period = (game.get("gameOutcome") or {}).get("lastPeriodType")
                    game_info["went_to_ot"] = last_period in ("OT", "SO")
                
                games.append(game_info)
        return games
    
    @staticmethod
    def _upsert_game(games_by_id: Dict[int, Dict], game_info: Dict) -> None:
        """Store one row per game_id; never replace a final result with an unfinished copy."""
        existing = games_by_id.get(game_info["game_id"])
        if (
            existing is not None
            and existing.get("game_state") in FINAL_STATES
            and game_info.get("game_state") not in FINAL_STATES
        ):
            return
        games_by_id[game_info["game_id"]] = game_info
    
    @staticmethod
    def _has_unfinished_past_games(schedule: Dict) -> bool:
        """True if a schedule week has past regular-season games that are not final."""
        today = date.today().isoformat()
        for game_week in schedule.get("gameWeek", []):
            if game_week.get("date", today) >= today:
                continue
            for game in game_week.get("games", []):
                if (
                    game.get("gameType") == 2
                    and game.get("gameScheduleState", "OK") == "OK"
                    and game.get("gameState") not in FINAL_STATES
                ):
                    return True
        return False
    
    @staticmethod
    def _next_window_start(schedule: Dict, current_date: date) -> date:
        """Return the start of the next schedule window, always moving forward."""
        try:
            candidate = date.fromisoformat(schedule.get("nextStartDate", ""))
        except (TypeError, ValueError):
            candidate = current_date + timedelta(days=7)
        if candidate <= current_date:
            candidate = current_date + timedelta(days=7)
        return candidate
    
    @staticmethod
    def _save_games(games_file: Path, games_by_id: Dict[int, Dict]) -> None:
        """Write games sorted by date and game_id."""
        games = sorted(games_by_id.values(), key=lambda g: (g.get("date") or "", g["game_id"]))
        games_file.write_text(json.dumps(games, indent=2))
    
    def _get_season_dates(self, season_name: str) -> tuple[date, date]:
        """
        Get start and end dates for a season.
        
        Args:
            season_name: Season name (e.g., "2023-24")
        
        Returns:
            Tuple of (start_date, end_date)
        """
        year1, year2 = season_name.split("-")
        year1 = int("20" + year1 if len(year1) == 2 else year1)
        year2 = int("20" + year2 if len(year2) == 2 else year2)
        
        # Special handling for COVID seasons
        if season_name == "2019-20":
            # Season cut short in March 2020
            return date(2019, 10, 1), date(2020, 8, 1)
        elif season_name == "2020-21":
            # Started late, 56-game season
            return date(2021, 1, 1), date(2021, 7, 15)
        
        # Normal season: October to June
        start = date(year1, 10, 1)
        end = date(year2, 6, 30)
        
        # Don't go past today
        today = date.today()
        if end > today:
            end = today
        
        return start, end
    
    # =========================================================================
    # Current Season Live Data
    # =========================================================================
    
    def gather_current_standings(self) -> None:
        """Gather current league standings."""
        print("\n📊 Fetching current standings...")
        
        url = f"{BASE_WEB_API}/standings/now"
        data = self._fetch(url, cache_key="standings_current")
        
        if data and "standings" in data:
            output_file = DATA_DIR / "current_standings.json"
            output_file.write_text(json.dumps(data["standings"], indent=2))
            print(f"  ✅ Saved standings for {len(data['standings'])} teams")
    
    # =========================================================================
    # Main Execution
    # =========================================================================
    
    def gather_all(self, seasons: Optional[List[str]] = None) -> None:
        """
        Gather all historical data.
        
        Args:
            seasons: List of season names to gather (default: all)
        """
        if seasons is None:
            seasons = list(SEASONS.keys())
        
        start_time = datetime.now()
        print(f"\n🚀 Starting data gathering at {start_time.strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"📋 Seasons to process: {', '.join(seasons)}")
        
        # Gather season-by-season data
        for season_name in seasons:
            if season_name in SEASONS:
                season_id = SEASONS[season_name]
                self.gather_season_data(season_name, season_id)
            else:
                print(f"⚠️  Unknown season: {season_name}")
        
        # Gather current standings
        self.gather_current_standings()
        
        # Summary
        end_time = datetime.now()
        duration = end_time - start_time
        
        print(f"\n{'='*60}")
        print(f"✅ Data gathering complete!")
        print(f"{'='*60}")
        print(f"⏱️  Duration: {duration}")
        print(f"📡 API Requests: {self.request_count}")
        print(f"📁 Data saved to: {DATA_DIR.absolute()}")
        print(f"\n💡 Next steps:")
        print(f"   1. Review data in {DATA_DIR}")
        print(f"   2. Run data validation/cleaning")
        print(f"   3. Build prediction models")


    # =========================================================================
    # Test Functions
    # =========================================================================
    
    def test_api_connectivity(self) -> bool:
        """
        Test API connectivity and data structure.
        
        Returns:
            True if test passes, False otherwise
        """
        print("\n🧪 Running API Connectivity Test")
        print("="*60)
        
        test_date = "2024-01-15"  # Known date with games
        all_tests_passed = True
        
        # Test 1: Schedule endpoint
        print("\n1️⃣  Testing schedule endpoint...")
        url = f"{BASE_WEB_API}/schedule/{test_date}"
        schedule = self._fetch(url)
        
        if schedule and "gameWeek" in schedule:
            games_found = sum(len(day.get("games", [])) for day in schedule.get("gameWeek", []))
            print(f"   ✅ Schedule API working - found {games_found} games")
            
            # Show sample game
            if games_found > 0:
                sample_game = schedule["gameWeek"][0]["games"][0]
                print(f"   📋 Sample game: {sample_game['awayTeam']['abbrev']} @ {sample_game['homeTeam']['abbrev']}")
        else:
            print(f"   ❌ Schedule API failed")
            all_tests_passed = False
        
        # Test 2: Team stats endpoint
        print("\n2️⃣  Testing team stats endpoint...")
        url = f"{BASE_STATS_API}/team/summary?cayenneExp=seasonId=20232024"
        team_stats = self._fetch(url)
        
        if team_stats and "data" in team_stats:
            teams_found = len(team_stats["data"])
            print(f"   ✅ Team stats API working - found {teams_found} teams")
            
            # Show sample team
            if teams_found > 0:
                sample_team = team_stats["data"][0]
                print(f"   📋 Sample team: {sample_team.get('teamFullName')} - GP: {sample_team.get('gamesPlayed')}")
        else:
            print(f"   ❌ Team stats API failed")
            all_tests_passed = False
        
        # Test 3: Goalie stats endpoint
        print("\n3️⃣  Testing goalie stats endpoint...")
        url = f"{BASE_STATS_API}/goalie/summary?limit=10&cayenneExp=seasonId=20232024&sort=wins&direction=DESC"
        goalie_stats = self._fetch(url)
        
        if goalie_stats and "data" in goalie_stats:
            goalies_found = len(goalie_stats["data"])
            print(f"   ✅ Goalie stats API working - found {goalies_found} goalies")
            
            # Show sample goalie
            if goalies_found > 0:
                sample_goalie = goalie_stats["data"][0]
                print(f"   📋 Sample goalie: {sample_goalie.get('goalieFullName')} - SV%: {sample_goalie.get('savePct', 0):.3f}")
        else:
            print(f"   ❌ Goalie stats API failed")
            all_tests_passed = False
        
        # Test 4: Standings endpoint
        print("\n4️⃣  Testing standings endpoint...")
        url = f"{BASE_WEB_API}/standings/now"
        standings = self._fetch(url)
        
        if standings and "standings" in standings:
            teams_found = len(standings["standings"])
            print(f"   ✅ Standings API working - found {teams_found} teams")
            
            # Show top team
            if teams_found > 0:
                top_team = standings["standings"][0]
                print(f"   📋 Top team: {top_team.get('teamName', {}).get('default')} - {top_team.get('points')} pts")
        else:
            print(f"   ❌ Standings API failed")
            all_tests_passed = False
        
        # Summary
        print("\n" + "="*60)
        if all_tests_passed:
            print("✅ All API tests passed! Ready to gather data.")
            print(f"\n📊 Data structure verified:")
            print(f"   - Schedule: ✅")
            print(f"   - Team stats: ✅")
            print(f"   - Goalie stats: ✅")
            print(f"   - Standings: ✅")
        else:
            print("❌ Some API tests failed. Check network/API status.")
        
        print(f"\n📡 Total requests made: {self.request_count}")
        return all_tests_passed
    
    def test_mini_gather(self) -> bool:
        """
        Test data gathering with a small date range (1 week).
        
        Returns:
            True if successful
        """
        print("\n🧪 Running Mini Data Gather Test")
        print("="*60)
        print("📅 Gathering 1 week of data from Jan 2024...")
        
        test_dir = DATA_DIR / "test_run"
        test_dir.mkdir(parents=True, exist_ok=True)
        
        # Gather games for 1 week (one request returns the whole week)
        print("\n🗓️  Fetching test week of games...")
        games = []
        start = date(2024, 1, 15)
        date_str = start.strftime("%Y-%m-%d")
        
        url = f"{BASE_WEB_API}/schedule/{date_str}"
        schedule = self._fetch(url)
        
        if schedule and "gameWeek" in schedule:
            for game_week in schedule["gameWeek"]:
                for game in game_week.get("games", []):
                    if game.get("gameType") == 2:  # Regular season
                        games.append({
                            "game_id": game["id"],
                            "date": game_week.get("date", date_str),
                            "home": game["homeTeam"]["abbrev"],
                            "away": game["awayTeam"]["abbrev"],
                            "home_score": game["homeTeam"].get("score"),
                            "away_score": game["awayTeam"].get("score"),
                        })
        
        # Save test data
        test_file = test_dir / "test_games.json"
        test_file.write_text(json.dumps(games, indent=2))
        
        print(f"\n✅ Test complete!")
        print(f"📊 Results:")
        print(f"   - Games found: {len(games)}")
        print(f"   - Date range: Jan 15-21, 2024")
        print(f"   - Sample saved to: {test_file}")
        print(f"   - API requests: {self.request_count}")
        
        if games:
            print(f"\n📋 Sample games:")
            for game in games[:3]:
                scores = ""
                if game["home_score"] is not None:
                    scores = f" ({game['away_score']}-{game['home_score']})"
                print(f"   • {game['away']} @ {game['home']}{scores}")
        
        return len(games) > 0


# =============================================================================
# CLI Interface
# =============================================================================

def main():
    """Main entry point for data gathering."""
    import argparse
    
    parser = argparse.ArgumentParser(
        description="Gather historical NHL data for modeling"
    )
    parser.add_argument(
        "--seasons",
        nargs="+",
        help="Specific seasons to gather (e.g., 2023-24 2024-25)",
        default=None
    )
    parser.add_argument(
        "--current-only",
        action="store_true",
        help="Only gather current season data"
    )
    parser.add_argument(
        "--standings-only",
        action="store_true",
        help="Only gather current standings"
    )
    parser.add_argument(
        "--test",
        action="store_true",
        help="Run API connectivity test"
    )
    parser.add_argument(
        "--test-mini",
        action="store_true",
        help="Run mini data gather test (1 week)"
    )
    
    args = parser.parse_args()
    
    gatherer = DataGatherer()
    
    if args.test:
        # Run connectivity test
        success = gatherer.test_api_connectivity()
        if not success:
            print("\n⚠️  Warning: Some tests failed. Check API status before full gather.")
    elif args.test_mini:
        # Run mini gather test
        success = gatherer.test_mini_gather()
        if success:
            print("\n✅ Mini test successful! You can now run the full gather.")
        else:
            print("\n❌ Mini test failed. Check errors above.")
    elif args.standings_only:
        gatherer.gather_current_standings()
    elif args.current_only:
        current_season = "2025-26"
        gatherer.gather_all(seasons=[current_season])
    else:
        gatherer.gather_all(seasons=args.seasons)


if __name__ == "__main__":
    main()
