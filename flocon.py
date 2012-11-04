#! /usr/bin/env python

import hashlib
import logging
import os
import random
import string
import sys
import time

from twisted.internet import reactor
from twisted.internet.protocol import DatagramProtocol
from twisted.web import resource, server, static

_LOGGING_FORMAT = '%(message)s'
_LOGGING_FORMAT_DEBUG = '[%(levelname)s] %(module)s.%(funcName)s: %(message)s'


_ROOT_PKG_CACHE = '/var/cache/pacman/pkg/'

_WAITING_TIMER = 1
_REANNOUNCE_TIMER = 60 * 3
_TIMEOUT = 1.5 * _REANNOUNCE_TIMER

_MULTICAST_GROUP = '228.0.2.35'
_MULTICAST_PORT = 19432
_MULTICAST_ADDR = (_MULTICAST_GROUP, _MULTICAST_PORT)

_HTTP_FILE_PORT = _MULTICAST_PORT
_HTTP_PACMAN_PORT = _HTTP_FILE_PORT + 1

_ID = hashlib.sha1('{name}_{random_value}'.format(
    name = os.uname()[1],
    random_value = int(random.random() * 100000000),
)).hexdigest()

_HAS_MSG = 'flocon: HAS'
_NO_MSG = 'flocon: NO'
_PING_MSG = 'flocon: PING'
_PONG_MSG = 'flocon: PONG'
_YES_MSG = 'flocon: YES'

_SEPARATOR = '-'
_SEPARATOR_F = ' = '

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

_FALLBACK_MIRROR = str(_find_fallback_mirror()) + '/$filename'
_FILE_SERVER = 'http://$ip:$port/$filename'


class Client:
    def __init__(self, id, addr):
        self.id, self.last, self.addr = id, None, addr
        self.ip, self.port = addr
        self.update()

    def __str__(self):
        return '{{addr = {}; port = {}; id = {}}}'.format(
            self.addr, self.port, self.id
        )

    def update(self):
        self.last = time.time()

    def is_valid(self):
        return (time.time() - self.last) < _TIMEOUT

_REQUEST = None

class MulticastClientManager(DatagramProtocol):
    def startProtocol(self):
        self.transport.joinGroup(_MULTICAST_GROUP)
        self.announce_presence()

    def datagramReceived(self, datagram, addr):
        logging.debug('Received a new UDP message from %r', addr)
        logging.debug('Message was: %s', datagram)
        try:
            _id, _msg = datagram.split(_SEPARATOR, 1)
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
            return

        # From here, if we don't know the client, we just ignore the message.
        try:
            client = _CLIENTS[_id]
        except KeyError:
            logging.error('I don\'t know this client!')
            return
        try:
            _msg, _filename = _msg.split(_SEPARATOR_F)
        except KeyError:
            logging.error('I couldn\'t understand last file message.')
            return
        if _msg == _HAS_MSG:
            self.has_file(client, _filename)
            return
        if _REQUEST is None or _REQUEST.filename != _filename:
            return
        if _msg == _YES_MSG and _REQUEST is not None:
            _REQUEST.redirect_file_server(_id)
        elif _msg == _NO_MSG and _REQUEST is not None:
            _REQUEST.client_answered_no()

    def send_data(self, msg, addr):
        self.transport.write(_SEPARATOR.join([_ID, msg]), addr)

    def send_with_filename(self, msg, filename, addr):
        self.send_data(_SEPARATOR_F.join([msg, filename]), addr)

    def announce_presence(self):
        logging.debug('Sending presence to multicast group.')
        self.send_data(_PING_MSG, _MULTICAST_ADDR)
        reactor.callLater(_REANNOUNCE_TIMER, self.announce_presence)

    def ask_file(self, filename):
        for _, client in _CLIENTS.iteritems():
            logging.debug('Sending request for file to %s.', client)
            self.send_with_filename(_HAS_MSG, filename, client.addr)
        return len(_CLIENTS)

    def has_file(self, client, filename):
        logging.info('Client %s asks if I have %s.', client, filename)
        packages = []
        for _, _, files in os.walk(_ROOT_PKG_CACHE):
            for _filename in files:
                if _filename.endswith('.tar.xz'):
                    packages.append(_filename)
        if filename in packages:
            logging.info('I have it!')
            self.send_with_filename(_YES_MSG, filename, client.addr)
        else:
            logging.info('It is not in my cache...')
            self.send_with_filename(_NO_MSG, filename, client.addr)

_MULTICAST_OBJ = MulticastClientManager()

class Request:
    def __init__(self, request):
        self.request = request
        _, self.repo, _, self.arch, self.filename = self.request.uri.split('/')

    def init_response(self):
        if not _CLIENTS:
            self.redirect_fallback_mirror()
        else:
            self.clients = _MULTICAST_OBJ.ask_file(self.filename)
        reactor.callLater(1, self.redirect_fallback_mirror)

    def __str__(self):
        return self.request.uri

    def redirect_file_server(self, id):
        global _REQUEST
        if _REQUEST is None or _REQUEST.filename != self.filename:
            return
        client = _CLIENTS[id]
        logging.info('Redirecting to client %s for packet %s.', client,
                     self.filename)
        url = string.Template(_FILE_SERVER).safe_substitute({
            'ip': client.ip, 'port': client.port, 'filename': self.filename,
        })
        logging.debug('Redirect URL: %s', url)
        self.request.redirect(url)
        self.request.finish()
        _REQUEST = None

    def redirect_fallback_mirror(self):
        global _REQUEST
        if _REQUEST is None or _REQUEST.filename != self.filename:
            return
        logging.info('Redirecting to fallback mirror.')
        url = string.Template(_FALLBACK_MIRROR).safe_substitute({
            'repo': self.repo, 'arch': self.arch, 'filename': self.filename,
        })
        logging.debug('Redirect URL: %s', url)
        self.request.redirect(url)
        self.request.finish()
        _REQUEST = None

    def client_answered_no(self):
        self.clients -= 1
        logging.debug('One of the clients answered no. Still %d clients '
                      'remaining.', self.clients)
        if self.clients == 0:
            self.redirect_fallback_mirror()


class LocalHttpServer(resource.Resource):
    isLeaf = True

    def render_GET(self, request):
        global _REQUEST
        logging.debug('Recieved GET request for %s', request.uri)
        _REQUEST = Request(request)
        _REQUEST.init_response()
        return server.NOT_DONE_YET


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

    if _FALLBACK_MIRROR.startswith('None'):
        logging.error('Fallback mirror was not found in your configuration.')
        sys.exit()

    # Displaying some information about us.
    logging.info('Id: %s', _ID)
    logging.info('Multicast group: %s', _MULTICAST_GROUP)
    logging.info('Multicast port: %s', _MULTICAST_PORT)
    logging.info('Fallback mirror: %s', _FALLBACK_MIRROR)
    logging.info('')

    # Multicast server/client
    reactor.listenMulticast(_MULTICAST_PORT, _MULTICAST_OBJ)

    # HTTP Server for pacman.
    reactor.listenTCP(_HTTP_PACMAN_PORT, server.Site(LocalHttpServer()))

    # HTTP Server for files.
    root = static.File(_ROOT_PKG_CACHE)
    reactor.listenTCP(_HTTP_FILE_PORT, server.Site(root))

    # Timeout clients when not reannouncing.
    timeout_clients()

    reactor.run()

if __name__ == '__main__':
    main(sys.argv[1:])
