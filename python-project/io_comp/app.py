"""
Calendar scheduler — finds available meeting time slots for a group of people.
"""
import csv
import sys
from dataclasses import dataclass
from datetime import time, timedelta
from pathlib import Path
from typing import List, Optional

# Working day boundaries (minutes from midnight)
_DAY_START = 7 * 60   # 07:00
_DAY_END   = 19 * 60  # 19:00

# Gaps of this many minutes or fewer are treated as transition/travel time
# between tasks (walking time) and are never offered as meeting slots.
# For example, if Alice has a meeting 09:00-09:30 and another 09:40-10:00, the
# 10-minute gap between them is not offered as a slot for a 30-minute meeting
# because 09:40+30=10:10 > 10:00, and the 10-minute gap is not enough for a transition between meetings.
TRANSITION_BUFFER_MINUTES = 10

# Slot enumeration step
_SLOT_STEP = 10

# Default calendar CSV file path (relative to this script)
_DEFAULT_CSV = Path(__file__).parent.parent / "resources" / "calendar.csv"

# a function to convert time to minutes from midnight, and vice versa, for easier calculations
# in the find_available_slots function. i use just mintues from midnight for all calculations, and convert back to time objects only when returning the final slots.
def _minutes(t: time) -> int:
    return t.hour * 60 + t.minute

# the inverse of _minutes, to convert back to time objects when returning the final slots.
# turn back to time objects when returning the final slots.
def _to_time(minutes: int) -> time:
    return time(minutes // 60, minutes % 60)


def _parse_time(s: str) -> time:
    h, m = s.strip().split(":")
    return time(int(h), int(m))

# class definition for Event. each event has a person, subject, start time and end time.
@dataclass
class Event:
    person: str
    subject: str
    start: time
    end: time

    def __post_init__(self):
        if self.start >= self.end:
            raise ValueError(
                f"Event '{self.subject}' for {self.person}: "
                f"start ({self.start}) must be before end ({self.end})"
            )

# class definition for Calendar. it has a method to load events from a csv file, and a method to get events for a specific person.
class Calendar:

    # a dictionary mapping person names to lists of their events.
    # like this {"Alice": [Event(...), Event(...)], "Bob": [Event(...)]}
    # now it easy to get all events for person and find their busy intervals and their slots.
    def __init__(self) -> None:
        self._events: dict = {}  # person -> list[Event]


    @classmethod
    def load_from_csv(cls, path: Path = _DEFAULT_CSV) -> "Calendar":
        """Load calendar events from a CSV file (person, subject, HH:MM, HH:MM)."""
        cal = cls()
        # Opens the file and iterates row by row. Rows with fewer than 4 columns are skipped (e.g. blank lines or headers).
        with open(path, newline="", encoding="utf-8") as f:
            for row in csv.reader(f):
                if len(row) < 4:
                    continue
                event = Event(
                    person=row[0].strip(),
                    subject=row[1].strip(),
                    start=_parse_time(row[2]),
                    end=_parse_time(row[3]),
                )
                # ensures the person has a list in the dict (if there is no event for the person it creates a list for them) and then appends the event to that person's list of events.
                cal._events.setdefault(event.person, []).append(event)
        return cal

    def get_events(self, person: str) -> list:
        """Return events for a person sorted by start time."""
        return sorted(self._events.get(person, []), key=lambda e: e.start)

# function to find available slots for a meeting that fits all listed people. it takes a list of people, the duration of the desired meeting, and an optional calendar to query (if not provided, it loads from the default CSV). it returns a sorted list of valid meeting start times within the working day.
def _merge_intervals(intervals: list) -> list:
    """Sort and merge overlapping/adjacent (start, end) integer intervals."""
    if not intervals:
        return []
    result = [list(sorted(intervals)[0])]
    for start, end in sorted(intervals)[1:]:
        if start <= result[-1][1]:
            result[-1][1] = max(result[-1][1], end)
        else:
            result.append([start, end])
    return [tuple(iv) for iv in result]

#this is the main function that ueses all functions above and find the slots between the tasks for some pesron or people.
def find_available_slots(
    # create the variable for the function that takes a list of people, the duration of the desired meeting, and an optional calendar to query (if not provided, it loads from the default CSV). it returns a sorted list of valid meeting start times within the working day.
    person_list: List[str],
    event_duration: timedelta,
    calendar: Optional[Calendar] = None,
) -> List[time]:
    """
    Find all available start times for a meeting that fits all listed people.

    Gaps of <= TRANSITION_BUFFER_MINUTES between tasks are treated as walking/
    transition time and are not offered as schedulable slots.

    Args:
        person_list: Names of people who must all attend.
        event_duration: Duration of the desired meeting.
        calendar: Calendar to query. Loads from default CSV if not provided.

    Returns:
        Sorted list of valid meeting start times within the working day.
    """
    # if the calendar is not provided, it loads from the default CSV file using the Calendar.load_from_csv() method.
    if calendar is None:
        calendar = Calendar.load_from_csv()

    duration_min = int(event_duration.total_seconds() // 60)

    # Collect every busy interval across all requested people
    busy = [
        (_minutes(event.start), _minutes(event.end))
        for person in person_list
        for event in calendar.get_events(person)
    ]
    merged_busy = _merge_intervals(busy)

    # Derive free gaps within the working day
    free_gaps = []
    # the time of _DAY_START is in minutes.
    cursor = _DAY_START
    for b_start, b_end in merged_busy:
        if b_start > cursor:
            free_gaps.append((cursor, b_start))
        cursor = max(cursor, b_end)
    if cursor < _DAY_END:
        free_gaps.append((cursor, _DAY_END))

    slots: List[tuple] = []
    for gap_start, gap_end in free_gaps:
        # Skip gaps that are too short for the requested meeting
        if gap_end - gap_start < duration_min:
            continue
        slots.append((_to_time(gap_start), _to_time(gap_end)))

    return slots

# the main function that run in the terminal and print the available slots. it uses the find_available_slots function to find the slots between the people and print them in the terminal. it also handles the case when there are no available slots found.
def main():
    calendar = Calendar.load_from_csv()
    #people = ["Alice", "Jack", "Bob"]
    people = sorted(calendar._events.keys)
    # the default time for slot is one hour. the user can change it.
    duration = timedelta(hours=1)
    # find the slots for the people and the duration using the find_available_slots function. it returns a list of tuples with the start and end time of the slots.
    slots = find_available_slots(people, duration, calendar)
    print(f"Available 60-minute slots for {', '.join(people)}:")
    # if there is any slot found, it prints the start and end time of the slots in the terminal. if there is no slot found, it prints a message saying that no available slots found.
    if slots:
        for s, e in slots:
            print(f"  {s.strftime('%H:%M')} - {e.strftime('%H:%M')}")
    else:
        print("  No available slots found.")
    sys.exit(0)

# the main function is called when the script is run directly. it runs the main function and exits with code 0.
if __name__ == "__main__":
    main()
