#!/usr/bin/env python3

"""
Generate related synthetic health datasets.

Outputs:
    samples/activity.csv
    samples/sleep.csv
    samples/heart_rate.csv

All datasets share:
    - the same synthetic users
    - the same date range
    - a deterministic random seed

Behavioral phases:
    Days 1-30:
        Normal behavior

    Days 31-37:
        Sleep decreases

    Days 38-45:
        Activity decreases

    Days 46-50:
        Resting heart rate increases

Usage:
    python generate_synthetic_data.py
    python generate_synthetic_data.py 100
    python generate_synthetic_data.py 100 --seed 123
"""

import argparse
import csv
import random
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from pathlib import Path


SCRIPT_DIR = Path(__file__).resolve().parent
OUTPUT_DIR = SCRIPT_DIR / "samples"

DEFAULT_NUM_DAYS = 50
DEFAULT_SEED = 42
NUM_USERS = 4

ACTIVITY_FILE = OUTPUT_DIR / "activity.csv"
SLEEP_FILE = OUTPUT_DIR / "sleep.csv"
HEART_RATE_FILE = OUTPUT_DIR / "heart_rate.csv"


ACTIVITY_FIELDS = [
    "user_id",
    "date",
    "steps",
    "active_minutes",
    "calories_burned",
    "resting_hr",
]

SLEEP_FIELDS = [
    "user_id",
    "date",
    "sleep_start",
    "sleep_end",
    "sleep_duration_hours",
    "deep_sleep_hours",
    "light_sleep_hours",
    "rem_sleep_hours",
    "awake_hours",
    "awakenings",
]

HEART_RATE_FIELDS = [
    "user_id",
    "timestamp",
    "heart_rate_bpm",
    "activity_state",
    "source",
]


@dataclass
class UserProfile:
    """Baseline characteristics for one synthetic user."""

    user_id: str
    base_steps: int
    base_sleep_hours: float
    base_resting_hr: int
    base_calories: int
    sleep_variability: float
    hr_variability: float


@dataclass
class DayContext:
    """Shared behavioral state for a user on a particular day."""

    steps_factor: float
    sleep_factor: float
    resting_hr_adjustment: float


def generate_users(rng: random.Random, num_users: int = NUM_USERS) -> list[UserProfile]:
    """Generate synthetic users with different baseline characteristics."""

    users = []

    for index in range(1, num_users + 1):
        profile = UserProfile(
            user_id=f"demo_user_{index:03d}",
            base_steps=rng.randint(7000, 10500),
            base_sleep_hours=rng.uniform(7.0, 8.0),
            base_resting_hr=rng.randint(58, 66),
            base_calories=rng.randint(2050, 2350),
            sleep_variability=rng.uniform(0.12, 0.25),
            hr_variability=rng.uniform(1.5, 3.0),
        )
        users.append(profile)

    return users


def get_day_context(day_number: int) -> DayContext:
    """
    Return the shared behavioral state for a particular day.

    Day numbers are 1-based.
    """

    # Days 1-30: normal behavior.
    if day_number <= 30:
        return DayContext(
            steps_factor=1.0,
            sleep_factor=1.0,
            resting_hr_adjustment=0.0,
        )

    # Days 31-37: sleep gradually decreases.
    if day_number <= 37:
        progress = (day_number - 31) / 6
        return DayContext(
            steps_factor=1.0,
            sleep_factor=1.0 - (0.55 * progress),
            resting_hr_adjustment=0.0,
        )

    # Days 38-45: activity gradually decreases.
    if day_number <= 45:
        progress = (day_number - 38) / 7
        return DayContext(
            steps_factor=1.0 - (0.40 * progress),
            sleep_factor=0.73,
            resting_hr_adjustment=0.0,
        )

    # Days 46-50: resting heart rate increases.
    progress = (day_number - 46) / 4
    return DayContext(
        steps_factor=0.60,
        sleep_factor=0.73,
        resting_hr_adjustment=5.0 * progress,
    )


