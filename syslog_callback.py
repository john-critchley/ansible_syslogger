import sys

if sys.version_info[0] < 3:
    raise RuntimeError("This callback plugin requires Python 3.")

from ansible.plugins.callback import CallbackBase
import socket
import os
import box
import syslog
import time
import datetime

DOCUMENTATION = '''
name: syslog
callback_type: notification
requirements:
    - enable in configuration
short_description: Sends play events to syslog
version_added: "2.0"  # for collections, use         # Event-specific data mapping: (result_key, format_function)
        event_data_mapping = {
            'failed': ('msg', lambda value: f'error="{value}"'),
            'unreachable': ('msg', lambda value: f'error="{value}"'),
            'skipped': ('skip_reason', lambda value: f'reason="{value}"'),
            'retry': ('retries', lambda value: f'attempt={value + 1}')
        }
        
        # Add specific data based on event type
        if event_type in event_data_mapping:
            result_key, format_func = event_data_mapping[event_type]
            value = result._result[result_key]
            msg_parts.append(format_func(value))n version, not the Ansible version
description:
    - This callback plugin sends Ansible playbook execution results to a syslog server
    - Supports both RFC3164 and RFC5424 syslog message formats
    - Configurable via environment variables for syslog server, port, facility, and tag
    - Each event type has configurable log levels for fine-grained control
options:
  syslog_host:
    description: Syslog server hostname or IP address
    default: localhost
    env:
      - name: ANSIBLE_SYSLOG_HOST
    type: str
  syslog_port:
    description: Syslog server port
    default: 514
    env:
      - name: ANSIBLE_SYSLOG_PORT
    type: int
  syslog_facility:
    description: Syslog facility to use
    default: user
    env:
      - name: ANSIBLE_SYSLOG_FACILITY
    type: str
  tag:
    description: Tag to include in syslog messages
    default: ansible
    env:
      - name: ANSIBLE_SYSLOG_TAG
    type: str
  debug:
    description: Enable debug mode
    default: false
    env:
      - name: ANSIBLE_SYSLOG_DEBUG
    type: bool
  level_playbook_start:
    description: Log level for playbook start events
    default: LOG_INFO
    env:
      - name: ANSIBLE_SYSLOG_LEVEL_PLAYBOOK_START
    type: str
  level_play_start:
    description: Log level for play start events
    default: LOG_INFO
    env:
      - name: ANSIBLE_SYSLOG_LEVEL_PLAY_START
    type: str
  level_task_start:
    description: Log level for task start events
    default: LOG_DEBUG
    env:
      - name: ANSIBLE_SYSLOG_LEVEL_TASK_START
    type: str
  level_ok:
    description: Log level for successful task events
    default: LOG_INFO
    env:
      - name: ANSIBLE_SYSLOG_LEVEL_OK
    type: str
  level_changed:
    description: Log level for task change events
    default: LOG_INFO
    env:
      - name: ANSIBLE_SYSLOG_LEVEL_CHANGED
    type: str
  level_failed:
    description: Log level for task failure events
    default: LOG_ERR
    env:
      - name: ANSIBLE_SYSLOG_LEVEL_FAILED
    type: str
  level_unreachable:
    description: Log level for unreachable host events
    default: LOG_EMERG
    env:
      - name: ANSIBLE_SYSLOG_LEVEL_UNREACHABLE
    type: str
  level_skipped:
    description: Log level for skipped task events
    default: LOG_NOTICE
    env:
      - name: ANSIBLE_SYSLOG_LEVEL_SKIPPED
    type: str
  level_retry:
    description: Log level for task retry events
    default: LOG_WARNING
    env:
      - name: ANSIBLE_SYSLOG_LEVEL_RETRY
    type: str
  level_item_ok:
    description: Log level for successful loop item events
    default: LOG_INFO
    env:
      - name: ANSIBLE_SYSLOG_LEVEL_ITEM_OK
    type: str
  level_item_failed:
    description: Log level for failed loop item events
    default: LOG_ERR
    env:
      - name: ANSIBLE_SYSLOG_LEVEL_ITEM_FAILED
    type: str
  level_item_skipped:
    description: Log level for skipped loop item events
    default: LOG_NOTICE
    env:
      - name: ANSIBLE_SYSLOG_LEVEL_ITEM_SKIPPED
    type: str
  level_summary_start:
    description: Log level for summary start events
    default: LOG_INFO
    env:
      - name: ANSIBLE_SYSLOG_LEVEL_SUMMARY_START
    type: str
  level_summary_host:
    description: Log level for per-host summary events
    default: LOG_INFO
    env:
      - name: ANSIBLE_SYSLOG_LEVEL_SUMMARY_HOST
    type: str
  level_summary_complete:
    description: Log level for summary completion events
    default: LOG_INFO
    env:
      - name: ANSIBLE_SYSLOG_LEVEL_SUMMARY_COMPLETE
    type: str
'''

