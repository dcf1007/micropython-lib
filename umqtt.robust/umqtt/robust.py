import utime
#from . import simple
import simple

class MQTTClient(simple.MQTTClient):
    ATTEMPTS=0
    DELAY = 0

    def __init__(self, client_id, server, port=0, user=None, password=None, keepalive=0,
                 ssl=False, ssl_params={}, attempts=10, delay=1):
        super().__init__(client_id, server, port, user, password, keepalive, ssl, ssl_params)
        self.ATTEMPTS = attempts
        self.DELAY = delay

    def with_retry(self, meth, *args, **kwargs):
        i = 0
        while i < self.ATTEMPTS:
            try:
                self.connect(False)
                return meth(*args, **kwargs)
            except OSError as e:
                print("%r" % e)
                i += 1
                utime.sleep(self.DELAY)
        print("time out")

    def publish(self, *args, **kwargs):
        return self.with_retry(super().publish, *args, **kwargs)

    def wait_msg(self, *args, **kwargs):
        return self.with_retry(super().wait_msg, *args, **kwargs)
