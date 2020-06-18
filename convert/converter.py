import os
import time
import shutil
import logging
import subprocess
from tempfile import gettempdir
from psutil import process_iter

CONVERT_DIR = os.path.join(gettempdir(), 'convert')
OUT_DIR = os.path.join(CONVERT_DIR, '/tmp/out/')
INSTANCE_DIR = os.path.join(gettempdir(), 'soffice')
ENV = '"-env:UserInstallation=file:///%s"' % INSTANCE_DIR
COMMAND = ['/usr/bin/libreoffice', ENV, '--nologo', '--headless', '--nocrashreport', '--nodefault', '--norestore', '--nolockcheck', '--invisible', '--convert-to', 'pdf', '--outdir', OUT_DIR]  # noqa

log = logging.getLogger(__name__)


def flush_path(path):
    if os.path.exists(path):
        shutil.rmtree(path)
    os.makedirs(path)


class ConversionFailure(Exception):
    # A failure related to the content or structure of the document
    # given, which is expected to re-occur with consecutive attempts
    # to process the document.
    pass


class SystemFailure(Exception):
    # A failure of the service that lead to a failed conversion of
    # the document which may or may not re-occur when the document
    # is processed again.
    pass


class Converter(object):
    def kill(self):
        for proc in process_iter():
            if 'office' not in proc.name():
                continue
            log.warn("Killing existing process: %r", proc)
            proc.kill()
            proc.wait()
            time.sleep(2)

    def prepare(self):
        flush_path(CONVERT_DIR)
        flush_path(OUT_DIR)

    def dispose(self):
        log.error('Disposing of LibreOffice.')
        self.kill()

    def terminate(self):
        # This gets executed in its own thread after `timeout` seconds.
        log.error('Document conversion failed.')
        self.dispose()
        self.prepare()

    def convert_file(self, file_name, timeout):
        try:
            flush_path(INSTANCE_DIR)
            flush_path(OUT_DIR)
            self.kill()
            cmd = COMMAND.copy()
            cmd.append(file_name)
            log.info('Starting LibreOffice: %s', cmd)
            subprocess.run(cmd, timeout=60) # TODO variable timeout

            files = os.listdir(OUT_DIR)
            pdf_files = list(filter(lambda f: f.endswith('.pdf'), files))
            if len(pdf_files) <= 0:
                raise ConversionFailure('Cannot generate PDF.')

            out_file = os.path.join(OUT_DIR, pdf_files[0])
            stat = os.stat(out_file)
            if stat.st_size == 0 or not os.path.exists(out_file):
                raise ConversionFailure('Cannot generate PDF.')
            return out_file
        except Exception as e:
            self.terminate()
            raise ConversionFailure('Cannot generate PDF.', e)
