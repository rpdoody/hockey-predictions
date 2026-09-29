"""Backtesting simulator for model validation."""
import streamlit as st
import pandas as pd
import sys
from pathlib import Path
from datetime import date, timedelta
import random

# Add src to path
src_path = Path(__file__).parent.parent
sys.path.insert(0, str(src_path))

from src.models.backtest import BacktestEngine, BacktestConfig, BetResult
from src.models.features import NHLFeatureEngineer
from src.utils.odds import decimal_to_american
from footer import add_betting_oracle_footer

# Half of a standard two-way vig: -110 on both sides implies 52.38% each.
VIG_PER_SIDE = 0.0238

st.title("🔬 Backtesting Simulator")
st.markdown("Validate staking rules against historical game results.")

# Configuration Section
st.subheader("Backtest Configuration")

col1, col2, col3 = st.columns(3)

with col1:
    start_date = st.date_input("Start Date", value=date(2025, 10, 1), min_value=date(2024, 9, 1), max_value=date.today())
    end_date = st.date_input("End Date", value=date(2026, 1, 31), min_value=date(2024, 9, 1), max_value=date.today())
    initial_bankroll = st.number_input("Initial Bankroll ($)", 100, 10000, 1000, 100)

with col2:
    unit_size = st.number_input("Unit Size ($)", 1, 100, 10, 1)
    min_edge = st.slider("Min Edge Required (%)", 0.0, 10.0, 1.0, 0.5) / 100
    max_kelly = st.slider("Max Kelly Fraction", 0.05, 0.50, 0.25, 0.05)

with col3:
    bet_types = st.multiselect(
        "Bet Types",
        ["moneyline"],
        default=["moneyline"]
    )
    st.caption("Puck line and totals need stored market lines and are not simulated yet.")
    seed = st.number_input("Random Seed", 0, 1000000, 42, 1)

# Simulation Section
st.markdown("---")
st.subheader("Run Simulation")

st.warning("""
⚠️ **Simulation only - this is not a test of your trained model.**
- Model and market probabilities are random draws (seeded, so reruns match).
- Only the game results are real (deduplicated 2025-26 games).
- Market odds include a two-way vig of about -110 on each side.
- Results show how the staking rules behave, not whether the model has an edge.
""")

if st.button("🚀 Run Backtest", type="primary"):
    games_file = Path("data_files/historical/2025-26/games.json")
    if not games_file.exists():
        st.error("Historical game data not found. Please ensure data_files/historical/2025-26/games.json exists.")
        st.stop()

    # The collector stores each game once per weekly schedule window it appeared
    # in, so load through the shared loader, which keeps one row per game_id.
    games_df = NHLFeatureEngineer().load_historical_games(["2025-26"])

    # Filter to completed games in our date range
    in_range = (
        (games_df["game_state"] == "OFF")
        & (games_df["date"] >= pd.Timestamp(start_date))
        & (games_df["date"] <= pd.Timestamp(end_date))
    )
    completed_games = games_df[in_range].to_dict("records")

    if not completed_games:
        st.warning(f"No completed games found between {start_date} and {end_date}")
        st.stop()

    st.caption(f"{len(completed_games)} unique completed games in range.")

    # Create backtest config
    config = BacktestConfig(
        start_date=start_date.isoformat(),
        end_date=end_date.isoformat(),
        initial_bankroll=initial_bankroll,
        unit_size=unit_size,
        min_edge=min_edge,
        max_kelly_fraction=max_kelly,
        bet_types=bet_types
    )

    # Initialize engine
    engine = BacktestEngine(config)
    rng = random.Random(int(seed))

    # Run backtest on real historical results
    with st.spinner(f"Running backtest on {len(completed_games)} historical games..."):
        for game in completed_games:
            game_date = game["date"].strftime("%Y-%m-%d")
            game_id = str(game["game_id"])

            # Base market probability (what odds imply)
            market_home_prob = 0.52  # Slight home advantage in NHL

            # Simulated model probability: a random draw with a small assumed edge
            model_skill = rng.gauss(0.03, 0.08)
            model_prob = max(0.35, min(0.75, market_home_prob + model_skill))

            # Simulated market: fair probability plus noise, then add the vig
            market_noise = rng.gauss(0, 0.03)
            market_prob_for_odds = max(0.35, min(0.75, market_home_prob + market_noise))
            offered_prob = min(0.95, market_prob_for_odds + VIG_PER_SIDE)

            # Convert to American odds and keep them in a realistic range
            odds = decimal_to_american(1 / offered_prob)
            odds = max(-800, min(600, odds))

            # Get actual result
            actual_home_win = bool(game["home_won"])

            # Evaluate bet (only on moneyline for now)
            if "moneyline" in bet_types:
                engine.evaluate_bet(
                    game_id=game_id,
                    date=game_date,
                    bet_type="home_ml",
                    model_prob=model_prob,
                    odds=odds,
                    actual_result=actual_home_win
                )

    results = engine.get_results()

    # Display Results
    st.success("✅ Backtest Complete!")

    # Summary Metrics
    st.subheader("Performance Summary")

    metric_col1, metric_col2, metric_col3, metric_col4 = st.columns(4)

    with metric_col1:
        st.metric("Total Bets", results.total_bets)
        st.metric("Win Rate", f"{results.win_rate:.1%}")

    with metric_col2:
        st.metric("Total Profit", f"${results.total_profit:+,.2f}")
        st.metric("ROI", f"{results.roi:+.1f}%")

    with metric_col3:
        st.metric("Units Profit", f"{results.units_profit:+.1f}u")
        st.metric("Max Drawdown", f"${results.max_drawdown():,.2f}")

    with metric_col4:
        breakeven_rate = 52.4  # At -110 odds
        status = "🟢" if results.win_rate * 100 >= breakeven_rate else "🔴"
        st.metric("vs Breakeven", f"{status} {results.win_rate * 100 - breakeven_rate:+.1f}%")
        st.metric("Longest Losing", f"{results.longest_losing_streak()} bets")

    # Performance Analysis
    st.markdown("---")
    st.subheader("Detailed Analysis")

    # Profitability assessment
    if results.roi > 5:
        st.success("🎯 **Strong simulated ROI** - The staking rules profit under these assumptions")
    elif results.roi > 0:
        st.info("📊 **Positive simulated ROI** - Modest returns under these assumptions")
    elif results.roi > -5:
        st.warning("⚠️ **Near break-even** - Consider adjusting parameters")
    else:
        st.error("❌ **Negative simulated ROI** - The strategy loses under these assumptions")

    # Recent Bets Table
    st.subheader("Recent Bets")

    if results.bets:
        recent_bets = results.bets[-20:]  # Last 20 bets
        bet_data = []

        for bet in recent_bets:
            result_icon = "✅" if bet.won else "❌"
            bet_data.append({
                "Date": bet.date,
                "Game": bet.game_id[-6:],  # Last 6 chars
                "Type": bet.bet_type.replace("_", " ").title(),
                "Odds": f"{bet.odds:+d}",
                "Stake": f"${bet.stake:.2f}",
                "Edge": f"{bet.edge*100:.1f}%",
                "Result": result_icon,
                "Profit": f"${bet.profit:+,.2f}"
            })

        df = pd.DataFrame(bet_data)
        st.dataframe(df, hide_index=True, width='stretch')

    # Cumulative Profit Chart
    st.subheader("Profit Curve")

    cumulative = []
    running_total = 0.0

    for bet in results.bets:
        if bet.profit is not None:
            running_total += bet.profit
            cumulative.append(running_total)

    if cumulative:
        profit_df = pd.DataFrame({
            "Bet Number": range(1, len(cumulative) + 1),
            "Cumulative Profit ($)": cumulative
        })
        st.line_chart(profit_df, x="Bet Number", y="Cumulative Profit ($)")

    # Download results
    st.download_button(
        "📥 Download Bet Log",
        data=pd.DataFrame([{
            "date": b.date,
            "game_id": b.game_id,
            "bet_type": b.bet_type,
            "odds": b.odds,
            "stake": b.stake,
            "model_prob": b.model_prob,
            "edge": b.edge,
            "won": b.won,
            "profit": b.profit
        } for b in results.bets]).to_csv(index=False),
        file_name=f"backtest_results_{config.start_date}_{config.end_date}.csv",
        mime="text/csv"
    )

