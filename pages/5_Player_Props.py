"""Player prop betting analysis."""
import streamlit as st
import pandas as pd
from pathlib import Path
import sys


# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))
from src.api.nhl_client import NHLClient
from src.utils.shooting_regression import ALPHA, MIN_SHOTS, PRIOR_SHOTS, regression_candidates
from footer import add_betting_oracle_footer


st.title("🎯 Player Props Analysis")


# Initialize client
@st.cache_resource
def get_client():
    return NHLClient()


client = get_client()

LEAGUE_POOL = -1  # -1 asks the API for every skater
SORT_KEYS = {"Points": "points", "Goals": "goals", "Assists": "assists", "Shots": "shots"}


# One cached fetch per (sort, limit) so the table, search and regression tab share data
@st.cache_data(ttl=300, show_spinner=False)
def load_skaters(sort: str, limit: int) -> list:
    return get_client().get_skater_stats(limit=limit, sort=sort)


@st.cache_data(ttl=300, show_spinner=False)
def load_goalies(sort: str, limit: int) -> list:
    return get_client().get_goalie_stats(limit=limit, sort=sort)


@st.cache_data(ttl=300, show_spinner=False)
def load_skater_analytics(limit: int) -> list:
    return get_client().get_skater_analytics(limit=limit)


# Prop type selector
prop_type = st.selectbox("Stat Type", ["Points", "Goals", "Assists", "Shots", "Saves (Goalies)"])


# Get player stats based on type
st.subheader(f"Top Players by {prop_type}")


try:
    if prop_type == "Saves (Goalies)":
        # Ranked by saves, the stat this prop is about
        players = load_goalies("saves", 20)

        if players:
            player_df = pd.DataFrame([
                {
                    "Rank": idx + 1,
                    "Player": p["name"],
                    "Team": client.TEAM_NAMES.get(p["team"], p["team"]),
                    "GP": p["games_played"],
                    "Wins": p["wins"],
                    "Losses": p["losses"],
                    "OTL": p["ot_losses"],
                    "Save %": f"{p['save_pct']:.3f}",
                    "GAA": f"{p['gaa']:.2f}",
                    "Shutouts": p["shutouts"],
                    "Saves": p["saves"]
                }
                for idx, p in enumerate(players)
            ])

            st.dataframe(
                player_df,
                width='stretch',
                hide_index=True,
                column_config={
                    "Rank": st.column_config.NumberColumn("Rank", width="small"),
                    "Player": st.column_config.TextColumn("Player", width="medium"),
                    "Team": st.column_config.TextColumn("Team", width="medium"),
                    "GP": st.column_config.NumberColumn("Games Played", width="small"),
                    "Wins": st.column_config.NumberColumn("Wins", width="small"),
                    "Losses": st.column_config.NumberColumn("Losses", width="small"),
                    "OTL": st.column_config.NumberColumn("OT Losses", width="small"),
                    "Save %": st.column_config.TextColumn("Save %", width="small"),
                    "GAA": st.column_config.TextColumn("Goals Against Avg", width="small"),
                    "Shutouts": st.column_config.NumberColumn("Shutouts", width="small"),
                    "Saves": st.column_config.NumberColumn("Saves", width="small"),
                }
            )
        else:
            st.info("No goalie stats available.")
    else:
        # The API ranks by the chosen stat, so this is the true top 50 for it
        players = load_skaters(SORT_KEYS[prop_type], 50)

        if players:
            player_df = pd.DataFrame([
                {
                    "Rank": idx + 1,
                    "Player": p["name"],
                    "Team": client.TEAM_NAMES.get(p["team"], p["team"]),
                    "Position": p.get("position", ""),
                    "GP": p["games"],
                    "Goals": p["goals"],
                    "Assists": p["assists"],
                    "Points": p["points"],
                    "Shots": p["shots"],
                    "S%": f"{p['shooting_pct']:.1f}%" if p.get("shooting_pct") else "0%",
                    "TOI/G": f"{p['toi_pg']:.1f}" if p.get("toi_pg") else "0"
                }
                for idx, p in enumerate(players)
            ])

            st.dataframe(
                player_df,
                width='stretch',
                hide_index=True,
                column_config={
                    "Rank": st.column_config.NumberColumn("Rank", width="small"),
                    "Player": st.column_config.TextColumn("Player", width="medium"),
                    "Team": st.column_config.TextColumn("Team", width="medium"),
                    "Position": st.column_config.TextColumn("Pos", width="small"),
                    "GP": st.column_config.NumberColumn("Games Played", width="small"),
                    "Goals": st.column_config.NumberColumn("Goals", width="small"),
                    "Assists": st.column_config.NumberColumn("Assists", width="small"),
                    "Points": st.column_config.NumberColumn("Points", width="small"),
                    "Shots": st.column_config.NumberColumn("Shots", width="small"),
                    "S%": st.column_config.TextColumn("Shooting %", width="small"),
                    "TOI/G": st.column_config.TextColumn("TOI/Game", width="small"),
                }
            )
        else:
            st.info("No player stats available.")

    # Player search
    st.divider()
    st.subheader("Player Search")
    player_search = st.text_input("Search by name", placeholder="Enter player name...")

    if player_search:
        # Search the whole league, not just the top scorers
        if prop_type == "Saves (Goalies)":
            players = load_goalies("saves", 100)
        else:
            players = load_skaters("points", LEAGUE_POOL)

        matching = [p for p in players if player_search.lower() in (p["name"] or "").lower()]

        if matching:
            st.success(f"Found {len(matching)} matching player(s)")

            for p in matching[:5]:  # Show first 5 matches
                team_name = client.TEAM_NAMES.get(p['team'], p['team'])
                with st.expander(f"{p['name']} ({team_name})"):
                    if prop_type == "Saves (Goalies)":
                        st.write(f"**Games Played:** {p['games_played']}")
                        st.write(f"**Record:** {p['wins']}-{p['losses']}-{p['ot_losses']}")
                        st.write(f"**Save %:** {p['save_pct']:.3f}")
                        st.write(f"**GAA:** {p['gaa']:.2f}")
                        st.write(f"**Shutouts:** {p['shutouts']}")
                        st.write(f"**Saves:** {p['saves']}")
                    else:
                        st.write(f"**Position:** {p.get('position', 'N/A')}")
                        st.write(f"**Games:** {p['games']}")
                        st.write(f"**Goals:** {p['goals']}")
                        st.write(f"**Assists:** {p['assists']}")
                        st.write(f"**Points:** {p['points']}")
                        st.write(f"**Shots:** {p['shots']}")
                        st.write(f"**+/-:** {p.get('plus_minus', 0)}")
        else:
            st.warning("No players found matching that name.")

