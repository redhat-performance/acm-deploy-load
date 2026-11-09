#!/usr/bin/env python3
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

import logging

from utils.command import command

logger = logging.getLogger("acm-deploy-load")


def git_commit_push(files, commit_message, repo_dir, dry_run, retries=3):
  for f in files:
    logger.debug("git add {}".format(f))
    rc, output = command(["git", "add", f], dry_run, retries=retries, cmd_directory=repo_dir)
    if rc != 0:
      logger.error("git add failed rc: {}, Output: {}".format(rc, output))
      raise RuntimeError("git add failed: rc={}, file={}".format(rc, f))
  logger.info("Added {} files in git".format(len(files)))
  rc, output = command(["git", "commit", "-m", commit_message], dry_run, cmd_directory=repo_dir)
  if rc != 0:
    if output and "nothing to commit" in output:
      logger.warning("git commit: nothing to commit, proceeding with push")
    else:
      logger.error("git commit failed rc: {}, Output: {}".format(rc, output))
      raise RuntimeError("git commit failed: rc={}".format(rc))
  rc, output = command(["git", "push"], dry_run, cmd_directory=repo_dir)
  if rc != 0:
    logger.error("git push failed rc: {}, Output: {}".format(rc, output))
    raise RuntimeError("git push failed: rc={}".format(rc))
