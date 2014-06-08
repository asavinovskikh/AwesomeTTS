# -*- coding: utf-8 -*-
# pylint:disable=bad-continuation

# AwesomeTTS text-to-speech add-on for Anki
#
# Copyright (C) 2014       Anki AwesomeTTS Development Team
# Copyright (C) 2014       Dave Shifflett
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.

"""
Update detection and callback handling
"""

__all__ = ['Updates']

from PyQt4 import QtCore, QtGui


_SIGNAL_NEED = QtCore.SIGNAL('awesomeTtsUpdateNeeded')
_SIGNAL_GOOD = QtCore.SIGNAL('awesomeTtsUpdateGood')
_SIGNAL_FAIL = QtCore.SIGNAL('awesomeTtsUpdateFailure')


class Updates(QtGui.QWidget):
    """
    Handles managing a thread and executing callbacks when checking for
    updates.
    """

    __slots__ = [
        '_endpoint',      # what URL to check for updates
        '_logger',        # reference to something w/ logging-like interface
        '_callbacks',     # dict lookup of possible callbacks
        '_got_finished',  # True if the worker is "finished"
        '_got_signal',    # True if we've actually gotten a signal back
        '_used',          # True if check() has been called this session
        '_worker',        # reference to the current worker
    ]

    def __init__(self, endpoint, logger):
        """
        Initializes the update checker with the endpoint to use for the
        update check and a logger.
        """

        super(Updates, self).__init__()

        self._used = False

        self._endpoint = endpoint
        self._logger = logger

        self._callbacks = None
        self._got_finished = None
        self._got_signal = None
        self._worker = None

    def check(self, callbacks):
        """
        Runs an update check against web service in a background thread,
        with the following callbacks:

        - done: called as soon as thread finishes
        - fail: called for exceptions or oddities (exception passed)
        - good: called if add-on is up-to-date
        - need: called if update available (version, notes passed)
        - then: called afterward

        The only required callback is 'need', as headless checks are
        free to ignore 'fail' and 'good' and would have no use for
        'done' or 'then'.
        """

        assert 'done' not in callbacks or callable(callbacks['done'])
        assert 'fail' not in callbacks or callable(callbacks['fail'])
        assert 'good' not in callbacks or callable(callbacks['good'])
        assert 'need' in callbacks and callable(callbacks['need'])
        assert 'then' not in callbacks or callable(callbacks['then'])

        self._try_reap()
        if self._worker:
            raise RuntimeError("An update check is already in progress")

        self._used = True
        self._callbacks = callbacks
        self._got_finished = False
        self._got_signal = False
        self._worker = _Worker(self._endpoint, self._logger)

        self.connect(self._worker, _SIGNAL_NEED, self._on_signal_need)
        self.connect(self._worker, _SIGNAL_GOOD, self._on_signal_good)
        self.connect(self._worker, _SIGNAL_FAIL, self._on_signal_fail)
        self._worker.finished.connect(self._on_finished)
        self._worker.start()

        self._logger.debug("Spawned worker to check for updates")

    def used(self):
        """
        Returns True if an update check has been run this session.
        """

        return self._used

    def _on_signal(self, key, *args, **kwargs):
        """
        Called for all signals.

        Does an internal consistency check, calls the 'done' handler (if
        any), the associated handler for the specific signal ('fail',
        'good', or 'need', if any), calls the 'then' handler (if any),
        and finally tries to reap the worker (if possible).

        If the specific signal callback is supposed to take arguments,
        those may be passed after the specific signal's key.
        """

        assert self._worker and not self._got_signal, "already got signal"
        self._got_signal = True

        if 'done' in self._callbacks:
            self._callbacks['done']()

        if key in self._callbacks:
            self._callbacks[key](*args, **kwargs)

        if 'then' in self._callbacks:
            self._callbacks['then']()

        self._try_reap()

    def _on_signal_fail(self, exception=None, stack_trace=None):
        """
        Called when something goes wrong during an update check. This
        can include both things like download errors or successful
        transmission of JSON that has an null value for the update
        status.
        """

        self._logger.error(
            "Exception (%s) during update check\n%s",

            exception.message or "no message",

            "\n".join("!!! " + line for line in stack_trace.split("\n"))
            if isinstance(stack_trace, basestring)
            else "Stack trace unavailable",
        )

        self._on_signal('fail', exception)

    def _on_signal_good(self):
        """
        Called when the worker finds no update information.
        """

        self._logger.info("No updates are available")
        self._on_signal('good')

    def _on_signal_need(self, version, notes):
        """
        Called when the worker finds information about a new version.
        """

        self._logger.warn("Update for %s available" % version)
        self._on_signal('need', version, notes)

    def _on_finished(self):
        """
        Called when the thread is considered "finished", even if a
        signal has not be returned back yet.
        """

        assert self._worker and not self._got_finished, "already finished"
        self._got_finished = True

        self._try_reap()

    def _try_reap(self):
        """
        If our worker has both been reported "finished" and got its
        signal back us, we can reap it. We do not reap it until both of
        these happen, which avoids crashes.
        """

        if self._worker and self._got_finished and self._got_signal:
            self._callbacks = None
            self._got_finished = None
            self._got_signal = None
            self._worker = None

            self._logger.debug("Reaped updates worker")


class _Worker(QtCore.QThread):
    """
    Handles the actual downloading of the JSON payload, parsing it, and
    returning a response to the main thread via a signal.
    """

    __slots__ = [
        '_endpoint',      # what URL to check for updates
        '_logger',        # reference to something w/ logging-like interface
    ]

    def __init__(self, endpoint, logger):
        """
        Initializes the worker with the logger and update endpoint from
        the creating instance.
        """

        super(_Worker, self).__init__()

        self._endpoint = endpoint
        self._logger = logger

    def run(self):
        """
        Attempt to download the JSON payload to check for a new version.
        """

        try:
            self._logger.debug("Downloading JSON from %s", self._endpoint)

            from urllib2 import urlopen
            response = urlopen(self._endpoint, timeout=30)

            if not response or response.getcode() != 200:
                raise IOError("Cannot communicate with update service")
            if response.info().gettype() != 'application/json':
                raise IOError("Update service did not return JSON")

            payload = response.read().strip()
            response.close()
            if not payload:
                raise IOError("Payload not returned from update service")

            from json import loads
            payload = loads(payload)
            if not isinstance(payload, dict):
                raise IOError("Update service did not return an object")

            update = payload.get('update')

            if update == True:
                version = payload.get('version')
                if not isinstance(version, basestring) or not version.strip():
                    raise IOError("No version returned in update object")

                notes = payload.get('notes')
                if not isinstance(notes, basestring) or not notes.strip():
                    raise IOError("No notes returned in update object")

                self.emit(_SIGNAL_NEED, version.strip(), notes.strip())

            elif update == False:
                self.emit(_SIGNAL_GOOD)

            else:
                message = payload.get('message')

                if isinstance(message, basestring) and message.strip():
                    raise EnvironmentError(message)
                else:
                    raise IOError("Update service did not return a status")

        except Exception as exception:  # catch all, pylint:disable=W0703
            from traceback import format_exc
            self.emit(_SIGNAL_FAIL, exception, format_exc())
