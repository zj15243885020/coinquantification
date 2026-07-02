"""CLI 入口 - 支持 backtest / dry-run / live 三种运行模式"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from config.settings import load_settings
from monitoring.logger import setup_logger, get_logger
from strategy import STRATEGY_REGISTRY


def run_backtest(args: argparse.Namespace) -> None:
    """运行回测"""
    from backtest.engine import BacktestEngine
    from backtest.report import generate_report, print_summary
    from data.store import DataStore

    settings = load_settings(args.config)
    logger = setup_logger(level=settings.system.log_level, log_format=settings.system.log_format)
    logger.info("Starting backtest", extra={"strategy": args.strategy, "symbol": args.symbol})

    strategy_cls = STRATEGY_REGISTRY.get(args.strategy)
    if not strategy_cls:
        logger.error(f"Unknown strategy: {args.strategy}. Available: {list(STRATEGY_REGISTRY.keys())}")
        sys.exit(1)

    strategy_params = settings.strategies.get(args.strategy, {})
    strategy_params["symbol"] = args.symbol
    strategy = strategy_cls(params=strategy_params)

    store = DataStore(cache_dir=settings.data.cache_dir)
    bars = store.load_ohlcv(args.symbol, args.timeframe, start=settings.backtest.start_date, end=settings.backtest.end_date)

    if bars.empty:
        logger.warning("No cached data found. Fetching from exchange...")
        from data.feed import DataFeed
        from execution.adapters.binance_adapter import BinanceAdapter

        adapter = BinanceAdapter(config=settings.exchanges.get("binance", {}).model_dump() if settings.exchanges.get("binance") else {})
        adapter.connect()
        feed = DataFeed(adapter)
        bars = feed.fetch_ohlcv_full(
            args.symbol, args.timeframe,
            start=settings.backtest.start_date,
            end=settings.backtest.end_date,
        )
        store.save_ohlcv(args.symbol, args.timeframe, bars)
        adapter.disconnect()

    if bars.empty:
        logger.error("No data available for backtest")
        sys.exit(1)

    logger.info(f"Loaded {len(bars)} bars for {args.symbol} {args.timeframe}")

    engine = BacktestEngine(
        strategy=strategy,
        initial_capital=settings.backtest.initial_capital,
        commission_maker=settings.backtest.commission.maker,
        commission_taker=settings.backtest.commission.taker,
        slippage_model=settings.backtest.slippage.model,
        slippage_value=settings.backtest.slippage.value,
    )

    state = engine.run(bars)

    summary = print_summary(state)
    print(summary)
    logger.info("Backtest completed")

    report_path = Path("backtest_report.html")
    generate_report(state, report_path)
    logger.info(f"Report saved to {report_path}")


def run_dry_run(args: argparse.Namespace) -> None:
    """运行模拟盘"""
    settings = load_settings(args.config)
    logger = setup_logger(level=settings.system.log_level, log_format=settings.system.log_format)
    logger.info("Starting dry-run mode", extra={"strategy": args.strategy, "symbol": args.symbol})

    strategy_cls = STRATEGY_REGISTRY.get(args.strategy)
    if not strategy_cls:
        logger.error(f"Unknown strategy: {args.strategy}")
        sys.exit(1)

    strategy_params = settings.strategies.get(args.strategy, {})
    strategy_params["symbol"] = args.symbol
    strategy = strategy_cls(params=strategy_params)

    logger.info("Dry-run mode: monitoring market and generating signals (no real orders)")
    logger.info("Press Ctrl+C to stop")

    from execution.adapters.binance_adapter import BinanceAdapter
    from execution.dry_run import DryRunAdapter
    from execution.order_manager import OrderManager
    from risk.engine import RiskEngine

    binance_config = settings.exchanges.get("binance")
    adapter = BinanceAdapter(config=binance_config.model_dump() if binance_config else {})
    adapter.connect()

    dry_adapter = DryRunAdapter(adapter, config={"commission_rate": settings.backtest.commission.taker})
    order_manager = OrderManager(dry_adapter)
    risk_engine = RiskEngine(
        max_position_pct=settings.risk.max_position_pct,
        max_daily_loss_pct=settings.risk.max_daily_loss_pct,
    )

    from data.feed import DataFeed
    feed = DataFeed(adapter)

    import time
    timeframe_seconds = {"1m": 60, "5m": 300, "15m": 900, "1h": 3600, "4h": 14400}
    interval = timeframe_seconds.get(args.timeframe, 3600)

    try:
        while True:
            bars = feed.fetch_ohlcv(args.symbol, args.timeframe, limit=200)
            if not bars.empty:
                strategy.calculate_indicators(bars, len(bars) - 1)
                signal = strategy.on_bar(len(bars) - 1, bars)
                if signal:
                    allowed, reason = risk_engine.check_signal(signal, 10000.0, 0.0)
                    if allowed:
                        from execution.adapters.base import OrderSide, OrderType
                        order = order_manager.submit_order(
                            args.symbol, OrderSide.BUY, OrderType.MARKET, 0.001
                        )
                        logger.info(f"DRY-RUN order: {order.side.value} {order.amount} {args.symbol} @ {order.filled_price}")
                    else:
                        logger.warning(f"Signal blocked by risk engine: {reason}")
            time.sleep(interval)
    except KeyboardInterrupt:
        logger.info("Dry-run stopped by user")
    finally:
        adapter.disconnect()


def run_live(args: argparse.Namespace) -> None:
    """运行实盘"""
    settings = load_settings(args.config)
    logger = setup_logger(level=settings.system.log_level, log_format=settings.system.log_format)
    logger.warning("LIVE MODE - Real money trading!", extra={"strategy": args.strategy, "symbol": args.symbol})
    logger.info("Live mode is not yet fully implemented. Use --dry-run for paper trading.")
    logger.info("To enable live trading, configure your exchange API keys in the vault.")


def cli_entry() -> None:
    parser = argparse.ArgumentParser(description="Crypto Quant MVP - 自用型量化交易系统")
    subparsers = parser.add_subparsers(dest="command", help="运行模式")

    for cmd in ["backtest", "dry-run", "live"]:
        sp = subparsers.add_parser(cmd)
        sp.add_argument("--strategy", "-s", default="dual_ma", choices=list(STRATEGY_REGISTRY.keys()))
        sp.add_argument("--symbol", default="BTC/USDT")
        sp.add_argument("--timeframe", "-t", default="4h")
        sp.add_argument("--config", "-c", default=None, help="Path to config YAML")

    args = parser.parse_args()

    if args.command == "backtest":
        run_backtest(args)
    elif args.command == "dry-run":
        run_dry_run(args)
    elif args.command == "live":
        run_live(args)
    else:
        parser.print_help()


if __name__ == "__main__":
    cli_entry()
