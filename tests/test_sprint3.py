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

    def test_request_help_accepts_uppercase_external_payload_aliases(self):
        state = server.MasterState(
            master_uuid="Master_B",
            peers={},
            capacity=10,
            release_threshold=4,
            task_queue=[],
        )
        state.register_local_worker("B1")

        response = server.handle_request_help_message(
            state,
            "req-upper",
            {
                "MASTER_ID": "Master_A",
                "CURRENT_LOAD": 15,
                "CAPACITY": 10,
                "WORKERS_NEEDED": 1,
                "RETURN_ADDRESS": "127.0.0.1:8000",
            },
        )

        self.assertEqual(response["type"], "response_accepted")
        self.assertEqual(response["payload"]["workers_offered"], 1)
        self.assertEqual(response["payload"]["WORKERS_OFFERED"], 1)
        self.assertEqual(response["payload"]["WORKER_DETAILS"], [{"ID": "B1", "ADDRESS": "dynamic"}])
        self.assertEqual(state.pending_redirects["B1"]["new_master_address"], "127.0.0.1:8000")

    def test_request_help_without_return_address_uses_configured_peer_address(self):
        state = server.MasterState(
            master_uuid="Master_B",
            peers={"Master_A": ("127.0.0.1", 8000)},
            capacity=10,
            release_threshold=4,
            task_queue=[],
        )
        state.register_local_worker("B1")

        server.handle_request_help_message(
            state,
            "req-peer-fallback",
            {
                "MASTER_ID": "Master_A",
                "CURRENT_LOAD": 15,
                "CAPACITY": 10,
                "WORKERS_NEEDED": 1,
            },
        )

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

    def test_register_temporary_worker_updates_origin_address_after_heartbeat(self):
        state = server.MasterState(
            master_uuid="Master_A",
            peers={"Master_B": ("127.0.0.1", 8001)},
            capacity=10,
            release_threshold=4,
            task_queue=[],
        )
        server.handle_heartbeat_message(
            state,
            "req-heartbeat",
            {"WORKER_UUID": "B1", "SERVER_UUID": "Master_B"},
        )

        server.handle_register_temporary_worker_message(
            state,
            "req-register",
            {"worker_id": "B1", "original_master_address": "127.0.0.1:8001"},
        )

        self.assertEqual(state.borrowed_workers["B1"]["original_master_address"], "127.0.0.1:8001")

    def test_register_temporary_worker_accepts_uppercase_external_payload_aliases(self):
        state = server.MasterState(
            master_uuid="Master_A",
            peers={},
            capacity=10,
            release_threshold=4,
            task_queue=[],
        )

        response = server.handle_register_temporary_worker_message(
            state,
            "req-register-upper",
            {"WORKER_ID": "B1", "ORIGINAL_MASTER_ADDRESS": "127.0.0.1:8001"},
        )

        self.assertEqual(response["type"], "register_temporary_worker_ack")
        self.assertEqual(response["payload"]["worker_id"], "B1")
        self.assertEqual(response["payload"]["WORKER_ID"], "B1")
        self.assertEqual(state.borrowed_workers["B1"]["original_master_address"], "127.0.0.1:8001")

    def test_notify_worker_returned_accepts_uppercase_external_payload_aliases(self):
        state = server.MasterState(
            master_uuid="Master_B",
            peers={},
            capacity=10,
            release_threshold=4,
            task_queue=[],
        )
        state.lent_workers["B1"] = {"borrower": "Master_A"}
        state.pending_redirects["B1"] = {"new_master_address": "127.0.0.1:8000"}

        response = server.handle_notify_worker_returned_message(
            state,
            "req-returned-upper",
            {"WORKER_ID": "B1"},
        )

        self.assertEqual(response["type"], "notify_worker_returned_ack")
        self.assertEqual(response["payload"]["WORKER_ID"], "B1")
        self.assertNotIn("B1", state.lent_workers)
        self.assertNotIn("B1", state.pending_redirects)

    def test_notify_worker_dead_accepts_uppercase_external_payload_aliases(self):
        state = server.MasterState(
            master_uuid="Master_B",
            peers={},
            capacity=10,
            release_threshold=4,
            task_queue=[],
        )
        state.lent_workers["B1"] = {"borrower": "Master_A"}
        state.pending_redirects["B1"] = {"new_master_address": "127.0.0.1:8000"}

        response = server.handle_notify_worker_dead_message(
            state,
            "req-dead-upper",
            {"WORKER_ID": "B1", "SOURCE_SERVER": "Master_A"},
        )

        self.assertEqual(response["type"], "notify_worker_dead_ack")
        self.assertEqual(response["payload"]["worker_id"], "B1")
        self.assertNotIn("B1", state.lent_workers)
        self.assertNotIn("B1", state.pending_redirects)

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

    def test_heartbeat_with_origin_records_borrowed_worker_not_local(self):
        state = server.MasterState(
            master_uuid="Master_A",
            peers={},
            capacity=10,
            release_threshold=4,
            task_queue=[],
        )
        state.register_local_worker("B1")

        response = server.handle_heartbeat_message(
            state,
            "req-heartbeat",
            {"WORKER_UUID": "B1", "SERVER_UUID": "Master_B"},
        )

        self.assertEqual(response["type"], "heartbeat_ack")
        self.assertNotIn("B1", state.local_workers)
        self.assertIn("B1", state.borrowed_workers)
        self.assertEqual(state.borrowed_workers["B1"]["original_master_address"], "Master_B")

    def test_borrowed_worker_gets_release_before_new_task_when_load_is_below_threshold(self):
        original_state = server.master_state
        original_notify = server.notify_worker_returned
        state = server.MasterState(
            master_uuid="Master_A",
            peers={},
            capacity=10,
            release_threshold=2,
            task_queue=["Task1"],
        )
        state.borrowed_workers["B1"] = {"original_master_address": "127.0.0.1:8001"}
        notified = []

        class FakeConn:
            def __init__(self):
                self.sent = []

            def sendall(self, data):
                self.sent.append(data)

        conn = FakeConn()

        try:
            server.master_state = state
            server.notify_worker_returned = lambda address, worker_id: notified.append((address, worker_id))
            worker_uuid, task = server.handle_worker_presentation(
                conn,
                {"WORKER": "ALIVE", "WORKER_UUID": "B1", "SERVER_UUID": "Master_B"},
            )
        finally:
            server.master_state = original_state
            server.notify_worker_returned = original_notify

        response = server.parse_json_message(conn.sent[0].decode().strip())
        self.assertEqual(worker_uuid, "B1")
        self.assertIsNone(task)
        self.assertEqual(response["type"], "command_release")
        self.assertEqual(response["payload"]["original_master_address"], "127.0.0.1:8001")
        self.assertEqual(notified, [("127.0.0.1:8001", "B1")])
        self.assertNotIn("B1", state.borrowed_workers)
        self.assertNotIn("B1", state.worker_heartbeats)
        self.assertEqual(state.tasks_pending, ["Task1"])

    def test_released_borrowed_worker_is_not_later_marked_dead_by_receiver(self):
        original_state = server.master_state
        original_notify = server.notify_worker_returned
        state = server.MasterState(
            master_uuid="Master_A",
            peers={},
            capacity=10,
            release_threshold=2,
            task_queue=[],
        )
        state.borrowed_workers["B1"] = {"original_master_address": "127.0.0.1:8001"}
        state.update_worker_heartbeat("B1", "Master_B")

        class FakeConn:
            def __init__(self):
                self.sent = []

            def sendall(self, data):
                self.sent.append(data)

        try:
            server.master_state = state
            server.notify_worker_returned = lambda address, worker_id: None
            server.handle_worker_presentation(
                FakeConn(),
                {"WORKER": "ALIVE", "WORKER_UUID": "B1", "SERVER_UUID": "Master_B"},
            )
        finally:
            server.master_state = original_state
            server.notify_worker_returned = original_notify

        expired = server.collect_expired_workers(
            state,
            now=9999999999.0,
            heartbeat_timeout=1,
            max_missed=1,
        )

        self.assertEqual(expired, [])
        self.assertEqual(state.worker_failures, 0)

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

    def test_lent_worker_is_not_expired_by_origin_master_heartbeat_monitor(self):
        state = server.MasterState(
            master_uuid="Master_B",
            peers={},
            capacity=10,
            release_threshold=4,
            task_queue=[],
        )
        state.register_local_worker("B1")
        state.update_worker_heartbeat("B1")
        with state.lock:
            state.lent_workers["B1"] = {
                "borrower": "Master_A",
                "new_master_address": "192.168.1.141:8000",
            }
            state.worker_heartbeats["B1"]["last_heartbeat"] = 100.0

        expired = server.collect_expired_workers(state, now=200.0, heartbeat_timeout=8, max_missed=3)

        self.assertEqual(expired, [])
        self.assertEqual(state.worker_heartbeats["B1"]["missed_intervals"], 0)
        self.assertIn("B1", state.lent_workers)

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

    def test_command_redirect_payload_includes_original_master_id(self):
        original_state = server.master_state
        state = server.MasterState(
            master_uuid="Master_B",
            peers={},
            capacity=10,
            release_threshold=4,
            task_queue=[],
        )
        state.pending_redirects["B1"] = {
            "new_master_address": "127.0.0.1:8000",
            "requester": "Master_A",
        }

        class FakeConn:
            def __init__(self):
                self.sent = []

            def sendall(self, data):
                self.sent.append(data)

        conn = FakeConn()

        try:
            server.master_state = state
            worker_uuid, task = server.handle_worker_presentation(
                conn,
                {"WORKER": "ALIVE", "WORKER_UUID": "B1"},
            )
        finally:
            server.master_state = original_state

        response = server.parse_json_message(conn.sent[0].decode().strip())
        self.assertEqual(worker_uuid, "B1")
        self.assertIsNone(task)
        self.assertEqual(response["type"], "command_redirect")
        self.assertEqual(response["payload"]["new_master_address"], "127.0.0.1:8000")
        self.assertEqual(response["payload"]["original_master_id"], "Master_B")
        self.assertEqual(response["payload"]["NEW_MASTER_ADDRESS"], "127.0.0.1:8000")
        self.assertEqual(response["payload"]["ORIGINAL_MASTER_ID"], "Master_B")


