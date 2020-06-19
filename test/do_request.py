import requests
import traceback
import time
from requests import RequestException, HTTPError

import os

base_dir = "defect/"
files = os.listdir(base_dir)

def do_request(file_path, file_name):
    fh = open(file_path, 'rb')
    print("convert " + file_name)
    try:
        files = {'file': (file_name, fh, "application/msword")}
        res = requests.post("http://localhost:3000/convert",
                            files=files,
                            timeout=(5, 305),
                            stream=True)
        res.raise_for_status()

        filename_parts = file_name.split(".")
        filename_parts.pop()
        base_filename = ".".join(filename_parts)

        out_path = base_dir + base_filename + ".pdf"
        with open(out_path, 'wb') as fh:
            bytes_written = 0
            for chunk in res.iter_content(chunk_size=None):
                bytes_written += len(chunk)
                fh.write(chunk)
            print("OK")
            if bytes_written > 50:
                return out_path
        raise Exception("Could not be converted to PDF.")
    except RequestException as exc:
        print("Conversion failed")
        traceback.print_tb(exc.__traceback__)
    finally:
        fh.close()


while True:
    for file in files:
        if file.endswith(".doc"):
            do_request("defect/" + file, file)
            time.sleep(5)
