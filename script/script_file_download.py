
from web_server import asyncio, send, send_http_ok, send_http_end_of_header

ENCODING = 'utf-8'
WAIT_FOR_PIECES_FROM_UPLOADER_SLEEP = 0.06

SEND_RESPONSE_TIMEOUT = 2

SEND_CHUNK_TIMEOUT = 1

async def _page_file_download(con, shared):
    file_name = shared.file_name
    if '"' in file_name:
        print('ERROR: bad char in file name')
        file_name = file_name.replace('"', '_')
    
    print(f'staring download of file `{file_name}`')
    
    await send_http_ok(con)
    await send(con, f'Content-disposition: attachment; filename="{file_name}"\n'.encode(ENCODING), SEND_RESPONSE_TIMEOUT)
    await send_http_end_of_header(con)
    
    while shared.file_upload_is_being_requested:
        if len(shared.file_content) > 0:
            while len(shared.file_content) > 0:
                data = shared.file_content.pop(0)
                await send(con, data, SEND_CHUNK_TIMEOUT)
        else:
            await asyncio.sleep(WAIT_FOR_PIECES_FROM_UPLOADER_SLEEP)

async def page_file_download(con, shared):
    if not shared.file_upload_is_being_requested:
        await send(con, b'no one is uploading a file', SEND_RESPONSE_TIMEOUT)
        return

    if shared.file_download_in_progress:
        await send(con, b'someone is already downloading', SEND_RESPONSE_TIMEOUT)
        print('someone is already downloading')
        return

    #print('well do a download')

    shared.file_download_in_progress = True
    try:
        await _page_file_download(con, shared)
    finally:
        shared.file_download_in_progress = False

async def main(share, con):
    try:
        share.ft
    except AttributeError:
        await send(con, b'file upload not initialized; someone needs to upload a file', SEND_RESPONSE_TIMEOUT)

    await page_file_download(con, share.ft)
