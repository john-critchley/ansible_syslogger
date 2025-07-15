from __future__ import (absolute_import, division, print_function)
__metaclass__ = type
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
version_added: "2.0"  # for collections, use the collection version, not the Ansible version
description:
    - This callback plugin sends Ansible playbook execution results to a syslog server
    - Supports both RFC3164 and RFC5424 syslog message formats
    - Configurable via environment variables for syslog server, port, facility, and tag
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
'''

class CallbackModule(CallbackBase):

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
        self.alert_levels=dict(
            ok=self.syslog_levels.LOG_INFO,
            failures=self.syslog_levels.LOG_ERR,
            unreachable=self.syslog_levels.LOG_EMERG,
            changed=self.syslog_levels.LOG_INFO,
            skipped=self.syslog_levels.LOG_NOTICE,
            rescued=self.syslog_levels.LOG_NOTICE,
            ignored=self.syslog_levels.LOG_NOTICE
            )

    def _load_config(self):
        """Load configuration from environment variables"""

        # Default configuration
        defaults = dict(
            syslog_host= 'localhost',
            syslog_port= 514,
            syslog_facility= 'user',
            changed_behavior= 'normal',  # normal, expected, unexpected
            tag= 'ansible',
            debug= False
        )

        # Get values from environment variables with defaults
        result = box.Box()
        result['syslog_host'] = os.environ.get('ANSIBLE_SYSLOG_HOST', defaults['syslog_host'])
        result['syslog_port'] = int(os.environ.get('ANSIBLE_SYSLOG_PORT', defaults['syslog_port']))
        result['syslog_facility'] = os.environ.get('ANSIBLE_SYSLOG_FACILITY', defaults['syslog_facility'])
        result['changed_behavior'] = os.environ.get('ANSIBLE_SYSLOG_CHANGED_BEHAVIOR', defaults['changed_behavior'])
        result['tag'] = os.environ.get('ANSIBLE_SYSLOG_TAG', defaults['tag'])
        result['debug'] = os.environ.get('ANSIBLE_SYSLOG_DEBUG', '').lower() in ('true', '1', 'yes')

        return result

    def v2_playbook_on_stats(self, stats):
        """Called at the end with playbook statistics summary"""
        try:
            # Send summary start message
            self._send_to_syslog(self.syslog_levels.LOG_INFO, f'{self._playbook_name} playbook_summary status=started')
            
            cl=self.__class__
            hosts = sorted(stats.processed.keys())
            if not hosts: #Needed?
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
                
                # Use appropriate log level based on failures/unreachable
                if host_stats.get('failures', 0) > 0:
                    level = self.syslog_levels.LOG_ERR
                elif host_stats.get('unreachable', 0) > 0:
                    level = self.syslog_levels.LOG_EMERG
                elif host_stats.get('changed', 0) > 0:
                    level = self.syslog_levels.LOG_INFO
                else:
                    level = self.syslog_levels.LOG_INFO
                    
                self._send_to_syslog(level, msg)
                
            # Send summary completion message
            self._send_to_syslog(self.syslog_levels.LOG_INFO, f'{self._playbook_name} playbook_summary status=completed')
            
        except Exception as e:
            self._send_to_syslog(self.syslog_levels.LOG_ALERT, f'{self._playbook_name} playbook_summary_error error="{e.__class__.__name__}"')
            for arg in e.args:
                self._send_to_syslog(self.syslog_levels.LOG_ALERT, f'{self._playbook_name} playbook_summary_error detail="{arg}"')

    def _send_to_syslog_RFC5424(self, level, message):
        facility='user'
        priority = self.make_priority(facility, level)
        timestamp = datetime.datetime.now().strftime('%Y-%m-%dT%H:%M:%S%z')
        if len(timestamp) > 19:  # Fix timezone format
            timestamp = timestamp[:-2] + ':' + timestamp[-2:]
        hostname = socket.gethostname()
        syslog_msg = f"<{priority}>1 {timestamp} {hostname} {self.config['tag']} - - {message}"
        
        self.syslog_socket.sendto(
            f'{syslog_msg}\n'.encode('utf-8'),
            (self.config.syslog_host, self.config.syslog_port)
        )

    def _send_to_syslog_RFC3164(self, level, message):
        facility='user'
        priority = self.make_priority(facility, level)
        timestamp = datetime.datetime.now().strftime('%b %d %H:%M:%S')
        hostname = socket.gethostname()
        syslog_msg = f"<{priority}>{timestamp} {hostname} {self.config['tag']}: {message}"
        
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
        self._send_to_syslog(self.syslog_levels.LOG_INFO, msg)

    def __del__(self):
        """
        Clean up socket connection
        """
        if self.syslog_socket:
            self.syslog_socket.close()

    def v2_runner_on_ok(self, result):
        """Called when a task succeeds"""
        host = result._host.get_name()
        task_name = result._task.get_name()
        msg = f'{self._playbook_name} target_host={host} task="{task_name}" status=ok'
        self._send_to_syslog(self.syslog_levels.LOG_INFO, msg)

    def v2_runner_on_changed(self, result):
        """Called when a task makes changes"""
        host = result._host.get_name()
        task_name = result._task.get_name()
        msg = f'{self._playbook_name} target_host={host} task="{task_name}" status=changed'
        self._send_to_syslog(self.syslog_levels.LOG_INFO, msg)

    def v2_runner_on_failed(self, result, ignore_errors=False):
        """Called when a task fails"""
        host = result._host.get_name()
        task_name = result._task.get_name()
        error_msg = result._result.get('msg', 'Unknown error')
        msg = f'{self._playbook_name} target_host={host} task="{task_name}" status=failed error="{error_msg}"'
        level = self.syslog_levels.LOG_NOTICE if ignore_errors else self.syslog_levels.LOG_ERR
        self._send_to_syslog(level, msg)

    def v2_runner_on_unreachable(self, result):
        """Called when a host is unreachable"""
        host = result._host.get_name()
        task_name = result._task.get_name()
        error_msg = result._result.get('msg', 'Host unreachable')
        msg = f'{self._playbook_name} target_host={host} task="{task_name}" status=unreachable error="{error_msg}"'
        self._send_to_syslog(self.syslog_levels.LOG_EMERG, msg)

    def v2_runner_on_skipped(self, result):
        """Called when a task is skipped"""
        host = result._host.get_name()
        task_name = result._task.get_name()
        reason = result._result.get('skip_reason', 'Condition not met')
        msg = f'{self._playbook_name} target_host={host} task="{task_name}" status=skipped reason="{reason}"'
        self._send_to_syslog(self.syslog_levels.LOG_NOTICE, msg)

    def v2_runner_retry(self, result):
        """Called when a task is retried"""
        host = result._host.get_name()
        task_name = result._task.get_name()
        retry_count = result._result.get('retries', 0) + 1
        msg = f'{self._playbook_name} target_host={host} task="{task_name}" status=retry attempt={retry_count}'
        self._send_to_syslog(self.syslog_levels.LOG_WARNING, msg)

    def v2_runner_item_on_ok(self, result):
        """Called when a task item succeeds (for loops)"""
        host = result._host.get_name()
        task_name = result._task.get_name()
        item = result._result.get('item', 'N/A')
        msg = f'{self._playbook_name} target_host={host} task="{task_name}" item="{item}" status=ok'
        self._send_to_syslog(self.syslog_levels.LOG_INFO, msg)

    def v2_runner_item_on_failed(self, result):
        """Called when a task item fails (for loops)"""
        host = result._host.get_name()
        task_name = result._task.get_name()
        item = result._result.get('item', 'N/A')
        error_msg = result._result.get('msg', 'Unknown error')
        msg = f'{self._playbook_name} target_host={host} task="{task_name}" item="{item}" status=failed error="{error_msg}"'
        self._send_to_syslog(self.syslog_levels.LOG_ERR, msg)

    def v2_runner_item_on_skipped(self, result):
        """Called when a task item is skipped (for loops)"""
        host = result._host.get_name()
        task_name = result._task.get_name()
        item = result._result.get('item', 'N/A')
        reason = result._result.get('skip_reason', 'Condition not met')
        msg = f'{self._playbook_name} target_host={host} task="{task_name}" item="{item}" status=skipped reason="{reason}"'
        self._send_to_syslog(self.syslog_levels.LOG_NOTICE, msg)

    def v2_playbook_on_play_start(self, play):
        """Called when a play starts"""
        play_name = play.get_name() or 'Unnamed play'
        msg = f'{self._playbook_name} play="{play_name}" status=started'
        self._send_to_syslog(self.syslog_levels.LOG_INFO, msg)

    def v2_playbook_on_task_start(self, task, is_conditional):
        """Called when a task starts"""
        task_name = task.get_name()
        msg = f'{self._playbook_name} task="{task_name}" status=started'
        self._send_to_syslog(self.syslog_levels.LOG_DEBUG, msg)

if __name__=='__main__':
    
    tst=CallbackModule()
    tst.v2_playbook_on_stats(stats)
