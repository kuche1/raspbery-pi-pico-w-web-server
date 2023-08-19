#! /usr/bin/env python3

# TODO
#
# ? make header receive timeout hardcoded
#
# ? make the file uploading and downloading into separate functions
#
# make a function for generic 1-line responses
#
# make some sort of admin interface

##########
########## determine platform
##########

import os

RP = os.uname().sysname == 'rp2'

##########
########## imports
##########

import socket
import time
import sys

if RP:
    import machine
    from machine import Pin
    import network
    import uasyncio as asyncio
    import _thread
    led = Pin("LED", Pin.OUT)
else:
    import asyncio
    import threading

##########
########## defines
##########

if RP:
    THIS_FILE_LOCATION = 'web_server'
else:
    THIS_FILE_LOCATION = os.path.dirname(__file__)

PAGE_FOLDER = f'{THIS_FILE_LOCATION}/page'
SCRIPT_FOLDER = f'{THIS_FILE_LOCATION}/script'

WIFI_SSID_FILE = f'{THIS_FILE_LOCATION}/wifi-ssid'
WIFI_PASS_FILE = f'{THIS_FILE_LOCATION}/wifi-pass'

LED_WIFI_CONNECT = 0.7

BIND_PORT = 80 if RP else 8080

SERVING_THREADS = 5

SOCK_ACCEPT_SLEEP = 0.1
RECV_HEADER_BYTE_SLEEP = 0.01
RECV_HEADER_FIRST_LINE_TIMEOUT = 1.2
RECV_REST_OF_HEADER_TIMEOUT = 4

SEND_GENERIC_RESPONSE_MESSAGE_TIMEOUT = 1
SEND_HTTP_HEADER_DATA_TIMEOUT = 1
SEND_SLEEP = 0

FILE_READ_CHUNK = 1024 * 5
FILE_SEND_CHUNK_TIMEOUT = 1

SCRIPT_EXTENSION = 'fnc'

##########
########## classes
##########

class Shared_data: pass

NetworkBlockingError = OSError if RP else BlockingIOError

class MaliciousClientError(Exception): pass

##########
########## functions
##########

######
###### generic

def connect_to_internet():
    if RP:
        with open(WIFI_SSID_FILE, 'r') as f:
            ssid = f.read()
        with open(WIFI_PASS_FILE, 'r') as f:
            password = f.read()

        print(f'trying to connect to wifi `{ssid}`...')
        wlan = network.WLAN(network.STA_IF)
        wlan.active(True)
        wlan.connect(ssid, password)
        while wlan.isconnected() == False:
            led.toggle()
            time.sleep(LED_WIFI_CONNECT)
        print('connected')
        
        ip, subnet, gateway, dns = wlan.ifconfig()
    else:
        # assume we already have internet
        ip = '127.0.0.1'
    
    print(f'assigned ip `{ip}`')

toggle_led = (lambda:led.toggle()) if RP else (lambda:None)

def create_lock():
    if RP:
        return _thread.allocate_lock()
    else:
        return threading.Lock()

def does_file_exist(path):
    if RP:
        try:
            open(path, 'rb')
        except OSError:
            return False
        return True
    else:
        return os.path.isfile(path)

async def send(con, data, timeout):
    start = time.time()
    while data:
        if time.time() - start > timeout:
            raise MaliciousClientError('slow download')

        try:
            sent = con.send(data)
        except BrokenPipeError: # TODO this is probably OSError instead on the raspbery pi
            raise MaliciousClientError('connection dropped by client') # TODO wtf why are we not catching this?

        data = data[sent:]
        await asyncio.sleep(SEND_SLEEP)

######
###### server generic

#### receive

async def recv_header_line(con, timeout, discard=False):
    end = b'\r\n'

    start = time.time()
    data = b''
    while True:
        remain = timeout - (time.time() - start)
        if remain <= 0:
            raise MaliciousClientError('upload too slow')

        try:
            byte = con.recv(1)
        except NetworkBlockingError:
            await asyncio.sleep(RECV_HEADER_BYTE_SLEEP)
            continue

        data += byte
        if data.endswith(end):
            break
        
        if discard and len(data) > 3:
            # leave 1 character so that the caller knows if this was an empty line
            data = data[-3:]

    data = data[:-len(end)]
    data = data.decode()
    return data

