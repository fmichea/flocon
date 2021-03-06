# main.py - Everything is in there.
# Author: Franck Michea < franck.michea@gmail.com >
# License: New BSD License (See LICENSE)

import hashlib
import logging
import os
import random
import signal
import socket
import string
import subprocess
import sys
import time

from twisted.internet import reactor
from twisted.internet.protocol import DatagramProtocol
from twisted.internet.error import MulticastJoinError
from twisted.web import resource, server, static

def has_option(short, long):
    return short in sys.argv[1:] or long in sys.argv[1:]

_DEBUG = has_option('-d', '--debug')
_IP = has_option('-i', '--ip')
_QUIET = has_option('-q', '--quiet')

_LOGGING_FORMAT = '%(message)s'
_LOGGING_FORMAT_DEBUG = '[%(levelname)s] %(module)s.%(funcName)s: %(message)s'\

_ROOT_PKG_CACHE = '/var/cache/pacman/pkg/'

_REANNOUNCE_TIMER = 60 * 3
_TIMEOUT = 1.5 * _REANNOUNCE_TIMER
_TIMEOUT_JOINERROR = 180
_WAITING_TIMER = 1

_MULTICAST_GROUP = '228.0.2.35'
_MULTICAST_PORT = 19432
_MULTICAST_ADDR = (_MULTICAST_GROUP, _MULTICAST_PORT)

_HTTP_FILE_PORT = _MULTICAST_PORT
_HTTP_PACMAN_PORT = _HTTP_FILE_PORT + 1

_ID = hashlib.sha1('{name}_{random_value}'.format(
    name = os.uname()[1],
    random_value = int(random.random() * 100000000),
)).hexdigest()

_DISCONNECT_MSG = 'flocon: DISCONNECT'
_HAS_MSG = 'flocon: HAS'
_NO_MSG = 'flocon: NO'
_PING_MSG = 'flocon: PING'
_PONG_MSG = 'flocon: PONG'
_YES_MSG = 'flocon: YES'

_SEPARATOR = '-'
_SEPARATOR_F = ' = '

_CLIENTS = dict()

def _list_clients(signum, stack_frame):
    c_len = len(_CLIENTS)
    logging.info('\nThere %s %s client%s connected.',
                 'are' if c_len > 1 else 'is', c_len, 's' if c_len > 1 else '')
    for client in _CLIENTS.values():
        logging.info(' - %s', client.display())
    logging.info('')

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
        self.id, self.last, self.addr, self.connected = id, None, addr, True
        self.ip, self.port, self.host = addr[0], addr[1], None
        self.find_host()
        self.update()

    def __str__(self):
        return self.display(display=False)

    def display(self, display=True):
        if _DEBUG or display:
            return '{{id = {}; host = {}; ip = {}; port = {}}}'.format(
                self.id, '[unknown]' if self.host is None else self.host,
                self.ip, self.port,
            )
        elif _IP or self.host is None:
            return '{{ip = {}; port = {}}}'.format(self.ip, self.port)
        else:
            return '{{host = {}; port = {}}}'.format(self.host, self.port)

    def update(self):
        self.last = time.time()

    def is_valid(self):
        return self.connected and (time.time() - self.last) < _TIMEOUT

    def find_host(self):
        kwargs = {'stdout': subprocess.PIPE, 'stderr': subprocess.PIPE}
        try:
            p = subprocess.Popen(['host', self.ip], **kwargs)
        except OSError:
            return
        out, _ = p.communicate()
        if p.returncode == 0:
            self.host = out.split()[-1][:-1]

_REQUEST = None

class MulticastClientManager(DatagramProtocol):
    def __init__(self, *args, **kwargs):
        try:
            DatagramProtocol.__init__(self, *args, **kwargs)
        except AttributeError:
            pass
        self.__attempts = _TIMEOUT_JOINERROR

    def startProtocol(self, signum=None, stack_frame=None):
        def multicastError(_):
            self.__attempts -= 1
            if self.__attempts == 0:
                logging.info('Impossible to connect to network. Send me '
                             'SIGUSR2 when you have some network available.')
                signal.signal(signal.SIGUSR2, self.startProtocol)
                self.__attempts = _TIMEOUT_JOINERROR
            else:
                logging.debug('Multicast join failed!')
                reactor.callLater(5, self.startProtocol)
        def mutlicastJoined(_):
            self.announce_presence()
        if signum is not None:
            signal.signal(signal.SIGUSR2, signal.SIG_IGN)
        joiner = self.transport.joinGroup(_MULTICAST_GROUP)
        joiner.addCallback(mutlicastJoined)
        joiner.addErrback(multicastError)
        return joiner

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
                logging.info('Client %s connected!', c)
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

        if _msg == _DISCONNECT_MSG:
            client.connected = False
            timeout_clients()
            return

        # File message.
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
        try:
            self.transport.write(_SEPARATOR.join([_ID, msg]), addr)
        except socket.error:
            pass

    def send_with_filename(self, msg, filename, addr):
        self.send_data(_SEPARATOR_F.join([msg, filename]), addr)

    def announce_presence(self):
        logging.debug('Sending presence to multicast group.')
        self.send_data(_PING_MSG, _MULTICAST_ADDR)
        reactor.callLater(_REANNOUNCE_TIMER, self.announce_presence)

    def announce_disconnection(self):
        self.send_data(_DISCONNECT_MSG, _MULTICAST_ADDR)

    def ask_file(self, filename):
        for _, client in _CLIENTS.iteritems():
            logging.debug('Sending request for file to %s.', client)
            self.send_with_filename(_HAS_MSG, filename, client.addr)
        return len(_CLIENTS)

    def has_file(self, client, filename):
        packages = []
        for _, _, files in os.walk(_ROOT_PKG_CACHE):
            for _filename in files:
                if _filename.endswith('.tar.xz'):
                    packages.append(_filename)
        if filename in packages:
            logging.info('%s: %s ? YES', client, filename)
            self.send_with_filename(_YES_MSG, filename, client.addr)
        else:
            logging.info('%s: %s ? NO', client, filename)
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
        logging.info('%s: Redirecting to client %s', self.filename, client)
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
        if _FALLBACK_MIRROR.startswith('None'):
            # No fallback mirror is set in configuration, so we just return an
            # error.
            logging.info('%s: No fallback mirror: 404 Not Found.', self.filename)
            self.request.setResponseCode(404)
            self.request.finish()
        else:
            logging.info('%s: Redirecting to fallback mirror.', self.filename)
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


def disconnect_multicast():
    # Send disconnect message to everyone.
    _MULTICAST_OBJ.announce_disconnection()


def main():
    if _DEBUG:
        logging.basicConfig(level=logging.DEBUG, format=_LOGGING_FORMAT_DEBUG)
    elif _QUIET:
        logging.basicConfig(level=logging.CRITICAL)
    else:
        logging.basicConfig(level=logging.INFO, format=_LOGGING_FORMAT)

    # Hook on SIGUSR1
    signal.signal(signal.SIGUSR1, _list_clients)
    signal.signal(signal.SIGUSR2, signal.SIG_IGN)

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

    # End of the program.
    reactor.addSystemEventTrigger('before', 'shutdown', disconnect_multicast)

    reactor.run()


if __name__ == '__main__':
    main()
