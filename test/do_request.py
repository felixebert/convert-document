import requests
import traceback
import time
from requests import RequestException, HTTPError

import os

files = os.listdir("defect/")

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
        print("OK")
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
