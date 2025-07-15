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
name: haha
callback_type: haha
requirements:
    - enable in configuration
short_description: Funny
version_added: "2.0"  # for collections, use the collection version, not the Ansible version
description:
    - Funny haha
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
        return (cls.syslog_facilities[facility] << 3) | cls.syslog_levels[level]

    CALLBACK_VERSION = 2.0
    CALLBACK_TYPE = 'haha'
    CALLBACK_NAME = 'haha'

    # only needed if you ship it and don't want to enable by default
    CALLBACK_NEEDS_ENABLED = False
    
    def __init__(self):
        # make sure the expected objects are present, calling the base's __init__
        super(CallbackModule, self).__init__()
        self.config = self._load_config() 
        self.syslog_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.alert_levels=dict(
            ok='LOG_INFO',
            failures='LOG_ERR',
            unreachable='LOG_EMERG',
            changed='LOG_INFO',
            skipped='LOG_NOTICE',
            rescued='LOG_NOTICE',
            ignored='LOG_NOTICE'
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
        try:
            cl=self.__class__
            hosts = sorted(stats.processed.keys())
            if not hosts: #Needed?
                return
            for host in hosts:
                for msgk, msgv in stats.summarize(host).items():
                    if msgv:
                        msg=f'{self._playbook_name} {host} {msgv} {msgk}'
                        level=self.alert_levels[msgk]
                        self._send_to_syslog(level, msg)
        except Exception as e:
            self._send_to_syslog('LOG_ALERT', e.__class__.__name__)
            for arg in e.args:
                self._send_to_syslog('LOG_ALERT', arg)

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
        self._playbook_name = os.path.basename(playbook._file_name)


    def __del__(self):
        """
        Clean up socket connection
        """
        if self.syslog_socket:
            self.syslog_socket.close()

if __name__=='__main__':
    
    tst=CallbackModule()
    tst.v2_playbook_on_stats(stats)
