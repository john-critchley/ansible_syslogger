#!/usr/bin/env python3
"""
Test script for the syslog callback module
This allows you to test the callback functionality without running Ansible
"""

import sys
import os
from collections import namedtuple

# Mock Ansible objects for testing
class MockHost:
    def __init__(self, name):
        self.name = name
    
    def get_name(self):
        return self.name

class MockTask:
    def __init__(self, name):
        self.name = name
    
    def get_name(self):
        return self.name

class MockPlay:
    def __init__(self, name):
        self.name = name
    
    def get_name(self):
        return self.name

class MockResult:
    def __init__(self, host_name, task_name, result_dict=None):
        self._host = MockHost(host_name)
        self._task = MockTask(task_name)
        self._result = result_dict or {}

# Mock Ansible stats object for testing
class MockStats:
    def __init__(self):
        self.processed = {
            'host1': True,
            'host2': True,
            'host3': True
        }
    
    def summarize(self, host):
        # Return different combinations for testing
        if host == 'host1':
            return {'ok': 5, 'changed': 2, 'failures': 0, 'unreachable': 0, 'skipped': 1, 'rescued': 0, 'ignored': 0}
        elif host == 'host2':
            return {'ok': 3, 'changed': 0, 'failures': 1, 'unreachable': 0, 'skipped': 0, 'rescued': 1, 'ignored': 0}
        else:
            return {'ok': 2, 'changed': 1, 'failures': 0, 'unreachable': 1, 'skipped': 0, 'rescued': 0, 'ignored': 1}

# Mock playbook object
class MockPlaybook:
    def __init__(self):
        self._file_name = '/path/to/test_playbook.yml'

def test_callback():
    """Test the callback module"""
    try:
        # Import the callback module
        from syslog_callback import CallbackModule
        
        print("Testing syslog callback module...")
        print("=" * 50)
        
        # Create callback instance
        callback = CallbackModule()
        
        # Test configuration
        print(f"Syslog host: {callback.config.syslog_host}")
        print(f"Syslog port: {callback.config.syslog_port}")
        print(f"Syslog facility: {callback.config.syslog_facility}")
        print(f"Tag: {callback.config.tag}")
        print()
        
        # Test make_priority function
        print("Testing make_priority function:")
        print(f"Priority for facility='user', level=6: {callback.make_priority('user', 6)}")
        print(f"Priority for facility=1, level=3: {callback.make_priority(1, 3)}")
        print()
        
        # Test playbook start
        playbook = MockPlaybook()
        callback.v2_playbook_on_start(playbook)
        print(f"Playbook name set to: {callback._playbook_name}")
        print()
        
        # Test play start
        print("Testing play start:")
        play = MockPlay("Test Play - Setup servers")
        callback.v2_playbook_on_play_start(play)
        print("Play start test completed!")
        print()
        
        # Test individual task callbacks
        print("Testing individual task event callbacks:")
        
        # Test successful task
        print("  - Testing successful task...")
        ok_result = MockResult("web01", "Install nginx")
        callback.v2_runner_on_ok(ok_result)
        
        # Test changed task
        print("  - Testing changed task...")
        changed_result = MockResult("web01", "Update nginx config")
        callback.v2_runner_on_changed(changed_result)
        
        # Test failed task
        print("  - Testing failed task...")
        failed_result = MockResult("db01", "Start database", {"msg": "Service startup failed"})
        callback.v2_runner_on_failed(failed_result)
        
        # Test unreachable host
        print("  - Testing unreachable host...")
        unreachable_result = MockResult("web03", "Ping test", {"msg": "Connection timeout"})
        callback.v2_runner_on_unreachable(unreachable_result)
        
        # Test skipped task
        print("  - Testing skipped task...")
        skipped_result = MockResult("web02", "Install debug tools", {"skip_reason": "Not in debug mode"})
        callback.v2_runner_on_skipped(skipped_result)
        
        # Test task with retry
        print("  - Testing task retry...")
        retry_result = MockResult("app01", "Download package", {"retries": 2})
        callback.v2_runner_retry(retry_result)
        
        # Test loop items
        print("  - Testing loop item callbacks...")
        item_ok_result = MockResult("web01", "Install packages", {"item": "nginx"})
        callback.v2_runner_item_on_ok(item_ok_result)
        
        item_failed_result = MockResult("web01", "Install packages", {"item": "mysql-server", "msg": "Package not found"})
        callback.v2_runner_item_on_failed(item_failed_result)
        
        item_skipped_result = MockResult("web01", "Install packages", {"item": "debug-tools", "skip_reason": "Not needed"})
        callback.v2_runner_item_on_skipped(item_skipped_result)
        
        # Test task start
        print("  - Testing task start...")
        task = MockTask("Configure firewall")
        callback.v2_playbook_on_task_start(task, False)
        
        print("Individual task callback tests completed!")
        print()
        
        # Test stats processing
        print("Testing stats processing (summary at end):")
        stats = MockStats()
        callback.v2_playbook_on_stats(stats)
        print("Stats processing completed!")
        print()
        
        # Test error handling
        print("Testing error handling:")
        try:
            raise ValueError("Test error for logging")
        except Exception as e:
            callback._send_to_syslog(callback.syslog_levels.LOG_ALERT, f"Test error: {str(e)}")
        print("Error handling test completed!")
        
    except ImportError as e:
        print(f"Error importing syslog_callback: {e}")
        print("Make sure the syslog_callback.py file is in the same directory")
    except Exception as e:
        print(f"Error running test: {e}")
        import traceback
        traceback.print_exc()

if __name__ == '__main__':
    print("Syslog Callback Test Script")
    print("This script tests the syslog callback functionality")
    print("Make sure you have a syslog server running on localhost:10514")
    print("Or set environment variables:")
    print("  ANSIBLE_SYSLOG_HOST=your_syslog_host")
    print("  ANSIBLE_SYSLOG_PORT=your_syslog_port")
    print()
    
    # Show current environment variables
    syslog_vars = {k: v for k, v in os.environ.items() if k.startswith('ANSIBLE_SYSLOG')}
    if syslog_vars:
        print("Current syslog environment variables:")
        for k, v in syslog_vars.items():
            print(f"  {k}={v}")
        print()
    
    test_callback()
