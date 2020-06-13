import os
import uno
import time
import shutil
import logging
import subprocess
from threading import Timer
from tempfile import gettempdir
from psutil import process_iter
from com.sun.star.beans import PropertyValue
from com.sun.star.lang import DisposedException
from com.sun.star.lang import IllegalArgumentException
from com.sun.star.connection import NoConnectException

DESKTOP = 'com.sun.star.frame.Desktop'
RESOLVER = 'com.sun.star.bridge.UnoUrlResolver'
CONVERT_DIR = os.path.join(gettempdir(), 'convert')
OUT_FILE = os.path.join(CONVERT_DIR, '/tmp/output.pdf')
INSTANCE_DIR = os.path.join(gettempdir(), 'soffice')
ENV = '"-env:UserInstallation=file:///%s"' % INSTANCE_DIR
CONNECTION = 'socket,host=localhost,port=2002,tcpNoDelay=1;urp;StarOffice.ComponentContext'  # noqa
ACCEPT = '--accept="%s"' % CONNECTION
COMMAND = ['/usr/bin/soffice', ENV, '--nologo', '--headless', '--nocrashreport', '--nodefault', '--norestore', '--nolockcheck', '--invisible', ACCEPT]  # noqa
COMMAND = ' '.join(COMMAND)

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
    """Launch a background instance of LibreOffice and convert documents
    to PDF using it's filters.
    """
    PDF_FILTERS = (
        ('com.sun.star.text.GenericTextDocument', 'writer_pdf_Export'),
        ('com.sun.star.text.WebDocument', 'writer_web_pdf_Export'),
        ('com.sun.star.presentation.PresentationDocument', 'impress_pdf_Export'),  # noqa
        ('com.sun.star.drawing.DrawingDocument', 'draw_pdf_Export'),
    )

    def __init__(self):
        self.alive = False
        self.start()

    def kill(self):
        for proc in process_iter():
            if 'soffice' not in proc.name():
                continue
            log.warn("Killing existing process: %r", proc)
            proc.kill()
            proc.wait()
            time.sleep(2)

    def start(self):
        self.kill()
        flush_path(INSTANCE_DIR)
        log.info('Starting LibreOffice: %s', COMMAND)
        subprocess.Popen(COMMAND, shell=True)
        time.sleep(3)
        self.alive = True

    def prepare(self):
        if not self.alive:
            self.start()
        flush_path(CONVERT_DIR)

    def dispose(self):
        log.error('Disposing of LibreOffice.')
        self.alive = False
        self.kill()

    def terminate(self):
        # This gets executed in its own thread after `timeout` seconds.
        log.error('Document conversion timed out.')
        self.dispose()
        flush_path(CONVERT_DIR)

    def _svc_create(self, ctx, clazz):
        return ctx.ServiceManager.createInstanceWithContext(clazz, ctx)

    def connect(self):
        for attempt in range(10):
            try:
                context = uno.getComponentContext()
                resolver = self._svc_create(context, RESOLVER)
                context = resolver.resolve('uno:%s' % CONNECTION)
                return self._svc_create(context, DESKTOP)
            except NoConnectException:
                log.warning("No connection to LibreOffice (%s)", attempt)
                time.sleep(2)
        raise SystemFailure("No connection to LibreOffice")

    def check_health(self, desktop):
        if desktop is None:
            raise SystemFailure('Cannot connect to LibreOffice.')
        if desktop.getFrames().getCount() != 0:
            raise SystemFailure('LibreOffice has stray frames.')
        if desktop.getTasks() is not None:
            raise SystemFailure('LibreOffice has stray tasks.')

    def convert_file(self, file_name, timeout):
        timer = Timer(timeout, self.terminate)
        timer.start()
        try:
            return self._timed_convert_file(file_name)
        finally:
            timer.cancel()

    def _timed_convert_file(self, file_name):
        desktop = self.connect()
        self.check_health(desktop)
        try:
            url = uno.systemPathToFileUrl(file_name)
            props = self.property_tuple({
                'Hidden': True,
                'MacroExecutionMode': 0,
                'ReadOnly': True,
                'Overwrite': True,
                'OpenNewView': True,
                'StartPresentation': False,
                'RepairPackage': False,
            })
            doc = desktop.loadComponentFromURL(url, '_blank', 0, props)
        except IllegalArgumentException:
            raise ConversionFailure('Cannot open document.')
        except DisposedException:
            raise SystemFailure('Bridge is disposed.')

        if doc is None:
            raise ConversionFailure('Cannot open document.')

        try:
            try:
                doc.ShowChanges = False
            except AttributeError:
                pass

            try:
                doc.refresh()
            except AttributeError:
                pass

            output_url = uno.systemPathToFileUrl(OUT_FILE)
            prop = self.get_output_properties(doc)
            doc.storeToURL(output_url, prop)
            doc.dispose()
            doc.close(True)
            del doc
        except DisposedException:
            raise ConversionFailure('Cannot generate PDF.')

        stat = os.stat(OUT_FILE)
        if stat.st_size == 0 or not os.path.exists(OUT_FILE):
            raise ConversionFailure('Cannot generate PDF.')
        return OUT_FILE

    def get_output_properties(self, doc):
        # https://github.com/unoconv/unoconv/blob/master/doc/filters.adoc
        for (service, pdf) in self.PDF_FILTERS:
            if doc.supportsService(service):
                return self.property_tuple({
                    'FilterName': pdf,
                    'Overwrite': True,
                    'ReduceImageResolution': True,
                    'MaxImageResolution': 300,
                    'SelectPdfVersion': 1,
                })
        raise ConversionFailure('PDF export not supported.')

    def property_tuple(self, propDict):
        properties = []
        for k, v in propDict.items():
            prop = PropertyValue()
            prop.Name = k
            prop.Value = v
            properties.append(prop)
        return tuple(properties)
