.PHONY: setup lint test run-backtest run-dryrun run-live clean

setup:
	pip install -e ".[dev]"

lint:
	ruff check .
	mypy config/ security/ data/ strategy/ backtest/ execution/ risk/ monitoring/

test:
	pytest tests/ -v --cov=. --cov-report=term-missing

run-backtest:
	python main.py backtest --strategy dual_ma --symbol BTC/USDT --timeframe 4h

run-dryrun:
	python main.py dry-run --strategy dual_ma --symbol BTC/USDT

run-live:
	python main.py live --strategy dual_ma --symbol BTC/USDT

clean:
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	rm -rf .pytest_cache .mypy_cache .ruff_cache dist/ build/ *.egg-info
