import unittest

import client
import server


class Sprint3MasterTests(unittest.TestCase):
    def test_parse_peer_masters_from_env_format(self):
        peers = server.parse_peer_masters("Master_B@127.0.0.1:8001,Master_C@10.0.0.2:9000")

        self.assertEqual(
            peers,
            {
                "Master_B": ("127.0.0.1", 8001),
                "Master_C": ("10.0.0.2", 9000),
            },
        )

    def test_build_initial_tasks_uses_configured_count(self):
        self.assertEqual(server.build_initial_tasks(0), [])
        self.assertEqual(server.build_initial_tasks(3), ["TAREFA1", "TAREFA2", "TAREFA3"])

    def test_validate_master_message_requires_type_request_id_and_payload(self):
        message_type, request_id, payload = server.validate_master_message(
            {
                "type": "request_help",
                "request_id": "req-1",
                "payload": {"workers_needed": 2},
                "ignored": "future-extension",
            }
        )

        self.assertEqual(message_type, "request_help")
        self.assertEqual(request_id, "req-1")
        self.assertEqual(payload, {"workers_needed": 2})

    def test_request_help_is_accepted_when_local_workers_are_available(self):
        state = server.MasterState(
            master_uuid="Master_B",
            peers={},
            capacity=10,
            release_threshold=4,
            task_queue=[],
        )
        state.register_local_worker("B1")
        state.register_local_worker("B2")

        response = server.handle_request_help_message(
            state,
            "req-accepted",
            {
                "master_id": "Master_A",
                "current_load": 15,
                "capacity": 10,
                "workers_needed": 2,
                "return_address": "127.0.0.1:8000",
            },
        )

        self.assertEqual(response["type"], "response_accepted")
        self.assertEqual(response["request_id"], "req-accepted")
        self.assertEqual(response["payload"]["workers_offered"], 2)
        self.assertEqual([w["id"] for w in response["payload"]["worker_details"]], ["B1", "B2"])
        self.assertEqual(state.pending_redirects["B1"]["new_master_address"], "127.0.0.1:8000")

    def test_request_help_is_rejected_when_no_workers_available(self):
        state = server.MasterState(
            master_uuid="Master_B",
            peers={},
            capacity=10,
            release_threshold=4,
            task_queue=[],
        )

        response = server.handle_request_help_message(
            state,
            "req-rejected",
            {
                "master_id": "Master_A",
                "current_load": 15,
                "capacity": 10,
                "workers_needed": 1,
            },
        )

        self.assertEqual(response["type"], "response_rejected")
        self.assertEqual(response["request_id"], "req-rejected")
        self.assertEqual(response["payload"]["reason"], "no_workers_available")

    def test_register_temporary_worker_records_origin(self):
        state = server.MasterState(
            master_uuid="Master_A",
            peers={"Master_B": ("127.0.0.1", 8001)},
            capacity=10,
            release_threshold=4,
            task_queue=[],
        )

        response = server.handle_register_temporary_worker_message(
            state,
            "req-register",
            {"worker_id": "B1", "original_master_address": "127.0.0.1:8001"},
        )

        self.assertEqual(response["type"], "register_temporary_worker_ack")
        self.assertEqual(response["request_id"], "req-register")
        self.assertEqual(state.borrowed_workers["B1"]["original_master_address"], "127.0.0.1:8001")

    def test_command_release_is_queued_for_borrowed_worker_below_threshold(self):
        state = server.MasterState(
            master_uuid="Master_A",
            peers={},
            capacity=10,
            release_threshold=4,
            task_queue=[],
        )
        state.borrowed_workers["B1"] = {"original_master_address": "127.0.0.1:8001"}

        queued = server.queue_releases_if_needed(state)

        self.assertEqual(queued, ["B1"])
        self.assertEqual(state.pending_releases["B1"]["original_master_address"], "127.0.0.1:8001")

    def test_task_moves_from_pending_to_in_progress_to_done(self):
        state = server.MasterState(
            master_uuid="Master_A",
            peers={},
            capacity=10,
            release_threshold=4,
            task_queue=["Task1"],
        )

        assigned = state.assign_next_task("W-1")
        self.assertEqual(assigned, "Task1")
        self.assertEqual(state.tasks_pending, [])
        self.assertEqual(state.tasks_in_progress, {"W-1": "Task1"})

        state.complete_worker_task("W-1", "OK")

        self.assertEqual(state.tasks_in_progress, {})
        self.assertEqual(
            state.tasks_done,
            [{"worker_uuid": "W-1", "task": "Task1", "status": "OK"}],
        )

    def test_worker_disconnect_requeues_in_progress_task(self):
        state = server.MasterState(
            master_uuid="Master_A",
            peers={},
            capacity=10,
            release_threshold=4,
            task_queue=["Task1", "Task2"],
        )

        state.assign_next_task("W-1")
        requeued = state.requeue_worker_task("W-1")

        self.assertEqual(requeued, "Task1")
        self.assertEqual(state.tasks_pending, ["Task1", "Task2"])
        self.assertEqual(state.tasks_in_progress, {})
        self.assertNotIn("W-1", state.busy_workers)

    def test_saturated_master_negotiates_help_without_worker_presentation(self):
        state = server.MasterState(
            master_uuid="Master_A",
            peers={"Master_B": ("127.0.0.1", 8001)},
            capacity=1,
            release_threshold=0,
            task_queue=["Task1", "Task2", "Task3"],
        )
        calls = []

        def fake_requester(peer_id, peer_address, current_load, workers_needed):
            calls.append((peer_id, peer_address, current_load, workers_needed))
            return {"type": "response_accepted", "request_id": "req-1", "payload": {"workers_offered": 1}}

        negotiated = server.negotiate_help_if_saturated(state, fake_requester)

        self.assertTrue(negotiated)
        self.assertEqual(calls, [("Master_B", ("127.0.0.1", 8001), 3, 2)])
        self.assertTrue(state.help_request_pending)


class Sprint3WorkerTests(unittest.TestCase):
    def test_worker_redirect_switches_current_master_and_marks_origin(self):
        state = client.WorkerState(
            worker_id="B1",
            original_master_host="127.0.0.1",
            original_master_port=8001,
        )

        register_payload = client.apply_command_redirect(
            state,
            {
                "new_master_address": "127.0.0.1:8000",
                "original_master_address": "127.0.0.1:8001",
            },
        )

        self.assertEqual((state.current_master_host, state.current_master_port), ("127.0.0.1", 8000))
        self.assertEqual(state.origin_server_uuid, "127.0.0.1:8001")
        self.assertEqual(register_payload["type"], "register_temporary_worker")
        self.assertEqual(register_payload["payload"]["worker_id"], "B1")

    def test_worker_release_returns_to_original_master(self):
        state = client.WorkerState(
            worker_id="B1",
            original_master_host="127.0.0.1",
            original_master_port=8001,
        )
        client.apply_command_redirect(
            state,
            {
                "new_master_address": "127.0.0.1:8000",
                "original_master_address": "127.0.0.1:8001",
            },
        )

        client.apply_command_release(state, {"original_master_address": "127.0.0.1:8001"})

        self.assertEqual((state.current_master_host, state.current_master_port), ("127.0.0.1", 8001))
        self.assertIsNone(state.origin_server_uuid)


if __name__ == "__main__":
    unittest.main()
