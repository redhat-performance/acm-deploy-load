#!/usr/bin/env python3
#
# Time and timestamp utility functions
#
#  Copyright 2026 Red Hat
#
#  Licensed under the Apache License, Version 2.0 (the "License");
#  you may not use this file except in compliance with the License.
#  You may obtain a copy of the License at
#
#      http://www.apache.org/licenses/LICENSE-2.0
#
#  Unless required by applicable law or agreed to in writing, software
#  distributed under the License is distributed on an "AS IS" BASIS,
#  WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
#  See the License for the specific language governing permissions and
#  limitations under the License.

from datetime import datetime
from datetime import timezone


def parse_ts(ts_value):
  """Parse an RFC 3339 / ISO 8601 timestamp string into a naive UTC datetime object.

  Kubernetes metadata timestamps are second granularity UTC ("%Y-%m-%dT%H:%M:%SZ"), which is the
  fast path. Some controllers emit fractional seconds or a numeric UTC offset in condition
  lastTransitionTime fields, so fall back to a full ISO 8601 parse and normalize the result to a
  naive UTC datetime. Returning naive datetimes keeps every timestamp in these analyses mutually
  comparable (mixing aware and naive datetimes raises TypeError).

  Args:
    ts_value: Timestamp string, or None/empty

  Returns:
    naive UTC datetime object if valid, empty string if invalid or None
  """
  if ts_value is None or ts_value == "":
    return ""
  try:
    return datetime.strptime(ts_value, "%Y-%m-%dT%H:%M:%SZ")
  except (ValueError, TypeError):
    pass
  try:
    # fromisoformat only accepts a "Z" suffix on Python 3.11+
    parsed_ts = datetime.fromisoformat(ts_value.replace("Z", "+00:00"))
  except (ValueError, TypeError, AttributeError):
    return ""
  if parsed_ts.tzinfo is not None:
    parsed_ts = parsed_ts.astimezone(timezone.utc).replace(tzinfo=None)
  return parsed_ts


def compute_duration(end_ts, start_ts):
  """Compute duration in seconds between two timestamps.

  Returns 0 when either timestamp is missing so the value remains printable in a CSV column. A
  returned 0 is therefore ambiguous: it means either "no data" or a genuine sub-second duration.
  Use has_duration() to tell the two apart before collecting a value into a stats list.

  Args:
    end_ts: End datetime object or empty string
    start_ts: Start datetime object or empty string

  Returns:
    Duration in seconds (float) if both timestamps valid, 0 otherwise
  """
  if has_duration(end_ts, start_ts):
    return (end_ts - start_ts).total_seconds()
  return 0


def has_duration(end_ts, start_ts):
  """Determine whether a measurable duration exists between two timestamps.

  Both timestamps being present means the duration is real data, including when it computes to 0
  seconds. Transitions regularly complete inside a single second at Kubernetes timestamp
  granularity, so a 0 is a measurement rather than a missing value and belongs in the stats.

  Args:
    end_ts: End datetime object or empty string
    start_ts: Start datetime object or empty string

  Returns:
    True if both timestamps are valid datetime objects, False otherwise
  """
  return end_ts != "" and start_ts != ""
