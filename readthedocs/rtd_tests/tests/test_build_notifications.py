# -*- coding: utf-8 -*-
"""Notifications sent after build is completed."""

from __future__ import (
    absolute_import, division, print_function, unicode_literals)

import django_dynamic_fixture as fixture
from django.core import mail
from django.test import TestCase
from mock import patch

from readthedocs.builds.models import Build, Version
from readthedocs.projects.models import Project, EmailHook, WebHook
from readthedocs.projects.tasks import send_notifications, UpdateDocsTask


class BuildNotificationsTests(TestCase):
    def setUp(self):
        self.project = fixture.get(Project)
        self.version = fixture.get(Version, project=self.project)
        self.build = fixture.get(Build, version=self.version)

    def test_send_notification_none(self):
        send_notifications(self.version.pk, self.build.pk)
        self.assertEqual(len(mail.outbox), 0)

    def test_send_webhook_notification(self):
        fixture.get(WebHook, project=self.project)
        with patch('readthedocs.projects.tasks.requests.post') as mock:
            mock.return_value = None
            send_notifications(self.version.pk, self.build.pk)
            mock.assert_called_once()

        self.assertEqual(len(mail.outbox), 0)

    def test_send_email_notification(self):
        fixture.get(EmailHook, project=self.project)
        send_notifications(self.version.pk, self.build.pk)
        self.assertEqual(len(mail.outbox), 1)

    def test_send_email_and_webhook__notification(self):
        fixture.get(EmailHook, project=self.project)
        fixture.get(WebHook, project=self.project)
        with patch('readthedocs.projects.tasks.requests.post') as mock:
            mock.return_value = None
            send_notifications(self.version.pk, self.build.pk)
            mock.assert_called_once()
        self.assertEqual(len(mail.outbox), 1)

    @patch('readthedocs.projects.tasks.UpdateDocsTask.get_project')
    @patch('readthedocs.projects.tasks.UpdateDocsTask.get_version')
    @patch('readthedocs.projects.tasks.UpdateDocsTask.get_build')
    @patch('readthedocs.projects.tasks.UpdateDocsTask.setup_vcs')
    def test_send_email_on_generic_failure_at_setup_vcs(
            self, setup_vcs, get_build, get_version, get_project):
        # TODO: this should be ``_at_run_setup`` but since we depend on
        # ``self.setup_env`` when an exception is raised, we need to raise the
        # exception after this variable is instantiated
        fixture.get(EmailHook, project=self.project)
        build = fixture.get(
            Build,
            project=self.project,
            version=self.project.versions.first(),
        )
        # We force an unhandled raised at ``setup_vcs``
        setup_vcs.side_effect = Exception('Generic exception raised at setup')

        # These mocks are needed at the beginning of the ``.run()`` method
        get_build.return_value = {'id': build.pk}
        get_version.return_value = self.version
        get_project.return_value = self.project

        update_docs = UpdateDocsTask()
        result = update_docs.delay(
            self.project.pk,
            build_pk=build.pk,
            record=False,
            intersphinx=False,
        )
        self.assertTrue(result.successful())
        self.assertFalse(result.result)
        self.assertEqual(len(mail.outbox), 1)
