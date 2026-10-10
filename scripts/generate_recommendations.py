"""
scripts/generate_recommendations.py — NHL (hockey-predictions)

Generates data_files/recommendations.json by:
  1. Fetching upcoming NHL games (next few days) with ESPN DraftKings odds
  2. Loading current-season team stats and analytics
  3. Running the xG / win-probability model
  4. Shrinking the model toward the market's vig-free probability
  5. Writing picks with positive edge

Every game the model evaluates is also appended to data_files/pick_log/ so the
predictions can be scored against real results later.

Reads by: scripts/export_best_bets.py (which then writes best_bets_today.json)
"""
import json
import sys
from pathlib import Path

# Add repo root to path
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.api.nhl_client import NHLClient
from src.models.expected_goals import (
    TeamMetrics,
    calculate_expected_goals,
    calculate_expected_goals_with_analytics,
)
from src.models.blend_projection import blend_projection
from src.models.win_probability import calculate_win_probability
from src.utils.pick_log import append_pick_log, source_version
from src.utils.season import current_season_id, to_eastern

OUT_PATH = ROOT / "data_files" / "recommendations.json"
LOG_DIR = ROOT / "data_files" / "pick_log"
MIN_EDGE = 0.03           # only include picks with ≥3 % edge
LOOKAHEAD_DAYS = 7
MIN_GAMES_PLAYED = 20     # the model was only evaluated once both teams had played this many
SHRINK_KEEP = 0.5         # share of the model's disagreement with the market that is kept
EARLY_MIN_EDGE = 0.05     # stricter edge while a team has fewer than MIN_GAMES_PLAYED games
EARLY_MIN_GAMES = 1       # games a team needs this season before the blended projection is used
PRIOR_ONLY_K = 1e12       # blend weight so small that the projection is last season only
MODEL_VERSION = source_version((
    ROOT / "src" / "models" / "expected_goals.py",
    ROOT / "src" / "models" / "win_probability.py",
    Path(__file__).resolve(),
))


def _american_to_prob(odds: int | float | str | None) -> float | None:
    """American moneyline → implied probability (no vig removal)."""
    if odds is None:
        return None
    try:
        odds = float(odds)
    except (TypeError, ValueError):
        return None
    if odds > 0:
        return 100.0 / (odds + 100.0)
    else:
        return abs(odds) / (abs(odds) + 100.0)


def _tier(edge: float) -> str:
    if edge >= 0.08:
        return "Elite"
    elif edge >= 0.03:
        return "Strong"
    elif edge >= 0.01:
        return "Good"
    return "Standard"


def fair_home_probability(home_implied: float | None, away_implied: float | None) -> float | None:
    """Remove the vig from a two-way moneyline to get the market's home win probability."""
    if home_implied is None or away_implied is None:
        return None
    total = home_implied + away_implied
    if total <= 0:
        return None
    return home_implied / total


def shrink_toward_market(model_prob: float, fair_prob: float | None, keep: float = SHRINK_KEEP) -> float:
    """Keep only part of the model's disagreement with the market."""
    if fair_prob is None:
        return model_prob
    return fair_prob + keep * (model_prob - fair_prob)


def _has_enough_games(stats: dict, abbrev: str) -> bool:
    """True when the stats row really belongs to this team and it has played enough games."""
    if not stats:
        return False
    if stats.get("team") != abbrev:
        return False
    return (stats.get("games_played") or 0) >= MIN_GAMES_PLAYED


def _is_scheduled(game: dict) -> bool:
    return str(game.get("status", "")).strip().lower() == "scheduled"


def _has_early_games(stats: dict, abbrev: str) -> bool:
    """True when the stats row belongs to this team and it has played at least one game."""
    if not stats or stats.get("team") != abbrev:
        return False
    return (stats.get("games_played") or 0) >= EARLY_MIN_GAMES


def _prior_reference(fields: dict) -> dict:
    """Last-season-only projection fields, for comparing against the blend."""
    return {
        "home_xg_prior":           fields["home_xg_blend"],
        "away_xg_prior":           fields["away_xg_blend"],
        "home_win_prob_prior_raw": fields["home_win_prob_blend_raw"],
    }


def _prior_stats(client, abbrev: str, season: str, cache: dict) -> dict:
    """Last season's team summary, fetched once per team per run."""
    if abbrev not in cache:
        try:
            cache[abbrev] = client.get_team_summary(abbrev, season=season) or {}
        except Exception:
            cache[abbrev] = {}
    return cache[abbrev]


