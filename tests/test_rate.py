import unittest

from kaidrop.rate import RateMeter, describe, duration


class Clock:
    def __init__(self):
        self.now = 0.0

    def __call__(self):
        return self.now


class RateMeterTest(unittest.TestCase):
    def test_speed_over_the_last_seconds(self):
        clock = Clock()
        meter = RateMeter(window=5.0, clock=clock)
        meter.start(100_000_000)
        self.assertIsNone(meter.speed())  # Nothing measured yet.
        for second in range(1, 11):
            clock.now = second
            meter.update(second * 2_000_000)  # 2 MB/s.
        self.assertAlmostEqual(meter.speed(), 2_000_000)
        self.assertAlmostEqual(meter.remaining(), 40.0)  # 80 MB left at 2 MB/s.

    def test_no_speed_from_the_first_burst(self):
        clock = Clock()
        meter = RateMeter(window=5.0, clock=clock)
        meter.start(10_000_000)
        clock.now = 0.01
        meter.update(65_536)  # The first block fills the network buffer at once.
        self.assertIsNone(meter.speed())
        self.assertIsNone(meter.remaining())

    def test_follows_a_change_of_speed(self):
        clock = Clock()
        meter = RateMeter(window=5.0, clock=clock)
        meter.start(1_000_000_000)
        done = 0
        for second in range(1, 21):
            clock.now = second
            done += 10_000_000 if second <= 10 else 1_000_000  # Wi-Fi gets slow.
            meter.update(done)
        self.assertAlmostEqual(meter.speed(), 1_000_000)

    def test_skipped_files_jump_ahead_without_counting_as_speed(self):
        clock = Clock()
        meter = RateMeter(window=5.0, clock=clock)
        meter.start(50_000_000)
        clock.now = 1
        meter.update(1_000_000)
        meter.skip(40_000_000)  # A file already there: done, but not sent.
        clock.now = 2
        meter.update(42_000_000)
        self.assertAlmostEqual(meter.speed(), 1_000_000)
        self.assertAlmostEqual(meter.remaining(), 8.0)


class DescribeTest(unittest.TestCase):
    def test_durations(self):
        self.assertEqual(duration(4), "a few seconds")
        self.assertEqual(duration(42), "42 s")
        self.assertEqual(duration(125), "2 min 5 s")
        self.assertEqual(duration(3 * 3600 + 7 * 60), "3 h 7 min")

    def test_line(self):
        self.assertEqual(describe(12_300_000, 1_200_000_000, 4_100_000, 290),
                         "11.7 MB of 1.1 GB · 3.9 MB/s · 4 min 50 s left")
        self.assertEqual(describe(0, 5_000, None, None), "0 B of 4.9 KB")


if __name__ == "__main__":
    unittest.main()
