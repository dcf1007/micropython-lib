import usocket as socket
import utime

class MQTTException(Exception):
    pass

class MQTTClient:

    def __init__(self, client_id, server, port=0, user=None, password=None, keepalive=0,
                 ssl=False, ssl_params={}):
        if port == 0:
            port = 8883 if ssl else 1883
        self.client_id = client_id
        self.sock = None
        self.server = server
        self.port = port
        self.ssl = ssl
        self.ssl_params = ssl_params
        self.pid = 0
        self.cb = None
        self.user = user
        self.pswd = password
        self.keepalive = keepalive
        self.lw_topic = None
        self.lw_msg = None
        self.lw_qos = 0
        self.lw_retain = False

    def _send_str(self, s):
        assert len(s) < 65536
        self.sock.write(len(s).to_bytes(2, 'big'))
        self.sock.write(s)

    def _recv_len(self):
        n = 0
        sh = 0
        while 1:
            b = self.sock.read(1)[0]
            n |= (b & 0x7f) << sh
            if not b & 0x80:
                return n
            sh += 7

    def _varlen_encode(self, value, buf, offset=0):
        assert value < 268435456  # 2**28, i.e. max. four 7-bit bytes
        while value > 0x7f:
            buf[offset] = (value & 0x7f) | 0x80
            value >>= 7
            offset += 1
        buf[offset] = value
        return offset + 1

    def set_callback(self, f):
        self.cb = f

    def set_last_will(self, topic, msg, retain=False, qos=0):
        assert 0 <= qos <= 2
        assert topic
        self.lw_topic = topic
        self.lw_msg = msg
        self.lw_qos = qos
        self.lw_retain = retain

    def connect(self, clean_session=True):
        self.sock = socket.socket()
        addr = socket.getaddrinfo(self.server, self.port)[0][-1]
        _ = self.sock.connect(addr) #Added dummy variable to avoid print in stdout
        if self.ssl:
            import ussl
            self.sock = ussl.wrap_socket(self.sock, **self.ssl_params)
        premsg = bytearray(b"\x10\0\0\0\0")
        msg = bytearray(b"\0\x04MQTT\x04\0\0\0")

        sz = 10 + 2 + len(self.client_id)
        msg[7] = clean_session << 1
        if self.user is not None:
            sz += 2 + len(self.user)
            msg[7] |= 1 << 7
            if self.pswd is not None:
                sz += 2 + len(self.pswd)
                msg[7] |= 1 << 6
        if self.keepalive:
            assert self.keepalive < 65536
            msg[8] |= self.keepalive >> 8
            msg[9] |= self.keepalive & 0x00FF
        if self.lw_topic:
            sz += 2 + len(self.lw_topic) + 2 + len(self.lw_msg)
            msg[7] |= 0x4 | (self.lw_qos & 0x1) << 3 | (self.lw_qos & 0x2) << 3
            msg[7] |= self.lw_retain << 5

        plen = self._varlen_encode(sz, premsg, 1)
        self.sock.write(premsg, plen)
        self.sock.write(msg)
        self._send_str(self.client_id)
        if self.lw_topic:
            self._send_str(self.lw_topic)
            self._send_str(self.lw_msg)
        if self.user is not None:
            self._send_str(self.user)
            if self.pswd is not None:
                self._send_str(self.pswd)
        resp = self.sock.read(4)
        assert resp[0] == 0x20 and resp[1] == 0x02
        if resp[3] != 0:
            raise MQTTException(resp[3])
        return resp[2] & 1

    def disconnect(self):
        self.sock.write(b"\xe0\0")
        self.sock.close()

    def ping(self):
        #Make sure the connection buffer is empty.
        prev_msg = self.check_msg()
        while prev_msg != None:
            prev_msg = self.check_msg()

        #Send PINGREQ
        self.sock.write(b"\xc0\x00")
        print("PINGREQ", end="")
        
        #Check the response
        i=0
        while i < 10:
            utime.sleep(0.1)
            print(".", end = "")
            res = self.check_msg()
            if res ==  b"\xd0\x00": # PINGRESP
                print("PINGRESP OK")
                return None
            else:
                i += 1
        else:
            print("Error")
            raise OSError("Connection timed out")

    def publish(self, topic, msg, retain=False, qos=0):
        pkt = bytearray(b"\x30\0\0\0\0")
        pkt[0] |= qos << 1 | retain
        sz = 2 + len(topic) + len(msg)
        if qos > 0:
            sz += 2
        plen = self._varlen_encode(sz, pkt, 1)
        self.sock.write(pkt, plen)
        self._send_str(topic)
        if qos > 0:
            self.pid += 1
            pid = self.pid
            self.sock.write(pid.to_bytes(2, 'big'))
        self.sock.write(msg)
        if qos == 1:
            while 1:
                op = self.wait_msg()
                if op == 0x40:
                    sz = self.sock.read(1)
                    assert sz == b"\x02"
                    rcv_pid = int.from_bytes(self.sock.read(2), 'big')
                    if pid == rcv_pid:
                        return
        elif qos == 2:
            assert 0

    def subscribe(self, topic, qos=0):
        assert self.cb is not None, "Subscribe callback is not set"
        pkt = bytearray(b"\x82\0\0\0\0\0\0")
        self.pid += 1
        sz = 2 + 2 + len(topic) + 1
        plen = self._varlen_encode(sz, pkt, 1)
        pkt[plen:plen + 2] = self.pid.to_bytes(2, 'big')
        self.sock.write(pkt, plen + 2)
        self._send_str(topic)
        self.sock.write(qos.to_bytes(1, "little"))
        while 1:
            op = self.wait_msg()
            if op == 0x90:
                resp = self.sock.read(4)
                assert resp[1] == pkt[plen] and resp[2] == pkt[plen + 1]
                if resp[3] == 0x80:
                    raise MQTTException(resp[3])
                return

    # Wait for a single incoming MQTT message and process it.
    # Subscribed messages are delivered to a callback previously
    # set by .set_callback() method. Other (internal) MQTT
    # messages processed internally.
    def wait_msg(self, blocking=True):
        self.sock.setblocking(blocking)
        res = self.sock.read(1)
        self.sock.setblocking(True)
        if res is None:
            return None
        if res == b"":
            raise OSError(-1)
        if res == b"\xd0":  # PINGRESP
            sz = self.sock.read(1)[0]
            assert sz == 0
            return b"\xd0\x00" #Return PINGRESP value instead of None to differentiate between no contents and ping response.
        op = res[0]
        if op & 0xf0 != 0x30:
            return op & 0xf0
        sz = self._recv_len()
        topic_len = int.from_bytes(self.sock.read(2), 'big')
        topic = self.sock.read(topic_len)
        sz -= topic_len + 2
        if op & 6:
            pid = int.from_bytes(self.sock.read(2), 'big')
            sz -= 2
        msg = self.sock.read(sz)
        self.cb(topic, msg)
        if op & 6 == 2:
            self.sock.write(b"\x40\x02")
            self.sock.write(pid.to_bytes(2, 'big'))
        elif op & 6 == 4:
            assert 0

    # Checks whether a pending message from server is available.
    # If not, returns immediately with None. Otherwise, does
    # the same processing as wait_msg.
    def check_msg(self):
        return self.wait_msg(False)