except Exception as e:
    st.error(f"Error loading player stats: {e}")


# ── Per-60 Analytics ─────────────────────────────────────────────────────────
st.divider()
st.subheader("⚡ Per-60 Rates & Shooting Luck Watch")
st.caption(
    "Per-60 rates normalise production for players with different ice time. "
    "Shooting luck compares each player's goals with what a typical player of the same type "
    "would score on the same shots."
)


per60_tab, regression_tab = st.tabs(["Per-60 Rates", "Shooting Luck Watch"])


with per60_tab:
    try:
        skater_analytics = load_skater_analytics(100)
        st.caption("Ranked among the league's top 100 point-scorers, not every skater.")

        if skater_analytics:
            per60_records = [
                {
                    "Player": p["name"],
                    "Team": client.TEAM_NAMES.get(p.get("team", ""), p.get("team", "")),
                    "Pos": p.get("position", ""),
                    "GP": p.get("games", 0),
                    "G/60": round(p.get("g_per_60", 0), 2),
                    "A/60": round(p.get("a_per_60", 0), 2),
                    "P/60": round(p.get("p_per_60", 0), 2),
                    "TOI/G": round(p.get("toi_pg", 0), 1) if p.get("toi_pg") else None,
                }
                for p in skater_analytics
                if p.get("p_per_60") is not None
            ]

            if not per60_records:
                st.info("Per-60 data not available for the current season.")
            else:
                per60_df = pd.DataFrame(per60_records)
                per60_df = per60_df.sort_values("P/60", ascending=False).reset_index(drop=True)
                per60_df.insert(0, "Rank", range(1, len(per60_df) + 1))

                st.dataframe(
                    per60_df,
                    hide_index=True,
                    width="stretch",
                    column_config={
                        "Rank": st.column_config.NumberColumn("Rank", width="small"),
                        "Player": st.column_config.TextColumn("Player", width="medium"),
                        "Team": st.column_config.TextColumn("Team", width="small"),
                        "Pos": st.column_config.TextColumn("Pos", width="small"),
                        "GP": st.column_config.NumberColumn("GP", width="small"),
                        "G/60": st.column_config.NumberColumn(
                            "G/60", width="small", format="%.2f",
                            help="Goals per 60 minutes of ice time",
                        ),
                        "A/60": st.column_config.NumberColumn(
                            "A/60", width="small", format="%.2f",
                            help="Assists per 60 minutes of ice time",
                        ),
                        "P/60": st.column_config.NumberColumn(
                            "P/60", width="small", format="%.2f",
                            help="Points per 60 minutes — best measure of scorer quality",
                        ),
                        "TOI/G": st.column_config.NumberColumn("TOI/G", width="small"),
                    },
                )
                with st.expander("Why per-60?"):
                    st.markdown(
                        "Raw totals reward players who log heavy ice time. Per-60 rates "
                        "show **efficiency** — how much a player produces per minute of "
                        "opportunity. A 4th-liner scoring at 1.5 P/60 may be more efficient "
                        "than a 1st-liner at 1.2 P/60 who gets 20+ minutes."
                    )
        else:
            st.info("Per-60 data not available for the current season.")
    except Exception as exc:
        st.warning(f"Could not load per-60 data: {exc}")


