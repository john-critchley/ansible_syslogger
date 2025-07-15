# Ansible Syslog Callback

An Ansible callback plugin that sends playbook execution results to a syslog server.

## Features

- Sends Ansible playbook statistics to syslog in RFC3164 or RFC5424 format
- Configurable syslog facility and server destination
- Supports both string and numeric facility/level codes
- Environment variable configuration
- Proper error handling and logging

## Configuration

Configure the callback using environment variables:

```bash
export ANSIBLE_SYSLOG_HOST=your-syslog-server.com
export ANSIBLE_SYSLOG_PORT=514
export ANSIBLE_SYSLOG_FACILITY=local0
export ANSIBLE_SYSLOG_TAG=ansible
export ANSIBLE_SYSLOG_DEBUG=true
```

## Usage

1. Place `syslog_callback.py` in your Ansible callback plugins directory
2. Enable the callback in your `ansible.cfg`:
   ```ini
   [defaults]
   callback_plugins = /path/to/callback/plugins
   callbacks_enabled = syslog
   ```
3. Run your Ansible playbooks normally

The callback will automatically send playbook execution statistics to your configured syslog server.

## Syslog Message Format

Messages are sent in RFC3164 format by default:
```
<priority>timestamp hostname tag: message
```

The priority is calculated using standard syslog facility and severity levels.

## Dependencies

- `python-box` - For configuration management
- Standard Python libraries (socket, datetime, os)
