"""Start new Terminal Windows with print and input control."""

import os
import sys
import json
import uuid
import socket
import platform
import subprocess

from base64 import b64encode, b64decode
from threading import Thread, Event, Lock


class WindowTerminal():
    """Start new Terminal Windows with print and input control."""

    ENCODING = 'utf-8'
    BUFFER_SIZE = 2**16

    BIND_IP = '127.0.0.1'

    PROCESSES_COMMANDS = {
        'window': {
            'arg': ('start', '/wait', 'cmd', '/c', 'python'), 
            'shell': True
        },
        'gnome': {
            'arg': ('gnome-terminal', '--', 'bash', '-c', 'python3 {}'), 
            'shell': False
        }
    }

    SOCKET_TIMEOUT = 3
    BYTES_MESSAGE_END = b'\r\n'
    MAX_SIMULTANEOUS_WINDOW_START = 10

    _process_command = None
    _server_socket = None
    _server_thread = None
    _server_shutdown_flag = Event()
    
    _windows = {}

    def __init__(self, server_address):
        self._uuid = str(uuid.uuid1())

        self._server_address = server_address

        self._input_callbacks = []
        self._last_result_input = None
        
        self._close_flag = Event()
        self._wait_close = Event()
        self._wait_input = Event()

        self._wait_connection_lock = Lock()
        self._wait_connection_lock.acquire()

        self._connection = None
        self._finished = False

    @property
    def uuid(self):
        """UUID identifying the Window Terminal"""
        return self._uuid

    def open(self):
        """Open Window Terminal"""
        if self._finished:
            raise RuntimeError('Window instance can be opened only once')
        self._start_window()

    def print(self, *args, sep=' ', end='\n'):
        """Print on Window Terminal"""
        print_text = sep.join(str(a) for a in args) + end
        self._send_command('print', print_text)
    
    def input(self, input_text, input_callback=None):
        """Input on Window Terminal
        
        Parameters:
            input_text (str): Prompt text.
            input_callback (function): Callback function that it will be
            called when input in Window Terminal return. If input_callback
            is not set, this function it will block current thread. 

        Returns:
            str: Only if input_callback is None.
            None: If a input_callback is not set.

        """
        input_text = str(input_text)
        self._send_command('input', input_text)

        if not input_callback:
            self._wait_input.wait()
            self._wait_input.clear()
            return self._last_result_input
        else:
            self._input_callbacks.append(input_callback)

        return None

    def close(self):
        """Close Window Terminal"""
        self._send_command('close')
        self._close_flag.set()

    def wait_close(self):
        """Block current thread until Window Terminal close"""
        self._wait_close.wait()

    def _set_connection(self, connection):
        self._connection = connection
        self._wait_connection_lock.release()

    def _send_command(self, command, arg=None):
        if self._finished:
            raise RuntimeError('Can\'t execute commands in finished Window')

        with self._wait_connection_lock:
            command_message = json.dumps(
                {'uuid': self._uuid, 'command': command, 'arg': arg}
            )
            message = command_message.encode(WindowTerminal.ENCODING)
            message = b64encode(message) + WindowTerminal.BYTES_MESSAGE_END
            self._connection.send(message)

    def _start_window(self):
        this_script = os.path.abspath(__file__)
        ip, port = self._server_address
        arg = WindowTerminal._process_command['arg']
        shell = WindowTerminal._process_command['shell']
        command = list(arg)
        command[-1] = command[-1].format(f'{this_script} {self._uuid} {ip} {port}')
        subprocess.Popen(command, shell=shell, stdout=subprocess.PIPE)

    def _shutdown(self):
        self._connection = None
        self._finished = True
        self._wait_close.set()

    @staticmethod
    def create_window():
        """Create a new instance of Window Terminal"""
        if WindowTerminal._server_socket is None:
            WindowTerminal._start_server()
        
        server_address = WindowTerminal._server_socket.getsockname()
        window_terminal = WindowTerminal(server_address)
        WindowTerminal._windows[window_terminal.uuid] = window_terminal
        return window_terminal

    @staticmethod
    def _start_server():
        WindowTerminal._server_socket = socket.socket(
            socket.AF_INET, socket.SOCK_STREAM
        )
        WindowTerminal._server_socket.bind((WindowTerminal.BIND_IP, 0))
        WindowTerminal._server_socket.settimeout(
            WindowTerminal.SOCKET_TIMEOUT
        )
        WindowTerminal._server_thread = Thread(
            target=WindowTerminal._listen_server, daemon=True
        )
        WindowTerminal._server_thread.start()

    @staticmethod
    def _listen_server():
        WindowTerminal._server_socket.listen(
            WindowTerminal.MAX_SIMULTANEOUS_WINDOW_START
        )

        while not WindowTerminal._server_shutdown_flag.is_set():
            try:
                connection = WindowTerminal._server_socket.accept()[0]
                connection_thread = Thread(
                    target=WindowTerminal._listen_connection, 
                    args=(connection,), daemon=True
                )
                connection_thread.start()
            except socket.timeout:
                continue

    @staticmethod
    def _listen_connection(connection):
        uuid_message = connection.recv(WindowTerminal.BUFFER_SIZE)
        uuid_ = uuid_message.decode(WindowTerminal.ENCODING)

        window = WindowTerminal._windows[uuid_]
        window._set_connection(connection)

        while (uuid_message and 
                    not WindowTerminal._server_shutdown_flag.is_set()):
            try:
                message = connection.recv(WindowTerminal.BUFFER_SIZE)

                if not message:
                    break

                if message:
                    message = b64decode(message)
                    message = message.decode(WindowTerminal.ENCODING)
                    window._last_result_input = message
                    window._wait_input.set()
                    if window._input_callbacks:
                        window._input_callbacks.pop()(message)
            
            except ConnectionResetError:
                break
            except socket.timeout:
                continue

        window._shutdown()
        del WindowTerminal._windows[uuid_]

    @staticmethod
    def stop_server():
        """Stop Universal Window Terminal"""
        WindowTerminal._server_shutdown_flag.set()

    @staticmethod
    def reset_server():
        """Reset Universal Window Terminal"""
        WindowTerminal._server_shutdown_flag.clear()


