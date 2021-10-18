# ############################################################################### #
# Autoreduction Repository : https://github.com/ISISScientificComputing/autoreduce
#
# Copyright &copy; 2021 ISIS Rutherford Appleton Laboratory UKRI
# SPDX - License - Identifier: GPL-3.0-or-later
# ############################################################################### #
"""Test cases for submitting batch runs."""
# pylint:disable=no-member
import os
from unittest.mock import Mock, patch

from django.contrib.auth import get_user_model
from django.test import LiveServerTestCase
import requests
from rest_framework.authtoken.models import Token

from autoreduce_db.reduction_viewer.models import ReductionRun
from autoreduce_qp.queue_processor.queue_listener import setup_connection
from autoreduce_utils.clients.connection_exception import ConnectionException
from autoreduce_utils.settings import SCRIPTS_DIRECTORY
from autoreduce_rest_api.runs.test.test_submit_runs import wait_until

INSTRUMENT_NAME = "TESTINSTRUMENT"


class SubmitBatchRunsTest(LiveServerTestCase):
    fixtures = ["autoreduce_rest_api/autoreduce_django/fixtures/super_user_fixture.json"]

    @classmethod
    def setUpClass(cls) -> None:

        os.makedirs(SCRIPTS_DIRECTORY % INSTRUMENT_NAME, exist_ok=True)
        with open(os.path.join(SCRIPTS_DIRECTORY % INSTRUMENT_NAME, "reduce_vars.py"), 'w') as file:
            file.write("")

        return super().setUpClass()

    def setUp(self) -> None:
        try:
            self.queue_client, self.listener = setup_connection()
        except ConnectionException as err:
            raise RuntimeError("Could not connect to ActiveMQ - check your credentials. If running locally check that "
                               "ActiveMQ Docker container is running and started") from err
        user = get_user_model()
        self.token = Token.objects.create(user=user.objects.first())
        return super().setUp()

    @patch("autoreduce_scripts.manual_operations.manual_submission.get_run_data_from_icat",
           return_value=["/tmp/location", "RB1234567", "test_title"])
    def test_batch_submit_and_delete_run(self, get_run_data_from_icat: Mock):
        """Submit and delete a run range via the API."""
        response = requests.post(f"{self.live_server_url}/api/runs/batch/{INSTRUMENT_NAME}",
                                 headers={"Authorization": f"Token {self.token}"},
                                 json={
                                     "runs": [63125, 63130],
                                     "reduction_arguments": {
                                         "apple": "banana"
                                     },
                                     "user_id": 99199,
                                     "description": "Test description"
                                 })
        assert response.status_code == 200
        assert wait_until(lambda: ReductionRun.objects.count() == 1)
        assert get_run_data_from_icat.call_count == 2
        get_run_data_from_icat.reset_mock()

        reduced_run = ReductionRun.objects.first()
        assert reduced_run.started_by == 99199
        assert reduced_run.run_description == "Test description"

        response = requests.delete(f"{self.live_server_url}/api/runs/batch/{INSTRUMENT_NAME}",
                                   json={"runs": [reduced_run.pk]},
                                   headers={"Authorization": f"Token {self.token}"})
        assert response.status_code == 200
        assert wait_until(lambda: ReductionRun.objects.count() == 0)
        get_run_data_from_icat.assert_not_called()