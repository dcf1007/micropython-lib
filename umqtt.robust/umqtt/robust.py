import utime
#from . import simple
import simple

class MQTTClient(simple.MQTTClient):
    def with_retry(self, meth, *args, attempts = 1, **kwargs):
        i = 0
        while i < attempts:
            try:
                if i > 0:
					utime.sleep(1)
                    print("Trying to reconnect")
                    self.connect(False)
                return meth(*args, **kwargs)
            except OSError as e:
                print("%r" % e)
                i += 1
        print("Error: Time out")

    def publish(self, *args, **kwargs):
        return self.with_retry(super().publish, *args, **kwargs)

    def subscribe(self, *args, **kwargs):
        return self.with_retry(super().subscribe, *args, **kwargs)

    def ping(self, *args, **kwargs):
        return self.with_retry(super().ping, *args, **kwargs)

    def wait_msg(self, *args, **kwargs):
        return self.with_retry(super().wait_msg, *args, **kwargs)
