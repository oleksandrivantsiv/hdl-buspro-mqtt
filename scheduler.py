import time
import sched
import threading


class Scheduler:

    def __init__(self):
        self.scheduler = sched.scheduler()

    def schedule_event(self, delay, priority, callback):
        self.scheduler.enter(delay, priority, callback)

    def worker(self):
        try:
            while True:
                self.scheduler.run(False)
                time.sleep(0.05)
        except KeyboardInterrupt:
            pass

    def run(self):
        thread = threading.Thread(target=self.worker)
        thread.start()
        return thread
