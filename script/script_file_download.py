
from web_server import asyncio

ENCODING = 'utf-8'
WAIT_FOR_PIECES_FROM_UPLOADER_SLEEP = 0.06

async def _page_file_download(con, shared):
    file_name = shared.file_name
    if '"' in file_name:
        print('ERROR: bad char in file name')
        file_name = file_name.replace('"', '_')
    
    print(f'staring download of file `{file_name}`')
    
    con.sendall(f'''HTTP/1.1 200 OK
Content-disposition: attachment; filename="{file_name}"

'''.encode(ENCODING))
    
    while shared.file_upload_is_being_requested:
        while len(shared.file_content) > 0:
            data = shared.file_content.pop(0)
            con.settimeout(None)
            con.sendall(data)
            con.settimeout(0)
        else:
            await asyncio.sleep(WAIT_FOR_PIECES_FROM_UPLOADER_SLEEP)

async def page_file_download(con, shared):
    if not shared.file_upload_is_being_requested:
        con.sendall(b'no one is uploading a file')
        print('no one is uploading a file')
        return

    if shared.file_download_in_progress:
        con.sendall(b'someone is already downloading')
        print('someone is already downloading')
        return

    print('well do a download')

    shared.file_download_in_progress = True
    try:
        await _page_file_download(con, shared)
    finally:
        shared.file_download_in_progress = False

async def main(share, con):
    try:
        share.ft
    except AttributeError:
        con.sendall(b'file upload not initialized; someone needs to upload a file')

    await page_file_download(con, share.ft)