def main() -> None:
    client = NHLClient(cache_ttl_minutes=60)
    season_id = current_season_id()

    # ── 1. Fetch upcoming games with odds ──────────────────────────────────────
    print(f"[generate_recommendations] Season {season_id}. Fetching upcoming games with odds...")
    try:
        odds_games = client.get_espn_odds(days_ahead=LOOKAHEAD_DAYS)
    except Exception as e:
        print(f"[generate_recommendations] ESPN odds fetch failed: {e}")
        odds_games = []

    if not odds_games:
        print("[generate_recommendations] No upcoming games found — writing empty output")
        OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
        OUT_PATH.write_text(json.dumps([], indent=2))
        return

    # ── 2. Load team analytics (best effort) ─────────────────────────────
    print("[generate_recommendations] Loading team analytics...")
    try:
        analytics_data = client.get_team_analytics(season=season_id)
    except Exception as e:
        print(f"[generate_recommendations] Analytics fetch failed: {e} — using legacy model")
        analytics_data = {}

    # ── 3. Build recommendations ────────────────────────────────────────
    recommendations = []
    log_records = []
    prior_cache: dict = {}

    for game in odds_games:
        home_abbr = game.get("home_team")
        away_abbr = game.get("away_team")

        if not home_abbr or not away_abbr:
            continue

        if not _is_scheduled(game):
            continue

        # Dates and times in Eastern, not the runner's UTC
        start_et = to_eastern(game.get("date", ""))
        if start_et is not None:
            game_date = start_et.date().isoformat()
            game_time = start_et.strftime("%-I:%M %p ET")
        else:
            game_date = (game.get("date") or "")[:10]
            game_time = ""
        if not game_date:
            continue

        # Parse DraftKings odds (prefer DK, fall back to first provider)
        dk_odds = None
        for provider in game.get("odds", []):
            if provider.get("provider") in ("DraftKings", "DraftKings Sportsbook"):
                dk_odds = provider
                break
        if dk_odds is None and game.get("odds"):
            dk_odds = game["odds"][0]

        home_ml = dk_odds.get("moneyline", {}).get("home") if dk_odds else None
        away_ml = dk_odds.get("moneyline", {}).get("away") if dk_odds else None

        home_implied = _american_to_prob(home_ml)
        away_implied = _american_to_prob(away_ml)

        # ── 4. Team stats for xG model ────────────────────────────
        try:
            home_stats = client.get_team_summary(home_abbr, season=season_id) or {}
            away_stats = client.get_team_summary(away_abbr, season=season_id) or {}
        except Exception:
            home_stats = away_stats = {}

        current_gp = (home_stats.get("games_played"), away_stats.get("games_played"))
        current_stats = (home_stats, away_stats)
        prior_only = not (
            _has_enough_games(home_stats, home_abbr) and _has_enough_games(away_stats, away_abbr)
        )
        last_season_id = f"{int(season_id[:4]) - 1}{season_id[:4]}"
        prior_home = _prior_stats(client, home_abbr, last_season_id, prior_cache)
        prior_away = _prior_stats(client, away_abbr, last_season_id, prior_cache)
        blend_fields = blend_projection(
            home_abbr, away_abbr, current_stats[0], current_stats[1], prior_home, prior_away,
        )
        prior_reference = _prior_reference(blend_projection(
            home_abbr, away_abbr, current_stats[0], current_stats[1], prior_home, prior_away,
            k_goals=PRIOR_ONLY_K,
        ))
        # Under 20 games: once both teams have played, project from last season blended with
        # this season (weighted by games played) instead of last season alone.
        early_blend = None
        if (
            prior_only
            and blend_fields["home_xg_blend"] is not None
            and _has_early_games(home_stats, home_abbr)
            and _has_early_games(away_stats, away_abbr)
        ):
            early_blend = blend_fields
            prior_only = False
        if prior_only:
            # Too few games this season: evaluate and log on last season's ratings,
            # but never turn the result into a recommendation.
            prior_id = f"{int(season_id[:4]) - 1}{season_id[:4]}"
            try:
                home_stats = client.get_team_summary(home_abbr, season=prior_id) or {}
                away_stats = client.get_team_summary(away_abbr, season=prior_id) or {}
            except Exception:
                home_stats = away_stats = {}
            if not home_stats or not away_stats:
                print(
                    f"[generate_recommendations] No {season_id} or {prior_id} data for "
                    f"{away_abbr} @ {home_abbr} — skipping"
                )
                continue

        try:
            home_tm = TeamMetrics.from_api_response(home_stats)
            away_tm = TeamMetrics.from_api_response(away_stats)
        except Exception as e:
            print(f"[generate_recommendations] TeamMetrics error for {away_abbr} @ {home_abbr}: {e}")
            continue

        home_analytics = None if (prior_only or early_blend is not None) else analytics_data.get(home_abbr)
        away_analytics = None if (prior_only or early_blend is not None) else analytics_data.get(away_abbr)

        if home_analytics and away_analytics:
            try:
                home_xg, away_xg = calculate_expected_goals_with_analytics(
                    home_tm, away_tm,
                    home_analytics=home_analytics,
                    away_analytics=away_analytics,
                    analytics_weight=0.5,
                )
                model_source = "Analytics blend"
            except Exception:
                home_xg, away_xg = calculate_expected_goals(home_tm, away_tm)
                model_source = "Legacy"
        else:
            home_xg, away_xg = calculate_expected_goals(home_tm, away_tm)
            model_source = "Legacy"

        if early_blend is not None:
            home_xg, away_xg = early_blend["home_xg_blend"], early_blend["away_xg_blend"]
            model_source = "Early blend (last season + this season)"

        try:
            probs = calculate_win_probability(home_xg, away_xg)
        except Exception as e:
            print(f"[generate_recommendations] Win prob error for {away_abbr} @ {home_abbr}: {e}")
            continue

        raw_home_prob = probs.home_win
        raw_away_prob = probs.away_win

        # Shrink toward the market until the model has proven itself against odds
        fair_home = fair_home_probability(home_implied, away_implied)
        home_win_prob = shrink_toward_market(raw_home_prob, fair_home)
        away_win_prob = 1.0 - home_win_prob if fair_home is not None else raw_away_prob

        matchup = f"{away_abbr} @ {home_abbr}"
        if prior_only:
            model_source = f"Prior season ({prior_id})"
        min_edge = EARLY_MIN_EDGE if early_blend is not None else MIN_EDGE

        log_records.append({
            "espn_game_id":       game.get("game_id"),
            "game_date":          game_date,
            "game_time":          game_time,
            "start_utc":          game.get("date"),
            "home_team":          home_abbr,
            "away_team":          away_abbr,
            "season_id":          season_id,
            "model_source":       model_source,
            "model_version":      MODEL_VERSION,
            "prior_only":         prior_only,
            "home_games_played":  current_gp[0],
            "away_games_played":  current_gp[1],
            "home_xg":            home_xg,
            "away_xg":            away_xg,
            "home_win_prob_raw":  round(raw_home_prob, 4),
            "away_win_prob_raw":  round(raw_away_prob, 4),
            "home_win_prob_used": round(home_win_prob, 4),
            "fair_home_prob":     None if fair_home is None else round(fair_home, 4),
            "home_ml":            home_ml,
            "away_ml":            away_ml,
            **blend_fields,
            **prior_reference,
        })

        # ── 5. Edge calculation ──────────────────────────────────────
        if home_implied is not None and not prior_only:
            home_edge = home_win_prob - home_implied
            if home_edge >= min_edge:
                recommendations.append({
                    "date":           game_date,
                    "game_time":      game_time,
                    "matchup":        matchup,
                    "home_team":      home_abbr,
                    "away_team":      away_abbr,
                    "bet_type":       "ML",
                    "recommendation": home_abbr,
                    "model_prob":     round(home_win_prob, 4),
                    "model_prob_raw": round(raw_home_prob, 4),
                    "edge":           round(home_edge, 4),
                    "odds":           home_ml,
                    "notes":          model_source,
                })

        if away_implied is not None and not prior_only:
            away_edge = away_win_prob - away_implied
            if away_edge >= min_edge:
                recommendations.append({
                    "date":           game_date,
                    "game_time":      game_time,
                    "matchup":        matchup,
                    "home_team":      home_abbr,
                    "away_team":      away_abbr,
                    "bet_type":       "ML",
                    "recommendation": away_abbr,
                    "model_prob":     round(away_win_prob, 4),
                    "model_prob_raw": round(raw_away_prob, 4),
                    "edge":           round(away_edge, 4),
                    "odds":           away_ml,
                    "notes":          model_source,
                })

    # ── 6. Write output ────────────────────────────────────────────
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text(json.dumps(recommendations, indent=2, ensure_ascii=False))
    log_path = append_pick_log(log_records, LOG_DIR)
    print(f"[generate_recommendations] Wrote {len(recommendations)} recommendations → {OUT_PATH}")
    if log_path:
        print(f"[generate_recommendations] Logged {len(log_records)} evaluated games → {log_path}")


if __name__ == "__main__":
    main()