class CallbackModule(CallbackBase):
    
    # Constants using Box values
    DEFAULT_FACILITY = 'user'
    DEFAULT_TAG = 'ansible'
    DEFAULT_HOST = 'localhost'
    DEFAULT_PORT = 514

    syslog_levels = box.Box(
        LOG_EMERG=0,      # Emergency: system is unusable
        LOG_ALERT=1,      # Alert: action must be taken immediately
        LOG_CRIT=2,       # Critical: critical conditions
        LOG_ERR=3,        # Error: error conditions
        LOG_WARNING=4,    # Warning: warning conditions
        LOG_NOTICE=5,     # Notice: normal but significant condition
        LOG_INFO=6,       # Informational: informational messages
        LOG_DEBUG=7       # Debug: debug-level messages
    )

    # Default log levels for each event type
    level_defaults = box.Box(
        playbook_start='LOG_INFO',
        play_start='LOG_INFO', 
        task_start='LOG_DEBUG',
        ok='LOG_INFO',
        changed='LOG_INFO',
        failed='LOG_ERR',
        unreachable='LOG_EMERG',
        skipped='LOG_NOTICE',
        retry='LOG_WARNING',
        item_ok='LOG_INFO',
        item_failed='LOG_ERR',
        item_skipped='LOG_NOTICE',
        summary_start='LOG_INFO',
        summary_host='LOG_INFO',
        summary_complete='LOG_INFO'
    )

    # Syslog facility codes from RFC 5424
    # These values will be shifted left by 3 bits (multiplied by 8) and logically OR'd with the level
    syslog_facilities = box.Box(
        kern=0,           # kernel messages
        user=1,           # user-level messages
        mail=2,           # mail system
        daemon=3,         # system daemons
        auth=4,           # security/authorization messages
        syslog=5,         # messages generated internally by syslogd
        lpr=6,            # line printer subsystem
        news=7,           # network news subsystem
        uucp=8,           # UUCP subsystem
        cron=9,           # clock daemon
        authpriv=10,      # security/authorization messages
        ftp=11,           # FTP daemon
        ntp=12,           # NTP subsystem
        log_audit=13,     # log audit
        log_alert=14,     # log alert
        clock=15,         # clock daemon (note 2)
        local0=16,        # local use 0
        local1=17,        # local use 1
        local2=18,        # local use 2
        local3=19,        # local use 3
        local4=20,        # local use 4
        local5=21,        # local use 5
        local6=22,        # local use 6
        local7=23         # local use 7
    )

    @classmethod
    def make_priority(cls, facility, level):
        # Handle facility - use directly if numeric, lookup if string
        facility_code = facility if isinstance(facility, int) else cls.syslog_facilities[facility]
        
        # Handle level - use directly if numeric, lookup if string
        level_code = level if isinstance(level, int) else cls.syslog_levels[level]
        
        return (facility_code << 3) | level_code

    CALLBACK_VERSION = 2.0
    CALLBACK_TYPE = 'notification'
    CALLBACK_NAME = 'syslog'

    # only needed if you ship it and don't want to enable by default
    CALLBACK_NEEDS_ENABLED = True
    
    def __init__(self):
        # make sure the expected objects are present, calling the base's __init__
        super(CallbackModule, self).__init__()
        self.config = self._load_config() 
        self.syslog_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

    def _load_config(self):
        """Load configuration from environment variables"""

        # Default configuration using class constants
        defaults = box.Box(
            syslog_host=self.DEFAULT_HOST,
            syslog_port=self.DEFAULT_PORT,
            syslog_facility=self.DEFAULT_FACILITY,
            tag=self.DEFAULT_TAG,
            debug=False
        )

        # Get basic config from environment variables with defaults
        result = box.Box(
            syslog_host=os.environ.get('ANSIBLE_SYSLOG_HOST', defaults.syslog_host),
            syslog_port=int(os.environ.get('ANSIBLE_SYSLOG_PORT', defaults.syslog_port)),
            syslog_facility=os.environ.get('ANSIBLE_SYSLOG_FACILITY', defaults.syslog_facility),
            tag=os.environ.get('ANSIBLE_SYSLOG_TAG', defaults.tag),
            debug=os.environ.get('ANSIBLE_SYSLOG_DEBUG', '').lower() in ('true', '1', 'yes')
        )
        
        # Load event-specific log levels using comprehension
        level_config = {
            f'level_{event_type}': os.environ.get(f'ANSIBLE_SYSLOG_LEVEL_{event_type.upper()}', default_level)
            for event_type, default_level in self.level_defaults.items()
        }
        result.update(level_config)

        return result

    def v2_playbook_on_stats(self, stats):
        """Called at the end with playbook statistics summary"""
        # Send summary start message
        level = self._get_log_level('summary_start')
        self._send_to_syslog(level, f'{self._playbook_name} playbook_summary status=started')
        
        hosts = sorted(stats.processed.keys())
        if not hosts:
            self._send_to_syslog(self.syslog_levels.LOG_WARNING, f'{self._playbook_name} playbook_summary status=no_hosts')
            return
            
        # Send per-host summary statistics
        for host in hosts:
            host_stats = stats.summarize(host)
            total_tasks = sum(host_stats.values())
            
            # Create summary message with all stats
            summary_parts = []
            for msgk, msgv in host_stats.items():
                if msgv > 0:  # Only include non-zero counts
                    summary_parts.append(f'{msgk}={msgv}')
            
            summary_str = ' '.join(summary_parts) if summary_parts else 'no_tasks'
            msg = f'{self._playbook_name} playbook_summary target_host={host} total_tasks={total_tasks} {summary_str}'
            
            # Use appropriate log level based on failures/unreachable or configured level
            if host_stats['failures'] > 0:
                level = self.syslog_levels.LOG_ERR
            elif host_stats['unreachable'] > 0:
                level = self.syslog_levels.LOG_EMERG
            else:
                level = self._get_log_level('summary_host')
                
            self._send_to_syslog(level, msg)
            
        # Send summary completion message
        level = self._get_log_level('summary_complete')
        self._send_to_syslog(level, f'{self._playbook_name} playbook_summary status=completed')

    def _send_to_syslog_RFC5424(self, level, message):
        priority = self.make_priority(self.syslog_facilities.user, level)
        timestamp = datetime.datetime.now().strftime('%Y-%m-%dT%H:%M:%S%z')
        if len(timestamp) > 19:  # Fix timezone format
            timestamp = timestamp[:-2] + ':' + timestamp[-2:]
        hostname = socket.gethostname()
        syslog_msg = f"<{priority}>1 {timestamp} {hostname} {self.config.tag} - - {message}"
        
        self.syslog_socket.sendto(
            f'{syslog_msg}\n'.encode('utf-8'),
            (self.config.syslog_host, self.config.syslog_port)
        )

    def _send_to_syslog_RFC3164(self, level, message):
        priority = self.make_priority(self.syslog_facilities.user, level)
        timestamp = datetime.datetime.now().strftime('%b %d %H:%M:%S')
        hostname = socket.gethostname()
        syslog_msg = f"<{priority}>{timestamp} {hostname} {self.config.tag}: {message}"
        
        self.syslog_socket.sendto(
            f'{syslog_msg}\n'.encode('utf-8'),
            (self.config.syslog_host, self.config.syslog_port)
        )
    def _send_to_syslog(self, *args, **kwargs):
        self._send_to_syslog_RFC3164(*args, **kwargs)

    def v2_playbook_on_start(self, playbook):
        """Called when playbook execution starts"""
        self._playbook_name = os.path.basename(playbook._file_name)
        msg = f'{self._playbook_name} playbook status=started'
        level = self._get_log_level('playbook_start')
        self._send_to_syslog(level, msg)

    def __del__(self):
        """Clean up socket connection"""
        if hasattr(self, 'syslog_socket') and self.syslog_socket:
            self.syslog_socket.close()

    def v2_runner_on_ok(self, result):
        """Called when a task succeeds"""
        self._log_runner_event(result, 'ok')

    def v2_runner_on_changed(self, result):
        """Called when a task makes changes"""
        self._log_runner_event(result, 'changed')

    def v2_runner_on_failed(self, result, ignore_errors=False):
        """Called when a task fails"""
        self._log_runner_event(result, 'failed', ignore_errors=ignore_errors)

    def v2_runner_on_unreachable(self, result):
        """Called when a host is unreachable"""
        self._log_runner_event(result, 'unreachable')

    def v2_runner_on_skipped(self, result):
        """Called when a task is skipped"""
        self._log_runner_event(result, 'skipped')

    def v2_runner_retry(self, result):
        """Called when a task is retried"""
        self._log_runner_event(result, 'retry')

    def v2_runner_item_on_ok(self, result):
        """Called when a task item succeeds (for loops)"""
        item = result._result['item']
        self._log_runner_event(result, 'ok', item=item)

    def v2_runner_item_on_failed(self, result):
        """Called when a task item fails (for loops)"""
        item = result._result['item']
        self._log_runner_event(result, 'failed', item=item)

    def v2_runner_item_on_skipped(self, result):
        """Called when a task item is skipped (for loops)"""
        item = result._result['item']
        self._log_runner_event(result, 'skipped', item=item)

    def v2_playbook_on_play_start(self, play):
        """Called when a play starts"""
        play_name = play.get_name() or 'Unnamed play'
        msg = f'{self._playbook_name} play="{play_name}" status=started'
        level = self._get_log_level('play_start')
        self._send_to_syslog(level, msg)

    def v2_playbook_on_task_start(self, task, is_conditional):
        """Called when a task starts"""
        task_name = task.get_name()
        msg = f'{self._playbook_name} task="{task_name}" status=started'
        level = self._get_log_level('task_start')
        self._send_to_syslog(level, msg)

    def _get_log_level(self, event_type):
        """Get the configured log level for a specific event type"""
        level_name = self.config[f'level_{event_type}']
        return self.syslog_levels[level_name]

    def _log_runner_event(self, result, event_type, item=None, ignore_errors=False):
        """Generic function to log runner events"""
        host = result._host.get_name()
        task_name = result._task.get_name()
        
        # Build message components
        msg_parts = [f'{self._playbook_name} target_host={host} task="{task_name}"']
        
        # Add item for loop events
        if item is not None:
            msg_parts.append(f'item="{item}"')
            
        msg_parts.append(f'status={event_type}')
        
        # Event-specific data mapping: (result_key, format_function)
        event_data_mapping = {
            'failed': ('msg', lambda value: f'error="{value}"'),
            'unreachable': ('msg', lambda value: f'error="{value}"'),
            'skipped': ('skip_reason', lambda value: f'reason="{value}"'),
            'retry': ('retries', lambda value: f'attempt={value + 1}')
        }
        
        # Add specific data based on event type
        if event_type in event_data_mapping:
            result_key, format_func = event_data_mapping[event_type]
            value = result._result[result_key]
            msg_parts.append(format_func(value))
            
        msg = ' '.join(msg_parts)
        
        # Determine log level
        if event_type == 'failed' and ignore_errors:
            level = self.syslog_levels.LOG_NOTICE
        else:
            level_key = f'item_{event_type}' if item is not None else event_type
            level = self._get_log_level(level_key)
            
        self._send_to_syslog(level, msg)

if __name__=='__main__':
    
    tst=CallbackModule()
    tst.v2_playbook_on_stats(stats)
