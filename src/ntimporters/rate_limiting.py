""" Rate limiting proxy """
import datetime
from time import sleep


class RLProxy:
    """Proxy class with rate limiting"""

    def __init__(self, proxied_object, window=15 * 60, num_requests=450):
        """Window - timeframe in seconds , num_requests = max number of wrapped_method calls"""
        now = datetime.datetime.now()
        self._max_rate = num_requests
        self._window = window

        self.num_requests = 0
        self.next_reset_at = now + datetime.timedelta(seconds=self._window)
        self.__proxied = proxied_object

    def __getattr__(self, attr):
        def wrapped_method(*args, **kwargs):
            """Wrapped method with rate limiting"""
            print("C", attr)
            if attr.startswith("get_"):
                # apply rl only to class.get_* methods (as in Todoist SDK)
                self.check_rl()
            result = getattr(self.__proxied, attr)(*args, **kwargs)
            return result

        return wrapped_method

    def reset(self):
        """Reset counters"""
        # print("RESET", self.num_requests)
        now = datetime.datetime.now()
        self.next_reset_at = now + datetime.timedelta(seconds=self._window)
        self.num_requests = 0

    def check_rl(self):
        """Check counters and wait if necessary"""
        if (now := datetime.datetime.now()) >= self.next_reset_at:
            self.reset()
        if self.num_requests >= self._max_rate:
            time_to_sleep = (self.next_reset_at - now).seconds
            sleep(time_to_sleep + 0.1)
            self.reset()
        self.num_requests += 1


# if __name__ == "__main__":
#     t = SomeClass()
#     proxy = RLProxy(t, window=3, num_requests=4)
#     for i in range(30):
#         proxy.get_method()
