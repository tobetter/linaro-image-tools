import logging


class NullHandler(logging.Handler):
    def emit(self, record):
        pass


h = NullHandler()
logging.getLogger(__name__).addHandler(h)
