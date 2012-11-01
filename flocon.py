#! /usr/bin/env python

import hashlib
import logging
import os
import random
import sys
import time

from twisted.internet import reactor
from twisted.internet.protocol import DatagramProtocol
from twisted.web import resource, server

_LOGGING_FORMAT = '%(message)s'
_LOGGING_FORMAT_DEBUG = '[%(levelname)s] %(module)s.%(funcName)s: %(message)s'

_REANNOUNCE_TIMER = 60 * 3
_TIMEOUT = 1.5 * _REANNOUNCE_TIMER

_MULTICAST_GROUP = '228.0.2.35'
_MULTICAST_PORT = 19432
_MULTICAST_ADDR = (_MULTICAST_GROUP, _MULTICAST_PORT)

_HTTP_PORT = _MULTICAST_PORT + 1

_ID = hashlib.sha1('{name}_{random_value}'.format(
    name = os.uname()[1],
    random_value = int(random.random() * 100000000),
)).hexdigest()

_PING_MSG = 'flocon: PING'
_PONG_MSG = 'flocon: PONG'

_SEPARATOR = '-'

_CLIENTS = dict()

def _find_fallback_mirror():
    with open('/etc/pacman.d/mirrorlist') as f:
        for line in f.readlines():
            if line.startswith("# flocon: Server"):
                try:
                    return line.split('=')[1].strip()
                except IndexError:
                    return None
    return None

_FALLBACK_MIRROR = _find_fallback_mirror()


class Client:
    def __init__(self, id, addr):
        self.id, self.last = id, None
        self.addr, self.port = addr
        self.update()

    def __str__(self):
        return '{{addr = {}; port = {}; id = {}}}'.format(
            self.addr, self.port, self.id
        )

    def update(self):
        self.last = time.time()

    def is_valid(self):
        return (time.time() - self.last) < _TIMEOUT


class MulticastClientManager(DatagramProtocol):
    def startProtocol(self):
        self.transport.setTTL(0)
        self.transport.joinGroup(_MULTICAST_GROUP)
        self.announce_presence()

    def datagramReceived(self, datagram, addr):
        logging.debug('Received a new UDP message from %r', addr)
        logging.debug('Message was: %s', datagram)
        try:
            _id, _msg = datagram.split(_SEPARATOR)
        except ValueError:
            logging.error('I couldn\'t understand last message.')
            return
        if _msg == _PING_MSG or _msg == _PONG_MSG:
            if _id == _ID:
                return
            try:
                _CLIENTS[_id].update()
            except KeyError:
                c = Client(_id, addr)
                logging.info('Client %s just connected!', c)
                _CLIENTS[_id] = c
                if _msg == _PING_MSG:
                    self.send_data(_PONG_MSG, addr)

    def send_data(self, msg, addr):
        self.transport.write(_SEPARATOR.join([_ID, msg]), addr)

    def announce_presence(self):
        self.send_data(_PING_MSG, _MULTICAST_ADDR)
        reactor.callLater(_REANNOUNCE_TIMER, self.announce_presence)


def timeout_clients():
    for _id, _client in _CLIENTS.items():
        if _client.is_valid():
            continue
        logging.info('Client %s disconnected!', _client)
        del _CLIENTS[_id]
    reactor.callLater(_REANNOUNCE_TIMER, timeout_clients)

def main(args):
    if '-d' in args or '--debug' in args:
        logging.basicConfig(level=logging.DEBUG, format=_LOGGING_FORMAT_DEBUG)
    else:
        logging.basicConfig(level=logging.INFO, format=_LOGGING_FORMAT)

    if _FALLBACK_MIRROR is None:
        logging.error('Fallback mirror was not found in your configuration.')
        sys.exit()

    # Displaying some information about us.
    logging.info('Id: %s', _ID)
    logging.info('Multicast group: %s', _MULTICAST_GROUP)
    logging.info('Multicast port: %s', _MULTICAST_PORT)
    logging.info('Fallback mirror: %s', _FALLBACK_MIRROR)
    logging.info('')

    # Multicast server/client
    reactor.listenMulticast(_MULTICAST_PORT, MulticastClientManager(), listenMultiple=True)

    # Timeout clients when not reannouncing.
    timeout_clients()

    reactor.run()

if __name__ == '__main__':
    main(sys.argv[1:])