# Interpretation Guide
st.markdown("---")
with st.expander("📚 Backtesting Guide"):
    st.markdown("""
    ### Understanding Backtest Results
    
    **Key Metrics Explained**
    
    | Metric | Description | Target |
    |--------|-------------|--------|
    | **Win Rate** | % of bets that won | > 52.4% for -110 odds |
    | **ROI** | Return on investment | > 5% is excellent |
    | **Units Profit** | Money made per unit bet | Positive = profitable |
    | **Max Drawdown** | Worst losing streak (in $) | Lower is better |
    
    **Interpreting Results**
    
    ✅ **Profitable Model** (ROI > 5%)
    - Model has genuine edge
    - Consider live betting with proper bankroll
    - Monitor for regression to mean
    
    📊 **Marginal Profit** (ROI 0-5%)
    - Model shows promise but needs refinement
    - Increase min edge requirement
    - Focus on higher-confidence bets
    
    ⚠️ **Break-even** (ROI -2% to 0%)
    - Model lacks edge or strategy too aggressive
    - Reduce Kelly fraction
    - Increase minimum edge threshold
    
    ❌ **Losing Money** (ROI < -2%)
    - Model predictions inaccurate
    - Recalibrate probability estimates
    - Check for data leakage or overfitting
    
    **Best Practices**
    
    1. **Sufficient Sample Size**: Need 100+ bets for statistical significance
    2. **Realistic Parameters**: Don't over-optimize on limited data
    3. **Out-of-Sample Testing**: Test on different time periods
    4. **Monitor Slippage**: Real odds may differ from historical closing lines
    5. **Account for Variance**: Even good models have losing streaks
    
    **Configuration Tips**
    
    - **Min Edge 2-3%**: Gives cushion for estimation errors
    - **Max Kelly 25%**: Prevents overexposure to single bets
    - **Unit Size 1-2%**: Standard bankroll management
    - **Focus on ML**: Moneyline bets have lowest variance
    
    **Production Implementation**
    
    To run real backtests:
    1. Save daily predictions to `data_files/predictions/`
    2. Store game results in `data_files/results/`
    3. Track actual odds (opening and closing lines)
    4. Run backtest with historical data
    5. Compare to this simulation for validation
    """)

add_betting_oracle_footer()
