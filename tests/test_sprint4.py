import json
import unittest

import server


class Sprint4PayloadTests(unittest.TestCase):
    def build_state(self):
        state = server.MasterState(
            master_uuid="michel_1",
            peers={"michel_2": ("10.0.0.2", 8000)},
            capacity=100,
            release_threshold=60,
            task_queue=["Task1", "Task2"],
        )
        state.register_local_worker("W1")
        state.register_local_worker("W2")
        state.borrowed_workers["B1"] = {
            "original_master_address": "10.0.0.3:8000",
            "registered_at": "2026-06-10T10:00:00",
        }
        state.lent_workers["L1"] = {
            "borrower": "michel_2",
            "new_master_address": "10.0.0.2:8000",
        }
        state.update_worker_heartbeat("W1")
        state.update_worker_heartbeat("W2")
        state.update_worker_heartbeat("B1", "michel_3")
        state.assign_next_task("W1")
        state.complete_worker_task("W1", "OK")
        state.assign_next_task("B1")
        state.tasks_done.append({"worker_uuid": "W2", "task": "OldTask", "status": "NOK"})
        state.worker_failures = 1
        state.peer_status["michel_2"] = {
            "status": "available",
            "last_heartbeat": "2026-06-10T12:00:00Z",
        }
        return state

    def test_supervisor_payload_contains_required_top_level_fields(self):
        state = self.build_state()

        payload = server.build_supervisor_payload(
            state,
            hostname="michel_1.farm.local",
            now=1760000000,
            message_id="msg-1",
        )

        self.assertEqual(payload["server_uuid"], "michel_1")
        self.assertEqual(payload["hostname"], "michel_1.farm.local")
        self.assertEqual(payload["role"], "master")
        self.assertEqual(payload["task"], "performance_report")
        self.assertEqual(payload["timestamp"], "2025-10-09T08:53:20Z")
        self.assertEqual(payload["message_id"], "msg-1")
        self.assertEqual(payload["payload_version"], "sprint4-monitor")
        self.assertIn("system", payload["performance"])
        self.assertIn("farm_state", payload["performance"])
        self.assertIn("config_thresholds", payload["performance"])
        self.assertIn("neighbors", payload["performance"])

    def test_supervisor_payload_reports_farm_state_counters(self):
        state = self.build_state()

        payload = server.build_supervisor_payload(state, hostname="host")
        workers = payload["performance"]["farm_state"]["workers"]
        tasks = payload["performance"]["farm_state"]["tasks"]

        self.assertEqual(workers["total_registered"], 4)
        self.assertEqual(workers["workers_utilization"], 0)
        self.assertEqual(workers["workers_alive"], 3)
        self.assertEqual(workers["workers_idle"], 2)
        self.assertEqual(workers["workers_borrowed"], 1)
        self.assertEqual(workers["workers_received"], 1)
        self.assertEqual(workers["workers_failed"], 1)
        self.assertEqual(workers["workers_home"], 2)
        self.assertEqual(workers["workers_available_capacity"], 2)
        self.assertIn(
            {
                "worker_uuid": "L1",
                "direction": "up",
                "status": "BORROWED_OUT",
                "peer_uuid": "michel_2",
                "parent_uuid": "michel_1",
                "parent_hostname": "michel_1.farm.local",
                "current_master_uuid": "michel_2",
            },
            workers["borrowed_workers"],
        )
        self.assertIn(
            {
                "worker_uuid": "B1",
                "direction": "down",
                "status": "BORROWED_IN",
                "peer_uuid": "michel_3",
                "parent_uuid": "michel_3",
                "parent_hostname": "michel_3.farm.local",
                "parent_node": "michel_3.farm.local",
                "node_parent": "michel_3.farm.local",
                "source_server": "michel_3",
                "source_hostname": "michel_3.farm.local",
                "original_master_id": "michel_3",
                "original_master_uuid": "michel_3",
                "original_master_hostname": "michel_3.farm.local",
                "home_master_uuid": "michel_3",
                "home_master_hostname": "michel_3.farm.local",
                "current_master_uuid": "michel_1",
                "current_master_hostname": "michel_1.farm.local",
            },
            workers["borrowed_workers"],
        )

        self.assertEqual(tasks["tasks_pending"], 0)
        self.assertEqual(tasks["tasks_running"], 1)
        self.assertEqual(tasks["tasks_completed"], 1)
        self.assertEqual(tasks["tasks_failed"], 1)
        self.assertEqual(tasks["oldest_task_age_s"], 0)

    def test_supervisor_payload_treats_origin_heartbeat_worker_as_borrowed_down(self):
        state = server.MasterState(
            master_uuid="michel_1",
            peers={},
            capacity=100,
            release_threshold=60,
            task_queue=[],
        )
        state.register_local_worker("B1")
        server.handle_heartbeat_message(
            state,
            "req-heartbeat",
            {"WORKER_UUID": "B1", "SERVER_UUID": "michel_2"},
        )

        payload = server.build_supervisor_payload(state, hostname="host")
        workers = payload["performance"]["farm_state"]["workers"]

        self.assertEqual(workers["workers_home"], 0)
        self.assertEqual(workers["workers_received"], 1)
        self.assertEqual(workers["workers_idle"], 0)
        self.assertEqual(workers["workers_available_capacity"], 1)
        self.assertIn(
            {
                "worker_uuid": "B1",
                "direction": "down",
                "status": "BORROWED_IN",
                "peer_uuid": "michel_2",
                "parent_uuid": "michel_2",
                "parent_hostname": "michel_2.farm.local",
                "parent_node": "michel_2.farm.local",
                "node_parent": "michel_2.farm.local",
                "source_server": "michel_2",
                "source_hostname": "michel_2.farm.local",
                "original_master_id": "michel_2",
                "original_master_uuid": "michel_2",
                "original_master_hostname": "michel_2.farm.local",
                "home_master_uuid": "michel_2",
                "home_master_hostname": "michel_2.farm.local",
                "current_master_uuid": "michel_1",
                "current_master_hostname": "michel_1.farm.local",
            },
            workers["borrowed_workers"],
        )

    def test_supervisor_payload_reports_thresholds_and_neighbors(self):
        state = self.build_state()

        payload = server.build_supervisor_payload(state, hostname="host")

        self.assertEqual(
            payload["performance"]["config_thresholds"],
            {
                "max_task": 100,
                "warn_cpu_percent": 85,
                "warn_memory_percent": 85,
                "release_task": 60,
            },
        )
        self.assertEqual(
            payload["performance"]["neighbors"],
            [
                {
                    "server_uuid": "michel_2",
                    "status": "available",
                    "last_heartbeat": "2026-06-10T12:00:00Z",
                }
            ],
        )