def generate_activity_row(
    user: UserProfile,
    current_date: date,
    context: DayContext,
    rng: random.Random,
) -> dict:
    """Generate one activity row."""

    # Day-to-day variation around the behavioral baseline.
    steps = int(
        user.base_steps
        * context.steps_factor
        * rng.uniform(0.82, 1.18)
    )

    # Small occasional unusual day.
    if rng.random() < 0.025:
        steps = int(steps * rng.uniform(0.55, 0.75))

    steps = max(2500, steps)

    active_minutes = int(
        steps / rng.uniform(120, 145)
        + rng.gauss(0, 4)
    )
    active_minutes = max(15, active_minutes)

    calories_burned = int(
        user.base_calories
        + (steps - user.base_steps) * 0.035
        + rng.gauss(0, 45)
    )
    calories_burned = max(1600, calories_burned)

    resting_hr = int(
        round(
            user.base_resting_hr
            + context.resting_hr_adjustment
            + rng.gauss(0, 1.5)
        )
    )

    resting_hr = max(45, min(90, resting_hr))

    return {
        "user_id": user.user_id,
        "date": current_date.isoformat(),
        "steps": steps,
        "active_minutes": active_minutes,
        "calories_burned": calories_burned,
        "resting_hr": resting_hr,
    }


def generate_sleep_row(
    user: UserProfile,
    current_date: date,
    context: DayContext,
    rng: random.Random,
) -> dict:
    """Generate one sleep-session row."""

    # Start with the user's normal sleep duration.
    duration = (
        user.base_sleep_hours
        * context.sleep_factor
        + rng.gauss(0, user.sleep_variability)
    )

    # Keep values within a plausible range.
    duration = max(5.0, min(9.0, duration))

    # Sleep architecture.
    deep_ratio = rng.uniform(0.15, 0.23)
    rem_ratio = rng.uniform(0.18, 0.27)

    deep_sleep = duration * deep_ratio
    rem_sleep = duration * rem_ratio

    # Awake time is separate from actual sleep duration.
    awake_hours = rng.uniform(0.10, 0.35)

    # Light sleep fills the remainder.
    light_sleep = duration - deep_sleep - rem_sleep
    light_sleep = max(0.5, light_sleep)

    # Round components while keeping the total approximately consistent.
    deep_sleep = round(deep_sleep, 2)
    rem_sleep = round(rem_sleep, 2)
    light_sleep = round(light_sleep, 2)
    awake_hours = round(awake_hours, 2)
    duration = round(deep_sleep + light_sleep + rem_sleep, 2)

    awakenings = max(
        0,
        int(round(awake_hours * rng.uniform(3.0, 5.5) + rng.gauss(0, 0.5))),
    )

    # Bedtime varies around 10:30 PM.
    bedtime_minutes = int(rng.gauss(22 * 60 + 30, 35))

    # Normalize bedtime to the same evening.
    bedtime_minutes %= 24 * 60

    sleep_start_date = current_date - timedelta(days=1)

    sleep_start = datetime.combine(
        sleep_start_date,
        time(0, 0),
    ) + timedelta(minutes=bedtime_minutes)

    # Awake time is part of the sleep window, so add it to the duration.
    sleep_window_hours = duration + awake_hours

    sleep_end = sleep_start + timedelta(hours=sleep_window_hours)

    return {
        "user_id": user.user_id,
        "date": current_date.isoformat(),
        "sleep_start": sleep_start.isoformat(timespec="seconds"),
        "sleep_end": sleep_end.isoformat(timespec="seconds"),
        "sleep_duration_hours": duration,
        "deep_sleep_hours": deep_sleep,
        "light_sleep_hours": light_sleep,
        "rem_sleep_hours": rem_sleep,
        "awake_hours": awake_hours,
        "awakenings": awakenings,
    }


def choose_activity_state(
    hour: int,
    rng: random.Random,
) -> str:
    """Choose an activity state based on time of day."""

    # Nighttime is overwhelmingly sedentary/asleep.
    if hour < 7:
        return rng.choices(
            ["sleeping", "sedentary"],
            weights=[90, 10],
            k=1,
        )[0]

    # Morning.
    if hour < 10:
        return rng.choices(
            ["sedentary", "walking", "active"],
            weights=[45, 45, 10],
            k=1,
        )[0]

    # Daytime.
    if hour < 18:
        return rng.choices(
            ["sedentary", "walking", "active"],
            weights=[55, 35, 10],
            k=1,
        )[0]

    # Evening.
    return rng.choices(
        ["sedentary", "walking", "active"],
        weights=[65, 30, 5],
        k=1,
    )[0]


def activity_hr_offset(activity_state: str) -> float:
    """Return the expected HR increase for an activity state."""

    offsets = {
        "sleeping": -8,
        "sedentary": 0,
        "walking": 18,
        "active": 42,
    }

    return offsets[activity_state]


