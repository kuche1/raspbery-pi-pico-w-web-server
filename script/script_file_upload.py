
from web_server import recv_header_line, asyncio, MaliciousClientError

RECV_FILE_ID_TIMEOUT = 1
RECV_RANDOM_HEADER_LINE_TIMEOUT = 1
WAIT_FOR_FILE_DOWNLOAD_TO_START_SLEEP = 0.4
FILE_UPLOAD_CHUNK = 1024 * 4
FILE_UPLOAD_MAX_CHUNKS = 5
SHARED_DATA_FILE_CONTENT_MAX_LEN = 7

ENCODING = 'utf-8'

RECEIVE_FILE_CHUNK_SLEEP = 0.06
MAX_TIME_BETWEEN_CHUNK_RECEIVE = 1

class File_transfer:
    file_upload_is_being_requested = False
    file_download_in_progress = False
    file_name = 'ERROR'
    file_content = []

async def _page_file_upload_in_progress(con, share):
    # this sucks but I can't figure out anything else
    # maybe that's why there is a lagre random number here
    # (if this really is the case, then the people who made this are idiots)
    ending = '\r\n' + (await recv_header_line(con, RECV_FILE_ID_TIMEOUT)) + '--\r\n'
    ending = ending.encode(ENCODING)
    
    file_name = None
    while True:
        data = (await recv_header_line(con, RECV_RANDOM_HEADER_LINE_TIMEOUT))
        
        if data.startswith('Content-Disposition:'):
            data = data.split('; ')
            for dat in data:
                tmp = 'filename='
                if dat.startswith(tmp):
                    file_name = dat[len(tmp):]
                    break
        elif len(data) == 0:
            break

    if file_name == None:
        con.sendall(b'ERROR: could not determine file name')
        return
    
    if file_name.startswith('"') and file_name.endswith('"'):
        if len(file_name) >= 2:
            file_name = file_name[1:-1]
    
    share.ft.file_name = file_name
    
    while not share.ft.file_download_in_progress:
        # TODO what is the user disconnects?
        # perhaps add a timer
        #print('waiting for file download to start...')
        await asyncio.sleep(WAIT_FOR_FILE_DOWNLOAD_TO_START_SLEEP)
    print('file download started')
    
    data = [b''] * FILE_UPLOAD_MAX_CHUNKS
    last_chunk_received = time.time()
    while True:
        if time.time() - last_chunk_received > MAX_TIME_BETWEEN_CHUNK_RECEIVE:
            raise MaliciousClientError('slow upload')

        try:
            chunk = con.recv(FILE_UPLOAD_CHUNK)
        except NetworkBlockingError:
            await asyncio.sleep(RECEIVE_FILE_CHUNK_SLEEP)
            continue
        print('received chunk')
        
        data.append(chunk)
        if (data[-2] + data[-1]).endswith(ending):
            del data[-1]
            del data[-1]
            break
        
        while len(share.ft.file_content) >= SHARED_DATA_FILE_CONTENT_MAX_LEN:
            # this might cause an infinite loop if the downloader disconnects
            await asyncio.sleep(0.5)
        share.ft.file_content.append(data[0])
        del data[0]
        # this really should be send the data to the sending thread
    
    # this ignores the limits
    while len(data) > 0:
        share.ft.file_content.append(data[0])
        del data[0]
    
    while len(share.ft.file_content) > 0:
        await asyncio.sleep(0.5)
    
    print(f'file uploaded complete')
    con.sendall(b'file upload complete')

async def main(share, con):
    try:
        share.ft
    except AttributeError:
        share.ft = File_transfer()
    
    if share.ft.file_upload_is_being_requested:
        con.sendall('someone is already requesting a file upload')
        return
    
    share.ft.file_upload_is_being_requested = True
    try:
        await _page_file_upload_in_progress(con, share)
    finally:
        share.ft.file_upload_is_being_requested = False
