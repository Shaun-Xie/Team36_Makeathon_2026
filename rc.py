from gpiozero import LED
import asyncio  # or `import asyncio` on CPython
import threading
from time import sleep


LEFT_GPIO = 27
RIGHT_GPIO = 22
FORWARD_GPIO = 17
# 1. Bring in the custom timer class we discussed


class RepeatingTimer(threading.Thread):
    def __init__(self, interval, function):
        super().__init__()
        self.interval = interval
        self.function = function
        self.stop_event = threading.Event()

    def cancel(self):
        self.stop_event.set()

    def run(self):
        while not self.stop_event.wait(self.interval):
            self.function()


class Movement:
    def __init__(self):
        self.left_pin = LED(LEFT_GPIO)
        self.right_pin = LED(RIGHT_GPIO)
        self.forward_pin = LED(FORWARD_GPIO)
        self.forward_timer = None

    def stop(self):
        self.forward_pin.off()
        if self.forward_timer:
            self.forward_timer.cancel()
            self.forward_timer = None
        self.forward_pin.off()


    def forward(self):
        if self.forward_timer is None:
            self._forward()
            self.forward_timer = RepeatingTimer(0.6, self._forward)
            self.forward_timer.start()

    def _forward(self):
        self.forward_pin.on()
        sleep(0.1)
        self.forward_pin.off()

    def left(self):
        self.right_pin.off()
        self.left_pin.on()

    def right(self):
        self.left_pin.off()
        self.right_pin.on()

    def straight(self):
        self.left_pin.off()
        self.right_pin.off()

    def cleanup(self):
        self.stop()
        self.left_pin.close()
        self.right_pin.close()
        self.forward_pin.close()
