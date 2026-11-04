# Contributing to acm-deploy-load

Thank you for your interest in contributing to `acm-deploy-load`! This document provides guidelines and instructions for contributing to the project.

## Table of Contents

- [Code of Conduct](#code-of-conduct)
- [Getting Started](#getting-started)
- [Development Environment Setup](#development-environment-setup)
- [Project Structure](#project-structure)
- [Development Workflow](#development-workflow)
- [Coding Standards](#coding-standards)
- [Testing Guidelines](#testing-guidelines)
- [Documentation Standards](#documentation-standards)
- [Pull Request Process](#pull-request-process)
- [Reporting Issues](#reporting-issues)
- [Communication](#communication)

---

## Code of Conduct

This project follows the principles of respectful collaboration:

- **Be respectful** - Value diverse perspectives and experiences
- **Be constructive** - Focus on what's best for the project and community
- **Be collaborative** - Work together to resolve conflicts and improve the project
- **Be professional** - Maintain a harassment-free environment for everyone

---

## Getting Started

### Prerequisites

Before contributing, ensure you have:

- **Python 3.9+** installed
- **OpenShift CLI (`oc`)** installed and configured
- **Access to an ACM hub cluster** (for integration testing)
- **Git** configured with your name and email
- **Basic understanding** of:
  - Red Hat Advanced Cluster Management (ACM)
  - OpenShift/Kubernetes
  - Python development
  - Prometheus metrics

### Quick Start

1. **Fork the repository** on GitHub
2. **Clone your fork**:
   ```bash
   git clone https://github.com/YOUR_USERNAME/acm-deploy-load.git
   cd acm-deploy-load
   ```
3. **Set up development environment**:
   ```bash
   ./bootstrap.sh
   source .venv/bin/activate
   ```
4. **Create a feature branch**:
   ```bash
   git checkout -b feature/your-feature-name
   ```

---

## Development Environment Setup

### Initial Setup

```bash
# 1. Bootstrap the environment
./bootstrap.sh

# This creates:
# - .venv/ (Python virtual environment)
# - Installs Python dependencies from requirements.txt
# - Installs Ansible collections from requirements.yml

# 2. Activate virtual environment
source .venv/bin/activate

# 3. Verify installation
python3 --version  # Should be 3.9+
oc version         # Should show client version
ansible --version  # Should show ansible-core version
```

### Environment Variables

Set these environment variables for development:

```bash
# Hub cluster kubeconfig
export KUBECONFIG=/path/to/hub/kubeconfig

# Optional: Enable debug logging
export LOG_LEVEL=DEBUG

# Optional: Default results directory
export RESULTS_DIR=./results
```

### Required Tools

Install these additional tools for full development:

```bash
# For PDF report generation
pip install reportlab

# For graph generation (requires Chrome/Chromium)
pip install kaleido

# For linting (optional)
pip install pylint black flake8

# For Ansible development
pip install ansible-lint
```

---

## Project Structure

Understanding the repository layout is essential for contributing:

```
acm-deploy-load/
├── acm-deploy-load/          # Python scripts (workload generation & analysis)
│   ├── acm-deploy-load.py    # Main deployment workload
│   ├── analyze-*.py          # Analysis scripts
│   ├── graph-*.py            # Visualization scripts
│   └── utils/                # Shared utilities
│       ├── command.py        # oc CLI wrapper
│       ├── ztp_monitor.py    # Background monitoring
│       └── common_ocp.py     # OpenShift utilities
├── scripts/                  # Bash orchestration scripts
│   ├── interval-ztp-install-all.sh  # Main orchestration
│   └── post-*.sh             # Post-test data collection
├── ansible/                  # Ansible playbooks for hub setup
│   ├── roles/                # 38 Ansible roles
│   └── vars/                 # Variable files
├── results/                  # Test output (git-ignored)
├── .claude/skills/           # Claude Code analysis skills
├── CLAUDE.md                 # Project overview & file tree
├── ARCHITECTURE.md           # System design documentation
├── CONTRIBUTING.md           # This file
└── requirements.txt          # Python dependencies
```

**Important Files to Update**:
- `CLAUDE.md` - When adding/removing scripts or changing directory structure
- `ARCHITECTURE.md` - When adding deployment methods or major architectural changes
- `requirements.txt` - When adding Python dependencies

---

## Development Workflow

### Creating a Feature Branch

```bash
# Update main branch
git checkout main
git pull upstream main

# Create feature branch
git checkout -b feature/short-description

# Branch naming conventions:
# - feature/add-new-deployment-method
# - bugfix/fix-prometheus-query
# - docs/update-architecture
# - test/add-unit-tests
```

### Making Changes

1. **Write code** following the [Coding Standards](#coding-standards)
2. **Test locally** using dry-run mode or small-scale tests
3. **Update documentation** if adding features or changing behavior
4. **Commit incrementally** with clear messages

### Commit Message Guidelines

Follow conventional commit format:

```
<type>(<scope>): <subject>

<body>

<footer>
```

**Types**:
- `feat` - New feature
- `fix` - Bug fix
- `docs` - Documentation changes
- `refactor` - Code refactoring
- `test` - Adding or updating tests
- `chore` - Maintenance tasks

**Examples**:

```
feat(deployment): add ibi-clusterinstance-gitops method

Implements Image-Based Installer deployment via ClusterInstance
and ArgoCD GitOps workflow. Includes manifest generation,
monitoring, and analysis support.

Closes #123
```

```
fix(prometheus): handle OCP 5.x token creation

OCP 5.0+ requires the same token creation method as 4.11+.
Updates get_prometheus_token() to support major version >= 5.

Fixes #456
```

```
docs(architecture): document ZTPMonitor design

Adds detailed explanation of background monitoring architecture,
sampling strategy, and state detection logic.
```

### Keeping Your Branch Updated

```bash
# Fetch upstream changes
git fetch upstream

# Rebase on main
git rebase upstream/main

# Resolve conflicts if any
git add <resolved-files>
git rebase --continue

# Force push (if already pushed)
git push --force-with-lease origin feature/your-branch
```

---

## Coding Standards

### Python Style Guide

Follow **PEP 8** with these project-specific conventions:

#### Naming Conventions

```python
# Functions and variables: snake_case
def deploy_clusters(cluster_config):
    cluster_count = len(cluster_config)

# Classes: PascalCase
class ClusterDeployment:
    pass

# Constants: UPPER_SNAKE_CASE
MAX_RETRY_ATTEMPTS = 5
DEFAULT_TIMEOUT = 300

# Private functions/methods: leading underscore
def _internal_helper():
    pass
```

#### Import Organization

```python
# 1. Standard library
import argparse
import json
import logging
import os
import sys
import time
from datetime import datetime

# 2. Third-party
import pandas as pd
import plotly.express as px
import requests

# 3. Local application
from utils.command import command
from utils.common_ocp import get_ocp_version
from utils.output import write_stats_file
```

#### Logging

Use Python's `logging` module, not `print()`:

```python
import logging

logger = logging.getLogger(__name__)

# Good
logger.info(f"Deploying {cluster_count} clusters")
logger.warning("etcd DB size approaching quota")
logger.error(f"Failed to apply manifest: {error}")

# Bad
print(f"Deploying {cluster_count} clusters")
```

**Log Levels**:
- `DEBUG` - Verbose diagnostic information
- `INFO` - General informational messages
- `WARNING` - Warning messages (recoverable issues)
- `ERROR` - Error messages (failures)

#### Error Handling

Always handle expected errors gracefully:

```python
# Good
try:
    rc, output = command(oc_cmd, retries=3)
    if rc != 0:
        logger.error(f"Command failed with exit code {rc}")
        return None
    data = json.loads(output)
except json.JSONDecodeError as e:
    logger.error(f"Failed to parse JSON: {e}")
    return None

# Bad (bare except)
try:
    data = json.loads(output)
except:
    pass
```

#### Documentation Strings

Add docstrings to all public functions:

```python
def generate_cluster_manifest(cluster_name, deploy_method, config):
    """
    Generate cluster deployment manifest for the specified method.
    
    Args:
        cluster_name (str): Name of the cluster to deploy
        deploy_method (str): Deployment method (e.g., 'ibi-clusterinstance-gitops')
        config (dict): Cluster configuration parameters
        
    Returns:
        str: YAML manifest as string
        
    Raises:
        ValueError: If deploy_method is not supported
    """
    if deploy_method not in SUPPORTED_METHODS:
        raise ValueError(f"Unsupported method: {deploy_method}")
    
    # Implementation...
```

#### Type Hints (Optional but Encouraged)

```python
from typing import Dict, List, Optional, Tuple

def query_prometheus(
    route: str,
    query: str,
    token: str,
    start_ts: int,
    end_ts: int
) -> Optional[Dict]:
    """Query Prometheus/Thanos endpoint."""
    # Implementation...
```

### Bash Script Standards

For shell scripts in `scripts/`:

```bash
#!/usr/bin/env bash

# Strict error handling
set -euo pipefail

# Constants in UPPER_CASE
readonly RESULTS_DIR="${1:-./results}"
readonly DEFAULT_TIMEOUT=3600

# Functions in snake_case
extract_timestamp() {
    local report_file="$1"
    local field="$2"
    grep "$field" "$report_file" | awk '{print $NF}'
}

# Main logic
main() {
    local cluster_count="$1"
    
    echo "Deploying $cluster_count clusters..."
    
    # Use || true for non-critical commands
    cleanup_old_results || true
    
    # Check exit codes explicitly for critical commands
    if ! python3 acm-deploy-load/acm-deploy-load.py --clusters "$cluster_count"; then
        echo "ERROR: Deployment failed" >&2
        exit 1
    fi
}

main "$@"
```

### Ansible Standards

For Ansible roles in `ansible/roles/`:

```yaml
# Use meaningful task names
- name: Create ACM namespace
  kubernetes.core.k8s:
    state: present
    definition:
      apiVersion: v1
      kind: Namespace
      metadata:
        name: open-cluster-management

# Tag tasks for selective execution
  tags:
    - acm
    - namespace

# Use variables for configurable values
- name: Deploy MCE operator
  kubernetes.core.k8s:
    state: present
    template: mce-subscription.yaml.j2
  vars:
    mce_version: "{{ mce_operator_version | default('stable-2.8') }}"
```

---

## Testing Guidelines

### Testing Strategy

The project uses primarily **integration testing** with real ACM clusters. Unit tests are limited but encouraged for utility functions.

### Pre-Commit Testing

Before submitting a pull request:

#### 1. Dry-Run Testing

Test manifest generation without applying to cluster:

```bash
# Test deployment method
python3 acm-deploy-load/acm-deploy-load.py \
  --deploy-method ibi-clusterinstance-gitops \
  --clusters 10 \
  --dry-run \
  --results-dir /tmp/dry-run-test

# Verify generated manifests
ls /tmp/dry-run-test/manifests/
cat /tmp/dry-run-test/manifests/*.yaml

# Validate with oc (client-side dry-run)
oc apply --dry-run=client -f /tmp/dry-run-test/manifests/
```

#### 2. Small-Scale Integration Test

Test with minimal cluster count:

```bash
# 5 clusters, 2 per batch, 5-minute intervals
./scripts/interval-ztp-install-all.sh \
  --clusters 5 \
  --batch-size 2 \
  --interval 300 \
  --method ibi-clusterinstance-gitops \
  --results-dir ./results/integration-test

# Verify results
cat ./results/integration-test/report.txt
ls ./results/integration-test/deploy-pa-*/stats/
```

#### 3. Analysis Script Testing

Test analysis scripts against existing results:

```bash
# Use a previous test's results directory
RESULTS_DIR="./results/20260913-152810-ibi-clusterinstance-gitops-1000cpa-500b-1800i-3"

# Test new analysis script
python3 acm-deploy-load/analyze-mynewresource.py "$RESULTS_DIR"

# Verify output
ls "$RESULTS_DIR"/*.csv
cat "$RESULTS_DIR"/*.stats
```

#### 4. Linting (Optional)

```bash
# Python linting
pylint acm-deploy-load/*.py
black --check acm-deploy-load/
flake8 acm-deploy-load/

# Ansible linting
ansible-lint ansible/playbooks/
```

### Writing Tests

If adding unit tests (encouraged for utility functions):

```python
# tests/test_command.py
import unittest
from acm_deploy_load.utils.command import command

class TestCommand(unittest.TestCase):
    def test_successful_command(self):
        """Test successful command execution."""
        rc, output = command(["echo", "hello"])
        self.assertEqual(rc, 0)
        self.assertEqual(output.strip(), "hello")
    
    def test_failed_command(self):
        """Test failed command handling."""
        rc, output = command(["false"])
        self.assertNotEqual(rc, 0)
    
    def test_dry_run_mode(self):
        """Test dry-run mode doesn't execute."""
        rc, output = command(["rm", "-rf", "/"], dry_run=True)
        self.assertEqual(rc, 0)  # Dry-run returns success without execution

if __name__ == "__main__":
    unittest.main()
```

---

## Documentation Standards

### When to Update Documentation

Update documentation when you:

- Add a new deployment method
- Add a new analysis script
- Change CLI arguments or behavior
- Add new dependencies
- Change the project structure
- Fix a non-obvious bug

### Documentation Files

#### `CLAUDE.md`

**Update when**:
- Adding/removing scripts in `acm-deploy-load/`, `scripts/`, or `utils/`
- Adding/removing Ansible roles
- Changing deployment methods
- Adding/removing skills

**Key sections to maintain**:
- File tree in "Code Architecture"
- "Main Workloads" table
- "Deployment methods" list

#### `ARCHITECTURE.md`

**Update when**:
- Adding a new deployment method (add to "Deployment Methods" section)
- Changing component architecture
- Adding new analysis pipelines
- Changing data formats

#### README.md (if it exists)

**Update when**:
- Changing installation steps
- Changing quick start instructions
- Adding new major features

### Code Comments

Add comments for:

- **Non-obvious logic**:
  ```python
  # OCP 5.x uses same token creation as 4.11+ (not 4.10-)
  if (ocp_version["major"] == 4 and ocp_version["minor"] > 10) or ocp_version["major"] >= 5:
      return create_token_method()
  ```

- **Workarounds**:
  ```python
  # Workaround for MCE-1234: ClusterInstance controller doesn't handle
  # rapid succession creates, add 2s delay between applications
  time.sleep(2)
  ```

- **API version dependencies**:
  ```python
  # TALM v4.16+ uses different CGU status structure
  if talm_minor_version >= 16:
      return parse_cgu_status_v16(cgu)
  ```

**Avoid comments that**:
- Restate what the code obviously does
- Reference the current task/PR (put that in commit message)
- Are outdated or wrong

---

## Pull Request Process

### Before Submitting

Checklist before creating a PR:

- [ ] Code follows [Coding Standards](#coding-standards)
- [ ] Tested with dry-run mode (for deployment changes)
- [ ] Tested with small-scale integration test (if possible)
- [ ] Updated `CLAUDE.md` file tree (if structure changed)
- [ ] Updated `ARCHITECTURE.md` (if architecture changed)
- [ ] Added docstrings to new functions
- [ ] Commit messages follow conventional format
- [ ] Branch is rebased on latest main

### Creating a Pull Request

1. **Push your branch**:
   ```bash
   git push origin feature/your-feature-name
   ```

2. **Open PR on GitHub**:
   - Navigate to your fork on GitHub
   - Click "Compare & pull request"
   - Fill out the PR template (see below)

3. **PR Title Format**:
   ```
   <type>(<scope>): <short description>
   ```
   Example: `feat(deployment): add ibi-clusterinstance-gitops method`

4. **PR Description Template**:
   ```markdown
   ## Summary
   Brief description of what this PR does.

   ## Changes
   - List of changes made
   - Each change as a bullet point

   ## Testing
   How this was tested:
   - [ ] Dry-run mode
   - [ ] Small-scale integration test (5 clusters)
   - [ ] Full-scale test (100+ clusters) - if applicable

   ## Documentation
   - [ ] Updated CLAUDE.md
   - [ ] Updated ARCHITECTURE.md
   - [ ] Added/updated docstrings
   - [ ] Added code comments for non-obvious logic

   ## Related Issues
   Closes #123
   Related to #456
   ```

### Code Review Process

**What reviewers look for**:
- Code correctness and error handling
- Adherence to coding standards
- Test coverage (dry-run or integration tests performed)
- Documentation updates
- Backward compatibility (does this break existing usage?)
- Performance impact (especially for analysis scripts)

**Responding to feedback**:
- Address all comments or explain why you disagree
- Push new commits (don't force-push during review)
- Mark conversations as resolved when addressed
- Request re-review when ready

### Merging

- PRs require **1 approval** from a maintainer
- All CI checks must pass (if configured)
- Maintainers will merge using **squash and merge** for clean history

---

## Reporting Issues

### Before Opening an Issue

1. **Search existing issues** to avoid duplicates
2. **Check documentation** (CLAUDE.md, ARCHITECTURE.md)
3. **Try latest version** (pull latest main branch)

### Bug Reports

Use this template:

```markdown
## Bug Description
Clear description of the bug.

## Expected Behavior
What you expected to happen.

## Actual Behavior
What actually happened.

## Reproduction Steps
1. Run command: `python3 acm-deploy-load/acm-deploy-load.py ...`
2. Observe error: ...
3. Check logs: ...

## Environment
- ACM Version: 2.11.0
- MCE Version: 2.8.0
- Hub OCP Version: 4.16.0
- Python Version: 3.11.5
- OS: RHEL 9.2

## Logs
```
Paste relevant error logs here
```

## Additional Context
Any other context (cluster size, network conditions, etc.)
```

### Feature Requests

Use this template:

```markdown
## Feature Description
What feature you'd like to see.

## Use Case
Why this feature is needed / what problem it solves.

## Proposed Solution
How you envision this working (optional).

## Alternatives Considered
Other approaches you've thought about (optional).
```

### Questions

For questions about usage:
- Tag issue with `question` label
- Check ARCHITECTURE.md first
- Provide context about what you're trying to achieve

---

## Communication

### Channels

- **GitHub Issues** - Bug reports, feature requests, questions
- **GitHub Discussions** - General discussion, ideas, Q&A
- **Pull Requests** - Code review and collaboration

### Response Times

This is a community project. Response times vary:
- Issues: Typically within 1-2 weeks
- PRs: Typically within 1 week for initial review
- Questions: Best-effort basis

### Getting Help

If stuck on a contribution:

1. **Check documentation**: CLAUDE.md, ARCHITECTURE.md
2. **Search issues**: Someone may have asked before
3. **Open a discussion**: Ask for guidance before investing effort
4. **Open a draft PR**: Get early feedback on approach

---

## Development Tips

### Working with Large Results

Results directories can be large (GB+):

```bash
# Archive before committing
tar -czf results-backup.tar.gz results/

# Clean up old results
find results/ -type d -mtime +30 -exec rm -rf {} +

# .gitignore already excludes results/
```

### Testing Against Different OCP Versions

```bash
# Set kubeconfig for different clusters
export KUBECONFIG=/path/to/ocp-4.16-kubeconfig
python3 acm-deploy-load/acm-deploy-load.py ...

export KUBECONFIG=/path/to/ocp-5.0-kubeconfig
python3 acm-deploy-load/acm-deploy-load.py ...
```

### Debugging Prometheus Queries

```bash
# Test individual query
python3 -c "
from acm_deploy_load.utils.common_ocp import get_prometheus_token, get_thanos_querier_route
import requests

route = get_thanos_querier_route('/path/to/kubeconfig')
token = get_prometheus_token('/path/to/kubeconfig', {'major': 4, 'minor': 16})

query = 'sum(container_memory_working_set_bytes{namespace=\"open-cluster-management\"})'
response = requests.get(
    f'{route}/api/v1/query',
    params={'query': query},
    headers={'Authorization': f'Bearer {token}'},
    verify=False
)
print(response.json())
"
```

### Performance Profiling

```bash
# Profile script execution
python3 -m cProfile -o profile.stats acm-deploy-load/analyze-prometheus.py results/test/

# View profile
python3 -m pstats profile.stats
# In pstats shell: sort cumulative, stats 20
```

---

## License

By contributing to this project, you agree that your contributions will be licensed under the same license as the project (Apache License 2.0).

---

## Recognition

Contributors will be recognized in:
- Git commit history
- GitHub contributor graph
- Release notes (for significant contributions)

---

## Questions?

If you have questions about contributing:
- Open a GitHub Discussion
- Open an issue with the `question` label
- Review ARCHITECTURE.md for technical details

**Thank you for contributing to acm-deploy-load!** 🎉
