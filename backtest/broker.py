import json
import logging
from importlib import import_module
from math import copysign
from multiprocessing.connection import Connection
from pathlib import Path
from threading import Thread
from typing import Callable

from .data import Msg, Positions

logger = logging.getLogger(Path(__file__).stem)


class Broker(Thread):

    def __init__(self, cash: float, symbols: dict, exchanges: list, calc_quantity) -> None:
        super().__init__(name=self.__class__.__name__)

        self.input: Connection
        self.output: Connection

        self.calc_quantity = calc_quantity

        logger.debug('Loading modules...')
        self.exchanges = {}
        for exchange in exchanges:
            self.exchanges[exchange] = import_module(f'{exchange}')

        self._loop: bool = True
        self._cash: float = cash
        self._initial_cash: float = cash
        self._positions: Positions = Positions()
        self._symbols: dict[str, dict] = symbols

        self._handlers: dict[str, Callable[[Msg], None]] = {
            'SIGNAL': self._handler_signal,
            'QUIT': self._handler_quit,
        }

        logger.debug('Initialized')

    def run(self):
        logger.debug('Starting...')

        self.output.send(Msg('CASH', cash=self._initial_cash))

        while self._loop:
            msg = self.input.recv()
            logger.debug(f'Received: {msg}')
            self._handlers[msg.type](msg)

    def _get_exchange(self, symbol):
        try:
            exchange = self._symbols[symbol]['exchange']
            return self.exchanges[exchange]
        except KeyError:
            logger.warning(f'Unknown symbol: {symbol}')
            return next(iter(self.exchanges.values()))  # return the first one

    def _handler_signal(self, msg: Msg) -> None:
        quantity = self.calc_quantity(
            msg.price,
            msg.strength,
            self._cash,
            self._positions)

        exchange = self._get_exchange(msg.symbol)

        price = exchange.simulate_price(
            msg.price,
            quantity)

        commission = exchange.calc_commission(
            price,
            quantity)

        tax = exchange.calc_tax(
            price,
            quantity)

        cost = self._calc_total_cost(
            price,
            quantity,
            commission,
            tax)

        self._cash -= cost

        self._positions[msg.symbol].quantity += quantity

        o = Msg("ORDER",
                symbol=msg.symbol,
                price=price,
                quantity=quantity,
                strength=msg.strength,
                commission=commission,
                tax=tax,
                slippage=msg.price - price,
                cash=self._cash,
                timestamp=msg.timestamp)
        self.output.send(o)

        q = Msg('QUANTITY',
                symbol=msg.symbol,
                quantity=self._positions[msg.symbol].quantity)
        self.output.send(q)

    def _handler_quit(self, _: Msg) -> None:
        self._loop = False

    @staticmethod
    def _calc_total_cost(price: float, quantity: float, commission: float, tax: float) -> float:
        return copysign(1, quantity) \
               * (abs(quantity)
                  * price
                  + commission
                  + tax)