class Sprint4SenderTests(unittest.TestCase):
    def test_sender_writes_json_line_and_does_not_recv(self):
        events = []

        class FakeSocket:
            def __enter__(self):
                events.append("enter")
                return self

            def __exit__(self, exc_type, exc, traceback):
                events.append("exit")
                return False

            def sendall(self, data):
                events.append(("sendall", data))

            def recv(self, size):
                raise AssertionError("sender must not call recv")

        def connector(address, timeout):
            events.append(("connect", address, timeout))
            return FakeSocket()

        payload = {"task": "performance_report"}

        server.send_supervisor_payload(
            payload,
            host="example.test",
            port=443,
            use_tls=False,
            connector=connector,
            timeout=3,
        )

        sent = [event for event in events if isinstance(event, tuple) and event[0] == "sendall"][0][1]
        self.assertEqual(events[0], ("connect", ("example.test", 443), 3))
        self.assertTrue(sent.endswith(b"\n"))
        self.assertEqual(json.loads(sent.decode().strip()), payload)

    def test_start_supervisor_metrics_returns_none_when_disabled(self):
        started = []

        def fake_thread_factory(target, daemon):
            started.append((target, daemon))
            raise AssertionError("thread should not start when disabled")

        thread = server.start_supervisor_metrics(enabled=False, thread_factory=fake_thread_factory)

        self.assertIsNone(thread)
        self.assertEqual(started, [])


if __name__ == "__main__":
    unittest.main()
