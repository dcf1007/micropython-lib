import utime
from . import simple

class MQTTClient(simple.MQTTClient):
    ATTEMPTS=10
    DELAY = 1
    DEBUG = False

    def __init__(self, client_id, server, port=0, user=None, password=None, keepalive=0,
                 ssl=False, ssl_params={}, attempts=10, delay=1):
        super().__init__(client_id, server, port, user, password, keepalive, ssl, ssl_params)
        self.ATTEMPTS = attempts
        self.DELAY = delay

    def delay(self):
        utime.sleep(self.DELAY)

    def log(self, in_reconnect, e):
        if self.DEBUG:
            if in_reconnect:
                print("mqtt reconnect: %r" % e)
            else:
                print("mqtt: %r" % e)

    def reconnect(self):
        i = 0
        while i < self.ATTEMPTS:
            try:
                return self.connect(False)
            except OSError as e:
                self.log(True, e)
                i += 1
                self.delay()

    def publish(self, topic, msg, retain=False, qos=0):
        while 1:
            try:
                return super().publish(topic, msg, retain, qos)
            except OSError as e:
                self.log(False, e)
            self.reconnect()

    def wait_msg(self, blocking=True):
        while 1:
            try:
                return super().wait_msg(blocking)
            except OSError as e:
                self.log(False, e)
            self.reconnect()
