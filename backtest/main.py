import argparse
import json
import logging
from multiprocessing import cpu_count
from pathlib import Path
from typing import Any

from .analyzer import Analyzer
from .broker import Broker
from .fetcher import Fetcher
from .ledger import Ledger
from .router import Router

logger = logging.getLogger(Path(__file__).stem)


def validate(**config):
    required = {'market', 'strategy', 'ticks_dir', 'ledger_dir', 'cash'}

    if missing := required - set(config):
        print('Missing: ' + ', '.join(missing))
        return False

    dirs = {key: config[key] for key in config if key.endswith('_dir')}
    for k, v in dirs.items():
        if not Path(v).exists():
            print(f'Not found dir: {v}')
            return False

    return True


def run(market: str,
        strategy: str,
        ticks_dir: str,
        ledger_dir: str,
        cash: float = 1_000_000):
    logger.info('Started')

    fetcher = Fetcher(Path(ticks_dir))
    analyzers = [Analyzer(strategy)
                 for _ in range((cpu_count() or 2) - 1)]
    broker = Broker(market, strategy, cash)
    ledger = Ledger(Path(ledger_dir))
    nodes: list[Any] = [ledger, broker, *analyzers, fetcher]

    router = Router()
    router.connect(nodes)

    nodes.insert(0, router)
    [node.start() for node in nodes]
    [node.join() for node in reversed(nodes)]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('-c', '--config', default='config.json')
    args = parser.parse_args()

    with Path(args.config).open('rt', encoding='utf8') as f:
        config = json.load(f)

    if validate(**config):
        run(**config)


    # assert self._msg_counter['TICK'] \
    #        == self._msg_counter['SIGNAL'] \
    #        == self._msg_counter['ORDER']
