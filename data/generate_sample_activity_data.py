#!/usr/bin/env python3

import csv
import random
import sys
from datetime import date, timedelta
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
OUTPUT_FILE = SCRIPT_DIR / "samples" / "activity.csv"

FIELDNAMES = [
    "user_id",
    "date",
    "steps",
    "active_minutes",
    "calories_burned",
    "resting_hr",
]


def generate_row(user_id: str, current_date: date) -> dict:
    """Generate one realistic-looking health data row."""

    steps = random.randint(4500, 12500)
    active_minutes = max(20, int(steps / random.uniform(120, 145)))
    calories_burned = random.randint(1950, 2450)
    resting_hr = random.randint(58, 66)

    return {
        "user_id": user_id,
        "date": current_date.isoformat(),
        "steps": steps,
        "active_minutes": active_minutes,
        "calories_burned": calories_burned,
        "resting_hr": resting_hr,
    }


def generate_data(num_lines: int, output_file: Path = OUTPUT_FILE) -> None:
    """Generate num_lines of sample data and write them to a CSV file."""

    if num_lines < 1:
        raise ValueError("Number of lines must be at least 1.")

    user_id = "demo_user_001"
    start_date = date(2026, 8, 1)

    # Create the samples directory if it doesn't exist.
    output_file.parent.mkdir(parents=True, exist_ok=True)

    with open(output_file, "w", newline="", encoding="utf-8") as csvfile:
        writer = csv.DictWriter(csvfile, fieldnames=FIELDNAMES)
        writer.writeheader()

        for i in range(num_lines):
            current_date = start_date + timedelta(days=i)
            row = generate_row(user_id, current_date)
            writer.writerow(row)

    print(f"Generated {num_lines} data lines.")
    print(f"Output: {output_file}")


def main() -> None:
    if len(sys.argv) != 2:
        print(f"Usage: python {sys.argv[0]} <number_of_lines>")
        print(f"Example: python {sys.argv[0]} 100")
        sys.exit(1)

    try:
        num_lines = int(sys.argv[1])
    except ValueError:
        print("Error: number_of_lines must be an integer.")
        sys.exit(1)

    try:
        generate_data(num_lines)
    except ValueError as exc:
        print(f"Error: {exc}")
        sys.exit(1)


if __name__ == "__main__":
    main()

# Usage: python generate_sample_data.py <number_of_lines>