#### send

async def send_http_ok(con):
    await send(con, b'HTTP/1.1 200 OK\n', SEND_HTTP_HEADER_DATA_TIMEOUT)

async def send_http_not_found(con):
    await send(con, b'HTTP/1.1 404 Not Found\n', SEND_HTTP_HEADER_DATA_TIMEOUT)

async def send_http_error(con):
    await send(con, b'HTTP/1.1 500 Internal Server Error\n', SEND_HTTP_HEADER_DATA_TIMEOUT) # TODO it is OK to have spaces here?

async def send_http_end_of_header(con):
    await send(con, b'\n', SEND_HTTP_HEADER_DATA_TIMEOUT)

######
###### server specific

async def serve_content_request(con, page):
    if page == '/':
        page = '/index.html'

    file = PAGE_FOLDER + page
    if not does_file_exist(file):
        await send_http_not_found(con)
        await send_http_end_of_header(con)
        await send(con, b'404', SEND_GENERIC_RESPONSE_MESSAGE_TIMEOUT)
        return

    await send_http_ok(con)
    await send_http_end_of_header(con)

    with open(file, 'rb') as f:
        chunk = f.read(FILE_READ_CHUNK)
        await send(con, chunk, FILE_SEND_CHUNK_TIMEOUT)

async def serve_script_request(share, con, page):
    script_name = page
    if script_name.startswith('/'):
        script_name = script_name[1:]

    file = SCRIPT_FOLDER + page + '.py'
    if not does_file_exist(file):
        return

    sys.path.insert(0, SCRIPT_FOLDER) # this seems iffy, but we have already ensured that this file exists, therefore it will be imported
    if RP:
        sys.path.insert(1, THIS_FILE_LOCATION)
    script = __import__(script_name)
    del sys.path[0]
    del sys.path[0]

    try:
        script = script.main
    except AttributeError:
        print(f'ERROR: bad script: {file}')
        return

    await script(share, con)

async def __serve_requests(share, con, addr):

    header = await recv_header_line(con, RECV_HEADER_FIRST_LINE_TIMEOUT)
    if header.count(' ') != 2:
        raise MaliciousClientError('bad header format')
    method, page, proto = header.split(' ')

    start = time.time()
    while True:
        remain = RECV_REST_OF_HEADER_TIMEOUT - (time.time() - start)
        line = await recv_header_line(con, remain, discard=True)
        if not line:
            break

    if '..' in page:
        # TODO not the best solution
        raise MaliciousClientError('cd')

    if not page.startswith('/'):
        page = '/' + page
    
    if method == 'GET':
        await serve_content_request(con, page)
    elif method == 'POST':
        await serve_script_request(share, con, page)
    else:
        raise MaliciousClientError('bad method')

async def _serve_requests(sock, share):
    #print('waiting for connection')
    while True:
        try:
            con, addr = sock.accept()
        except NetworkBlockingError:
            await asyncio.sleep(SOCK_ACCEPT_SLEEP)
        else:
            break
    #print('connection!')
    
    toggle_led()

    try:
        await __serve_requests(share, con, addr)
    finally:
        con.close()

async def serve_requests(sock, share):
    while True:
        try:
            await _serve_requests(sock, share)
        except MaliciousClientError as err:
            print(f'malicious client: {err}')
        except:
            asyncio.create_task(serve_requests(sock, share))
            raise

async def _main(sock):
    #sock = ssl.wrap_socket(
        #sock,
        #keyfile=KEYFILE,
        #certfile=CERTFILE,
        #server_side=True,
        #ssl_version=SSL_VERSION,
        #do_handshake_on_connect=True
    #)

    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)

    print(f'trying to bind to port {BIND_PORT}')
    sock.bind(('', BIND_PORT))
    print('bound')
    sock.listen(1)
    sock.setblocking(False)

    share = Shared_data()

    # hopefully we can save some performance this way...
    assert SERVING_THREADS > 0
    for _ in range(SERVING_THREADS - 1):
        asyncio.create_task(serve_requests(sock, share))
    await serve_requests(sock, share)

def main():
    connect_to_internet()

    sock = socket.socket()

    try:
        asyncio.run(_main(sock))
    except KeyboardInterrupt:
        pass
    
    sock.close()

if __name__ == '__main__':
    main()
