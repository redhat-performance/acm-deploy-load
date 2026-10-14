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


def parse_ts(ts_value):
  """Parse ISO 8601 timestamp string into datetime object.

  Args:
    ts_value: Timestamp string in format "%Y-%m-%dT%H:%M:%SZ" or None/empty

  Returns:
    datetime object if valid, empty string if invalid or None
  """
  if ts_value is None or ts_value == "":
    return ""
  try:
    return datetime.strptime(ts_value, "%Y-%m-%dT%H:%M:%SZ")
  except ValueError:
    return ""


def compute_duration(end_ts, start_ts):
  """Compute duration in seconds between two timestamps.

  Args:
    end_ts: End datetime object or empty string
    start_ts: Start datetime object or empty string

  Returns:
    Duration in seconds (float) if both timestamps valid, 0 otherwise
  """
  if end_ts != "" and start_ts != "":
    return (end_ts - start_ts).total_seconds()
  return 0
