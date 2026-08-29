import time


class LatencyTracker:
    def __init__(self):
        self.marks = {}

    def mark(self, label):
        self.marks[label] = time.monotonic()

    def elapsed_ms(self, start_label, end_label):
        if start_label not in self.marks or end_label not in self.marks:
            return None
        return round((self.marks[end_label] - self.marks[start_label]) * 1000)

    def snapshot(self):
        if "user_stopped" not in self.marks:
            return {}

        base = self.marks["user_stopped"]
        result = {}
        for label, t in self.marks.items():
            if label != "user_stopped":
                result[label] = round((t - base) * 1000)
        return result