class WindowTerminalClient(Thread):
    def __init__(self, uuid_, ip, port):
        super().__init__(daemon=True)
        self._uuid = uuid_
        self._server_address = ip, int(port)

        self._close_flag = Event()
        
        self._socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._socket.bind((WindowTerminal.BIND_IP, 0))
        self._socket.settimeout(WindowTerminal.SOCKET_TIMEOUT)

        self._commands = {
            'print': self._print_response,
            'input': self._input_response,
            'close': self._close_response 
        }

    def run(self):
        self._socket.connect(self._server_address)
        self._socket.send(self._uuid.encode(WindowTerminal.ENCODING))

        while not self._close_flag.is_set():
            try:
                messages = self._socket.recv(WindowTerminal.BUFFER_SIZE)

                if not messages:
                    self._close_flag.set()
                else:
                    Thread(
                        target=self._recv_handler, 
                        args=(messages,), daemon=True
                    ).start()
                
            except ConnectionResetError:
                self._close_flag.set()
            except socket.timeout:
                continue

        self._socket.close()

    def _recv_handler(self, messages):
        for message in messages.split(WindowTerminal.BYTES_MESSAGE_END):
            if message:
                message = b64decode(message)
                json_message = json.loads(message)
                uuid_ = json_message['uuid']
                if uuid_ == self._uuid:
                    command, arg = json_message['command'], json_message['arg']
                    self._commands[command](arg)

    def _print_response(self, text):
        print(text, sep='', end='')

    def _input_response(self, text):
        response = input(text)
        message = b64encode(response.encode(WindowTerminal.ENCODING))
        self._socket.send(message)

    def _close_response(self, nothing=None):
        self._close_flag.set()

SUPPORTED_PLATFORMS = ('Windows', 'Linux')

assert (platform.system() in SUPPORTED_PLATFORMS), 'Platform not supported'

if platform.system() == 'Windows':
    WindowTerminal._process_command = (
        WindowTerminal.PROCESSES_COMMANDS['window']
    )
elif platform.system() == 'Linux':
    WindowTerminal._process_command = (
        WindowTerminal.PROCESSES_COMMANDS['gnome']
    )

if __name__ == '__main__':
    window_terminal_server = WindowTerminalClient(*sys.argv[1:])
    window_terminal_server.start()
    window_terminal_server.join()