class Sprint3WorkerTests(unittest.TestCase):
    def test_worker_redirect_accepts_uppercase_external_payload_aliases(self):
        state = client.WorkerState(
            worker_id="B1",
            original_master_host="127.0.0.1",
            original_master_port=8001,
        )

        register_payload = client.apply_command_redirect(
            state,
            {
                "NEW_MASTER_ADDRESS": "127.0.0.1:8000",
                "ORIGINAL_MASTER_ADDRESS": "127.0.0.1:8001",
                "ORIGINAL_MASTER_ID": "Master_B",
            },
        )

        self.assertEqual((state.current_master_host, state.current_master_port), ("127.0.0.1", 8000))
        self.assertEqual(state.origin_server_uuid, "Master_B")
        self.assertEqual(register_payload["payload"]["original_master_address"], "127.0.0.1:8001")

    def test_worker_redirect_prefers_original_master_id_for_server_uuid(self):
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
                "original_master_id": "Master_B",
            },
        )

        presentation = client.build_worker_presentation_payload(state)

        self.assertEqual(state.origin_server_uuid, "Master_B")
        self.assertEqual(presentation["SERVER_UUID"], "Master_B")

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

    def test_worker_presentation_after_redirect_uses_origin_fallback(self):
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

        presentation = client.build_worker_presentation_payload(state)

        self.assertEqual(
            presentation,
            {
                "WORKER": "ALIVE",
                "WORKER_UUID": "B1",
                "SERVER_UUID": "127.0.0.1:8001",
            },
        )

    def test_register_temporary_worker_ack_failure_is_non_fatal(self):
        state = client.WorkerState(
            worker_id="B1",
            original_master_host="127.0.0.1",
            original_master_port=8001,
            current_master_host="127.0.0.1",
            current_master_port=8000,
            origin_server_uuid="Master_B",
        )

        class ClosingSocket:
            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, traceback):
                return False

            def settimeout(self, timeout):
                self.timeout = timeout

            def sendall(self, data):
                self.sent = data

            def recv(self, size):
                return b""

        def fake_connector(address, timeout):
            return ClosingSocket()

        registered = client.register_temporary_worker_best_effort(
            state,
            connector=fake_connector,
            logger=lambda level, message: None,
        )

        self.assertFalse(registered)
        self.assertEqual((state.current_master_host, state.current_master_port), ("127.0.0.1", 8000))
        self.assertEqual(state.origin_server_uuid, "Master_B")

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

    def test_worker_release_accepts_uppercase_external_payload_aliases(self):
        state = client.WorkerState(
            worker_id="B1",
            original_master_host="127.0.0.1",
            original_master_port=8001,
            current_master_host="127.0.0.1",
            current_master_port=8000,
            origin_server_uuid="Master_B",
        )

        client.apply_command_release(state, {"ORIGINAL_MASTER_ADDRESS": "127.0.0.1:8001"})

        self.assertEqual((state.current_master_host, state.current_master_port), ("127.0.0.1", 8001))
        self.assertIsNone(state.origin_server_uuid)


if __name__ == "__main__":
    unittest.main()
