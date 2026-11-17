#!/usr/bin/env bash
# Install and update uv
if [ ! $(which uv) ]; then curl -LsSf https://astral.sh/uv/install.sh | sh; fi
uv self update

# Create and populate virtual environment
uv venv --clear --force .venv --python 3.12
uv pip install --python .venv/bin/python -r requirements.txt
# uv pip install ansible-core==2.16.10

# Activate virtual environment when sourcing
source .venv/bin/activate

# Configure Ansible Collections
ansible-galaxy collection install --upgrade awx.awx ansible.eda

# Plotly's static image export tool requires Chrome to be installed
plotly_get_chrome -y
