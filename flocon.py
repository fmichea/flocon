#! /usr/bin/env python

import hashlib
import logging
import os
import random
import sys

from twisted.internet.protocol import DatagramProtocol
from twisted.internet import reactor

_LOGGING_FORMAT = '[%(levelname)s] %(module)s.%(funcName)s: %(message)s'

_MULTICAST_GROUP = '228.0.2.35'
_MULTICAST_PORT = 19432

_ID = hashlib.sha1('{name}_{random_value}'.format(
    name = os.uname()[1],
    random_value = int(random.random() * 100000000),
)).hexdigest()

_PING_MSG = 'flocon: PING'
_PONG_MSG = 'flocon: PONG'

_SEPARATOR = '-'

_CLIENTS = list()


class Multicast(DatagramProtocol):
    def startProtocol(self):
        self.transport.setTTL(0)
        self.transport.joinGroup(_MULTICAST_GROUP)
        self.send_data(_PING_MSG, (_MULTICAST_GROUP, _MULTICAST_PORT))

    def datagramReceived(self, datagram, addr):
        try:
            _msg, _id = datagram.split(_SEPARATOR)
        except ValueError:
            logging.error('Recieved a message I can\'t understand: {}'.format(
                datagram
            ))
            return
        if _msg == _PING_MSG or _msg == _PONG_MSG:
            if addr in _CLIENTS or _id == _ID:
                logging.info('Already knew this client or this is me...')
                return
            logging.info('New client! %s', repr(addr))
            _CLIENTS.append(addr)
            if _msg == _PING_MSG:
                self.send_data(_PONG_MSG, addr)

    def send_data(self, msg, addr):
        self.transport.write(_SEPARATOR.join([msg, _ID]), addr)


def main(args):
    logging.basicConfig(level=logging.DEBUG, format=_LOGGING_FORMAT)

    # Multicast server/client
    reactor.listenMulticast(_MULTICAST_PORT, Multicast(), listenMultiple=True)
    reactor.run()

if __name__ == '__main__':
    main(sys.argv[1:])
