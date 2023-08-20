
from web_server import asyncio, send, send_http_ok, send_http_end_of_header, send_http_error

ENCODING = 'utf-8'
WAIT_FOR_PIECES_FROM_UPLOADER_SLEEP = 0.06

SEND_RESPONSE_TIMEOUT = 2

SEND_CHUNK_TIMEOUT = 2

async def _page_file_download(con, share):
    file_name = share.ft.file_name
    if '"' in file_name:
        print('ERROR: bad char in file name')
        file_name = file_name.replace('"', '_')
    
    await send_http_ok(con)
    await send(con, f'Content-disposition: attachment; filename="{file_name}"\n'.encode(ENCODING), SEND_RESPONSE_TIMEOUT)
    await send_http_end_of_header(con)
    
    while share.ft.file_upload_is_being_requested:
        if len(share.ft.file_content) > 0:
            while len(share.ft.file_content) > 0:
                data = share.ft.file_content.pop(0)
                await send(con, data, SEND_CHUNK_TIMEOUT)
        else:
            await asyncio.sleep(WAIT_FOR_PIECES_FROM_UPLOADER_SLEEP)

async def page_file_download(con, share):
    if not share.ft.file_upload_is_being_requested:
        await send_http_error()
        await send_http_end_of_header()
        await send(con, b'no one is uploading a file', SEND_RESPONSE_TIMEOUT)
        return

    if share.ft.file_download_in_progress:
        await send_http_error()
        await send_http_end_of_header()
        await send(con, b'someone is already downloading', SEND_RESPONSE_TIMEOUT)
        print('someone is already downloading')
        return

    #print('well do a download')

    share.ft.file_download_in_progress = True
    try:
        await _page_file_download(con, share)
    finally:
        share.ft.file_download_in_progress = False

async def main(share, con):
    try:
        share.ft
    except AttributeError:
        await send_http_error()
        await send_http_end_of_header()
        await send(con, b'file upload not initialized; someone needs to upload a file', SEND_RESPONSE_TIMEOUT)
        return

    await page_file_download(con, share)