with regression_tab:
    st.markdown(
        "Lists players whose goals are **unlikely to be luck alone**, judged against the "
        "league's goals-per-shot for their position group (forwards and defensemen are "
        "compared separately). A hot or cold streak is not a forecast: shooting skill is real, "
        "so the **Projected S%** column pulls each player's rate back toward the position "
        "average only as far as their shot count justifies."
    )

    try:
        skaters = load_skaters("points", LEAGUE_POOL)

        if skaters:
            result = regression_candidates(skaters)
            baselines = result["baselines"]
            regression_rows = [
                {
                    "Player": r["name"],
                    "Team": client.TEAM_NAMES.get(r["team"] or "", r["team"]),
                    "Pos": r["position"],
                    "GP": r["games"],
                    "Goals": r["goals"],
                    "Shots": r["shots"],
                    "S%": f"{r['shooting_pct'] * 100:.1f}%",
                    "Pos Avg S%": f"{r['baseline_pct'] * 100:.1f}%",
                    "Expected Goals": round(r["expected_goals"], 1),
                    "Goals vs Exp": round(r["goals"] - r["expected_goals"], 1),
                    "Luck Odds": f"{r['p_value']:.2%}",
                    "Projected S%": f"{r['shrunk_pct'] * 100:.1f}%",
                    "Signal": "🔴 Running hot" if r["signal"] == "hot" else "🔵 Running cold",
                }
                for r in result["rows"]
            ]

            if regression_rows:
                st.dataframe(pd.DataFrame(regression_rows), hide_index=True, width="stretch")
                st.caption(
                    "Luck Odds is the chance a typical player of that position would do this "
                    "well (or this badly) on the same shots."
                )
            else:
                st.success(
                    "No player stands out beyond luck yet. That is normal early in the season, "
                    "when shot counts are small."
                )
            st.caption(
                f"Position averages from {len(skaters)} skaters: "
                + ", ".join(
                    f"{'Forwards' if g == 'F' else 'Defensemen'} {v * 100:.1f}%"
                    for g, v in sorted(baselines.items())
                )
            )
        else:
            st.info("No skater data available for this analysis.")
    except Exception as exc:
        st.warning(f"Could not load shooting luck data: {exc}")

    with st.expander("How the luck watch works"):
        st.markdown(f"""
        **Method:**
        - Each player's expected goals are their shots times the league's goals-per-shot for
          their position group, measured from all skaters on this page's data.
        - A player is listed only if the chance of a result this extreme is at most
          **{ALPHA:.0%}** (exact binomial test) and they have at least **{MIN_SHOTS}** shots.
        - **Projected S%** blends the player's own rate with the position average, treating the
          average as worth **{PRIOR_SHOTS}** shots of evidence. That weight is an assumption,
          not a measured constant.

        **How to use it:** a flagged player is more likely than not to score less (or more) than
        his rate so far, but not all the way back to average, since finishing skill exists. With
        hundreds of skaters checked, a few will be flagged by chance alone. Treat it as a
        reason to look closer at a goals prop, not as a bet signal by itself.
        """)


# Add footer
add_betting_oracle_footer()
