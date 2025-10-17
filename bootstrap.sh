#!/usr/bin/env bash
python3 -m venv .venv
source .venv/bin/activate
pip3 install --upgrade pip
# pip3 install ansible-core==2.16.10
pip3 install -r requirements.txt
ansible-galaxy collection install --upgrade awx.awx ansible.eda
