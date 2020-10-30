import os
import time
import errno
import select
import socket
import logging
import functools

__all__ = ['TCP']

Timeout = socket.timeout
OPENING, OPEN, CLOSED = range(3)


ERR_MAP = {
    errno.ECONNREFUSED: ConnectionRefusedError,
    errno.ECONNRESET: ConnectionResetError,
    errno.ECONNABORTED: ConnectionAbortedError,
    errno.EPIPE: BrokenPipeError,
    errno.EBADF: OSError,
}


def to_error(err):
    if err:
        return ERR_MAP.get(err, ConnectionError)(err, os.strerror(err))


def create_connection(host, port):
    err = None
    for res in socket.getaddrinfo(host, port, 0, socket.SOCK_STREAM):
        af, socktype, proto, canonname, sa = res
        sock = None
        try:
            sock = socket.socket(af, socktype, proto)
            sock.setblocking(False)
            sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
            res = sock.connect_ex(sa)
            if res not in {0, errno.EINPROGRESS}:
                raise to_error(res)
            # Break explicitly a reference cycle
            err = None
            return sock
        except OSError as _:
            err = _
            if sock is not None:
                sock.close()

    raise error("getaddrinfo returns an empty list") if err is None else err


def wait_open(sock, timeout=None):
    _, w, _ = select.select((), (sock,), (), timeout)
    if not w:
        err = sock.getsockopt(socket.SOL_SOCKET, socket.SO_ERROR)
        err = to_error(err) if err else Timeout("timeout trying to connect")
        raise err


def stream(sock, buffer_size=8096, timeout=None):
    readers = sock,
    while True:
        start = time.monotonic()
        r, _, _ = select.select(readers, (), (), timeout)
        end = time.monotonic()
        if timeout is not None:
            timeout -= start - end
        if (timeout is not None and timeout <= 0) or not r:
            raise Timeout("read timeout")
        data = sock.recv(buffer_size)
        if not data:
            break
        yield data


def check_open(f):
    @functools.wraps(f)
    def wrapper(self, *args, **kwargs):
        state = self._state
        if state is CLOSED:
            raise to_error(errno.EBADF)
        elif state is OPENING:
            self._wait_open()
        return f(self, *args, **kwargs)
    return wrapper


def close_on_error(f):
    @functools.wraps(f)
    def wrapper(self, *args, **kwargs):
        try:
            return f(self, *args, **kwargs)
        except BaseException:
            self.close()
            raise
    return wrapper


class RawTCP:

    def __init__(self, host, port, eol=b"\n", timeout=None):
        self.eol = eol
        self.timeout = timeout
        self._buffer = b""
        # create a non blocking socket
        self._state = OPENING
        self._connection_time = time.monotonic()
        self._sock = create_connection(host, port)

    def __del__(self):
        self.close()

    def _wait_open(self):
        if self._state is OPEN:
            return
        elif self._state is CLOSED:
            raise OSError("would block forever")
        elif self._state is OPENING:
            timeout = self.timeout
            if timeout is not None:
                timeout -= time.monotonic() - self._connection_time
            wait_open(self._sock, timeout=timeout)
        self._state = OPEN

    @close_on_error
    def _write(self, data):
        self._sock.sendall(data)

    @close_on_error
    def _read(self, n, timeout=None):
        if self._buffer:
            data, self._buffer = self._buffer, b""
            return data
        timeout = self.timeout if timeout is None else timeout
        r, _, _ = select.select((self._sock,), (), (), timeout)
        if r:
            data = self._sock.recv(8096)
            if not data:
                raise ConnectionError("remote end closed")
            return data
        else:
            raise Timeout("timeout reading from socket")

    @close_on_error
    def _readline(self, eol=None, timeout=None):
        eol = self.eol if eol is None else eol
        timeout = self.timeout if timeout is None else timeout
        data, eo, left = self._buffer.partition(eol)
        if eo:
            self._buffer = left
            return data + eo
        for data in stream(self._sock, timeout=timeout):
            self._buffer += data
            data, eo, left = self._buffer.partition(eol)
            if eo:
                self._buffer = left
                return data + eo
        else:
            raise ConnectionError("remote end closed")

    def state(self):
        return self._state

    def close(self):
        self._state = CLOSED
        self._buffer = b""
        if self._sock is not None:
            try:
                self._sock.shutdown(socket.SHUT_RDWR)
                self._sock.close()
            except OSError:
                pass
            finally:
                self._sock = None

    @check_open
    def write(self, data):
        self._write(data)

    @check_open
    def read(self, n, timeout=None):
        return self._read(n, timeout=timeout)

    @check_open
    def readline(self, eol=None, timeout=None):
        return self._readline(eol=eol, timeout=timeout)

    @check_open
    def write_read(self, data, n, timeout=None):
        self._write(data)
        return self._read(n, timeout=timeout)

    @check_open
    def write_readline(self, data, eol=None, timeout=None):
        self._write(data)
        return self._readline(eol=eol, timeout=timeout)


def ensure_connection(f):
    @functools.wraps(f)
    def wrapper(self, *args, **kwargs):
        made_connection = self._ensure_connected()
        try:
            return f(self, *args, **kwargs)
        except Timeout:
            raise
        except OSError:
            self.close()
            if made_connection:
                raise
            self._ensure_connected()
            return f(self, *args, **kwargs)
    return wrapper


class TCP:

    def __init__(self, host, port, eol=b"\n", timeout=None):
        self.host = host
        self.port = port
        self.eol = eol
        self.timeout = timeout
        self.connection_counter = 0
        self._sock = None
        self._log = logging.getLogger("icepap.TCP({})".format(host))

    def connected(self):
        return self._sock is not None and self._sock.state() is not CLOSED

    def _ensure_connected(self):
        if self.connected():
            return False
        self._sock = RawTCP(
            self.host, self.port, eol=self.eol, timeout=self.timeout
        )
        self.connection_counter += 1
        self._log.debug("reconnecting #%d...", self.connection_counter)
        return True

    def close(self):
        if self._sock is not None:
            self._sock.close()

    @ensure_connection
    def write(self, data):
        self._log.debug("write -> %r", data)
        self._sock.write(data)

    @ensure_connection
    def write_read(self, data, n, timeout=None):
        self._log.debug("write_read -> %r", data)
        reply = self._sock.write_read(data, n, timeout=timeout)
        self._log.debug("write_read <- %r", reply)
        return reply

    @ensure_connection
    def write_readline(self, data, eol=None, timeout=None):
        self._log.debug("write_readline -> %r", data)
        reply = self._sock.write_readline(data, eol=eol, timeout=timeout)
        self._log.debug("write_readline <- %r", reply)
        return reply
