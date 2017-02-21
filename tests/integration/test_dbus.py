#!/usr/bin/env python
#pylint: skip-file

import dbus
import sys
import subprocess
try:
    from slip.dbus import polkit
except ImportError:
    sys.exit(77)
import dbus.service
import dbus.mainloop.glib
import json

_integration_test_serial = 0

clean_up_tasks = []

# Throw this error to signify at test failure
class AtomicIntegrationTestError(Exception):
    def __init__(self, test_name, error):
        super(AtomicIntegrationTestError, self).__init__("Test '{}' Failed... due to {}".format(test_name, error))


def integration_test(func):
    global _integration_test_serial
    func._integration_test_serial = _integration_test_serial
    _integration_test_serial += 1
    return func


class TestDBus():

    def __init__(self):
        self.bus = dbus.SystemBus()
        self.dbus_object = self.bus.get_object("org.atomic", "/org/atomic/object")
        self.cid = None

    @staticmethod
    def run_cmd(cmd):
        if not isinstance(cmd, list):
            cmd = cmd.split()
        return subprocess.check_output(cmd)

    @staticmethod
    def add_cleanup_cmd(cmd):
        assert(isinstance(cmd, str))
        clean_up_tasks.append(cmd.split())

    @staticmethod
    def remove_cleanup_cmd(cmd):
        assert(isinstance(cmd, str))
        clean_up_tasks.remove(cmd.split())

    @staticmethod
    def cleanup():
        for task in clean_up_tasks:
            print("Running clean up: {}".format(" ".join(task)))
            TestDBus.run_cmd(task)

    # Add this decorator to define the method as something that should be
    # tested

    @integration_test
    def test_scan_list(self):
        results = self.dbus_object.ScanList()
        assert(isinstance(results, dbus.String))

    @integration_test
    def test_pull(self):
        TestDBus.add_cleanup_cmd('docker rmi docker.io/library/busybox:1.24')
        assert(self.dbus_object.ImagePull('docker.io/library/busybox:1.24') == 0)

    @integration_test
    def test_pull_bad_image(self):
        try:
            self.dbus_object.ImagePull('docker.io/library/foobar:1234')
            raise ValueError("This test should have resulted in an exception")
        except dbus.DBusException:
            pass

    @integration_test
    def test_update(self):
        TestDBus.add_cleanup_cmd('docker rmi docker.io/busybox:latest')
        self.run_cmd(['docker', 'tag', 'docker.io/library/busybox:1.24', 'docker.io/library/busybox:latest'])
        assert(self.dbus_object.ImageUpdate('docker.io/library/busybox:latest') ==  0)


    @integration_test
    def test_update_already_present(self):
        try:
            self.dbus_object.ImageUpdate('docker.io/library/busybox:latest')
            raise ValueError("This test should have resulted in an exception")
        except dbus.DBusException:
            pass


    @integration_test
    def test_pull_already_present(self):
        try:
            self.dbus_object.ImagePull('docker.io/library/busybox:latest')
            raise ValueError("This should have resulted in an exception")
        except dbus.DBusException:
            pass
    @integration_test
    def test_run(self):
        self.dbus_object.Run('atomic-test-3', name='atomic-dbus-3')
        self.cid = TestDBus.run_cmd('docker ps -aq -l').decode('utf-8').rstrip()
        TestDBus.add_cleanup_cmd('docker rm {}'.format(self.cid))
        container_inspect = json.loads(TestDBus.run_cmd('docker inspect {}'.format(self.cid)).decode('utf-8'))[0]
        assert(container_inspect['Name'] == '/atomic-test-3')

    @integration_test
    def test_container_delete(self):
        self.dbus_object.ContainersDelete([self.cid])
        TestDBus.remove_cleanup_cmd('docker rm {}'.format(self.cid))


    @integration_test
    def test_container_delete_nonexistent(self):
        try:
            self.dbus_object.ContainersDelete([self.cid])
            raise ValueError("Expected an exception to be raised and was not.")
        except dbus.DBusException:
            pass

    @integration_test
    def test_push(self):
        TestDBus.run_cmd('docker pull docker.io/alpine:latest')
        TestDBus.run_cmd('docker tag docker.io/alpine:latest localhost:5000/alpine:latest')
        TestDBus.run_cmd('docker run -d -p 5000:5000 --restart=always --name registry docker.io/registry:2')
        registry_cid = TestDBus.run_cmd('docker ps -aq -l').decode('utf-8').rstrip()
        TestDBus.add_cleanup_cmd('docker rm -f {}'.format(registry_cid))
        TestDBus.add_cleanup_cmd('docker rmi docker.io/registry:2')
        TestDBus.add_cleanup_cmd('docker rmi docker.io/alpine:latest')
        TestDBus.add_cleanup_cmd('docker rmi localhost:5000/alpine:latest')
        results = self.dbus_object.ImagePush("localhost:5000/alpine:latest", False, False, False, "", "foo", "bar", "", "", "", "", "")
        assert(results == 0)

    @integration_test
    def test_push_no_password(self):
        try:
            self.dbus_object.ImagePush("localhost:5000/alpine:latest", False, False, False, "", "foo", "", "", "", "", "", "")
            raise ValueError("Expected an exception to be raised and was not.")
        except dbus.DBusException:
            pass

    @integration_test
    def test_push_no_username(self):
        try:
            self.dbus_object.ImagePush("localhost:5000/alpine:latest", False, False, False, "", "", "", "", "", "", "", "")
            raise ValueError("Expected an exception to be raised and was not.")
        except dbus.DBusException:
            pass

    @integration_test
    def test_push_pulp_no_username(self):
        try:
            self.dbus_object.ImagePush("localhost:5000/alpine:latest", True, False, False, "url", "", "", "", "", "", "", "")
            raise ValueError("Expected an exception to be raised and was not.")
        except dbus.DBusException:
            pass

    @integration_test
    def test_push_pulp_no_url(self):
        try:
            self.dbus_object.ImagePush("localhost:5000/alpine:latest", True, False, False, "", "foo", "bar", "", "", "", "", "")
            raise ValueError("Expected an exception to be raised and was not.")
        except dbus.DBusException:
            pass
if __name__ == '__main__':

    #tb = TestDBus()
    #method = getattr(tb, 'test_scan_list')


    def get_test_methods(_tb):
        """
        Returns the test methods from above that have the integration_test decorator
        :param _tb: TestDbus instance
        """
        method_names = (n for n in dir(_tb) if not n.startswith('__') and
                        callable(getattr(_tb, n)))
        methods_and_names = ((getattr(_tb, n), n) for n in method_names)

        test_method_names_order = (
            (x[1], getattr(x[0], '_integration_test_serial'))
            for x in methods_and_names
            if '_integration_test_serial' in dir(x[0]))
        test_method_names_ordered = [x[0] for x in
                                     sorted(test_method_names_order,
                                            key=lambda x: x[1])]

        return test_method_names_ordered

    tb = TestDBus()
    test_methods = get_test_methods(tb)
    for test in test_methods:
        _tb = getattr(tb, test)
        try:
            _tb()
        except ValueError as e:
            tb.cleanup()
            raise AtomicIntegrationTestError(test, e)

        print("Test '{}' passed.".format(test))

    tb.cleanup()