def generate_heart_rate_rows(
    user: UserProfile,
    current_date: date,
    context: DayContext,
    rng: random.Random,
) -> list[dict]:
    """
    Generate multiple heart-rate observations for one user/day.

    This intentionally has a different grain from the activity and sleep
    datasets.
    """

    rows = []

    # Roughly every 30 minutes, with some missing measurements.
    for hour in range(24):
        for minute in (0, 30):
            # Controlled missingness.
            if rng.random() < 0.035:
                continue

            timestamp = datetime.combine(
                current_date,
                time(hour, minute),
            )

            state = choose_activity_state(hour, rng)

            resting_component = (
                user.base_resting_hr
                + context.resting_hr_adjustment
            )

            heart_rate = (
                resting_component
                + activity_hr_offset(state)
                + rng.gauss(0, user.hr_variability)
            )

            # A few plausible sensor anomalies.
            if rng.random() < 0.008:
                heart_rate += rng.choice(
                    [
                        rng.uniform(-12, -7),
                        rng.uniform(12, 20),
                    ]
                )

            heart_rate = int(round(heart_rate))

            # Avoid impossible-looking values.
            heart_rate = max(42, min(185, heart_rate))

            # Different source/device identifiers per user.
            source = rng.choices(
                ["watch", "phone", "chest_strap"],
                weights=[70, 25, 5],
                k=1,
            )[0]

            rows.append(
                {
                    "user_id": user.user_id,
                    "timestamp": timestamp.isoformat(timespec="seconds"),
                    "heart_rate_bpm": heart_rate,
                    "activity_state": state,
                    "source": source,
                }
            )

    return rows


def write_csv(
    output_file: Path,
    fieldnames: list[str],
    rows: list[dict],
) -> None:
    """Write dictionaries to a CSV file."""

    output_file.parent.mkdir(parents=True, exist_ok=True)

    with open(
        output_file,
        "w",
        newline="",
        encoding="utf-8",
    ) as csvfile:
        writer = csv.DictWriter(
            csvfile,
            fieldnames=fieldnames,
        )
        writer.writeheader()
        writer.writerows(rows)


def generate_data(
    num_days: int = DEFAULT_NUM_DAYS,
    seed: int = DEFAULT_SEED,
) -> None:
    """Generate all related synthetic datasets."""

    if num_days < 1:
        raise ValueError("Number of days must be at least 1.")

    if num_days < 50:
        print(
            "Warning: fewer than 50 days means some behavioral phases "
            "will not be included."
        )

    rng = random.Random(seed)

    users = generate_users(rng)

    activity_rows = []
    sleep_rows = []
    heart_rate_rows = []

    start_date = date(2026, 8, 1)

    for user in users:
        for day_index in range(num_days):
            current_date = start_date + timedelta(days=day_index)

            # 1-based day number.
            day_number = day_index + 1

            context = get_day_context(day_number)

            activity_rows.append(
                generate_activity_row(
                    user,
                    current_date,
                    context,
                    rng,
                )
            )

            sleep_rows.append(
                generate_sleep_row(
                    user,
                    current_date,
                    context,
                    rng,
                )
            )

            heart_rate_rows.extend(
                generate_heart_rate_rows(
                    user,
                    current_date,
                    context,
                    rng,
                )
            )

    write_csv(
        ACTIVITY_FILE,
        ACTIVITY_FIELDS,
        activity_rows,
    )

    write_csv(
        SLEEP_FILE,
        SLEEP_FIELDS,
        sleep_rows,
    )

    write_csv(
        HEART_RATE_FILE,
        HEART_RATE_FIELDS,
        heart_rate_rows,
    )

    print(f"Generated {len(users)} synthetic users.")
    print(f"Generated {len(activity_rows)} activity rows.")
    print(f"Generated {len(sleep_rows)} sleep rows.")
    print(f"Generated {len(heart_rate_rows)} heart-rate rows.")
    print()
    print(f"Activity:    {ACTIVITY_FILE}")
    print(f"Sleep:       {SLEEP_FILE}")
    print(f"Heart rate:  {HEART_RATE_FILE}")
    print()
    print(f"Random seed: {seed}")


def parse_args() -> argparse.Namespace:
    """Parse command-line arguments."""

    parser = argparse.ArgumentParser(
        description="Generate related synthetic health datasets."
    )

    parser.add_argument(
        "num_days",
        nargs="?",
        type=int,
        default=DEFAULT_NUM_DAYS,
        help="Number of days to generate (default: 50).",
    )

    parser.add_argument(
        "--seed",
        type=int,
        default=DEFAULT_SEED,
        help=f"Random seed (default: {DEFAULT_SEED}).",
    )

    return parser.parse_args()


def main() -> None:
    args = parse_args()

    try:
        generate_data(
            num_days=args.num_days,
            seed=args.seed,
        )
    except ValueError as exc:
        print(f"Error: {exc}")
        raise SystemExit(1)


if __name__ == "__main__":
    main()
