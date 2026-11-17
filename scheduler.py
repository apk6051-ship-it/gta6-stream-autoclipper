"""
Automated 2-Hour Interval Scheduler
Runs the Auto-Clipper session every 2 hours starting tomorrow.
If no reliable stream is available, the process exits cleanly until the next interval.
"""

import time
import datetime
import subprocess
import sys
import logging

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [SCHEDULER] %(message)s",
)
logger = logging.getLogger("Scheduler")


def run_clipper_once():
    logger.info("Triggering 2-hour Auto-Clipper session...")
    try:
        # Run src/main.py as a subprocess
        result = subprocess.run([sys.executable, "-m", "src.main"])
        logger.info(f"Session finished with return code {result.returncode}.")
    except Exception as e:
        logger.error(f"Error running session: {e}")


def wait_until_tomorrow():
    now = datetime.datetime.now()
    # Calculate midnight tomorrow (or 00:00:00 next day)
    tomorrow = (now + datetime.timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
    sleep_seconds = (tomorrow - now).total_seconds()
    logger.info(f"Current Time: {now.strftime('%Y-%m-%d %H:%M:%S')}")
    logger.info(f"Target Start: {tomorrow.strftime('%Y-%m-%d %H:%M:%S')}")
    logger.info(f"Sleeping for {sleep_seconds / 3600:.2f} hours until tomorrow...")
    time.sleep(sleep_seconds)


def start_schedule(wait_for_tomorrow: bool = True):
    if wait_for_tomorrow:
        wait_until_tomorrow()

    logger.info("Schedule active: Running every 2 hours.")
    interval_seconds = 2 * 60 * 60  # 2 hours

    while True:
        run_clipper_once()
        logger.info(f"Waiting 2 hours until next stream check at "
                    f"{(datetime.datetime.now() + datetime.timedelta(seconds=interval_seconds)).strftime('%H:%M:%S')}...")
        time.sleep(interval_seconds)


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="GTA 6 2-Hour Clipper Scheduler")
    parser.add_argument(
        "--now",
        action="store_true",
        help="Run immediately instead of waiting until tomorrow (useful for testing)"
    )
    args = parser.parse_args()

    start_schedule(wait_for_tomorrow=not args.now)
