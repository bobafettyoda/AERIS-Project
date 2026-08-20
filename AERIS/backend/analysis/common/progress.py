from __future__ import annotations

import time


class StageReporter:
    def __init__(self, total_stages: int) -> None:
        self.total_stages = total_stages
        self.started_at = time.monotonic()

    def stage(self, number: int, message: str) -> None:
        elapsed = time.monotonic() - self.started_at
        print(
            f"[{number}/{self.total_stages}] {message} | elapsed {elapsed:,.1f}s",
            flush=True,
        )

    @staticmethod
    def detail(message: str) -> None:
        print(f"      {message}", flush=True)
