from __future__ import annotations

import io
import json
import os
import tempfile
import sys
import types
import unittest
from argparse import Namespace
from pathlib import Path
from unittest import mock

from symbraid.cli import prepare_project_payload, profile_set, run
from symbraid.registry import Registry, default_registry, normalize_project_path
from symbraid.service import CodeIndexService
from symbraid.secrets import SERVICE, SecretUpdate


def fake_keyring(initial=None):
    module = types.ModuleType("keyring")

    class PasswordDeleteError(Exception):
        pass

    module.errors = types.SimpleNamespace(PasswordDeleteError=PasswordDeleteError)
    module.credentials = dict(initial or {})
    module.history = []

    def get_password(service, name):
        return module.credentials.get((service, name))

    def set_password(service, name, value):
        module.credentials[(service, name)] = value
        module.history.append(("set", service, name, value))

    def delete_password(service, name):
        key = (service, name)
        if key not in module.credentials:
            raise PasswordDeleteError(name)
        del module.credentials[key]
        module.history.append(("delete", service, name))

    module.get_password = get_password
    module.set_password = set_password
    module.delete_password = delete_password
    return module


class RegistryMigrationTests(unittest.TestCase):
    def test_v2_rejects_normalized_path_collision_even_with_matching_project_id(self):
        with tempfile.TemporaryDirectory() as directory:
            data = default_registry()
            data["schema_version"] = 2
            shared_id = "0123456789abcdef"
            data["projects"] = {
                "first": {"path": "C:/Work/Repo", "project_id": shared_id, "sources": {}, "overrides": {}},
                "second": {"path": "c:/work/repo", "project_id": shared_id, "sources": {}, "overrides": {}},
            }
            config_path = Path(directory) / "config.json"
            original = json.dumps(data)
            config_path.write_text(original, encoding="utf-8")
            registry = Registry(config_path)
            with mock.patch("symbraid.registry.normalize_project_path", return_value="c:/work/repo"):
                with self.assertRaisesRegex(ValueError, "Project path collision"):
                    registry.load()
            self.assertEqual(config_path.read_text(encoding="utf-8"), original)
            self.assertTrue(config_path.with_name("config.json.v2.bak").is_file())

    @unittest.skipUnless(os.name == "nt", "Windows case-fold contract")
    def test_windows_normalization_casefolds_project_paths(self):
        self.assertEqual(
            normalize_project_path("C:/Work/Repo"),
            normalize_project_path("c:/work/repo"),
        )

    def test_v1_removes_external_sources_and_preserves_physical_locations_in_backup(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            project_root = root / "repo"; project_root.mkdir()
            config_path = root / "config.json"
            external_directory = root / "external-index"
            legacy = default_registry(); legacy["schema_version"] = 1
            legacy["defaults"]["kilo_lancedb_roots"] = [str(root / "discovery")]
            key = normalize_project_path(str(project_root))
            legacy["projects"][key] = {
                "path": str(project_root), "project_id": "0123456789abcdef", "auto_watch": True,
                "active_source_id": "external-lance", "overrides": {},
                "sources": {
                    "managed-lancedb": {
                        "id": "managed-lancedb", "owner": "code-index", "mode": "read-write",
                        "backend": "lancedb", "embedding_profile": "default-code",
                        "location": {"directory": str(root / "managed")},
                    },
                    "external-lance": {
                        "id": "external-lance", "owner": "kilo", "mode": "read-only",
                        "backend": "lancedb", "embedding_profile": "default-code",
                        "location": {"directory": str(external_directory)},
                    },
                },
            }
            config_path.write_text(json.dumps(legacy), encoding="utf-8")
            registry = Registry(config_path)
            migrated = registry.load()
            project = migrated["projects"][key]
            self.assertEqual(migrated["schema_version"], 3)
            self.assertNotIn("kilo_lancedb_roots", migrated["defaults"])
            self.assertEqual(project["active_source_id"], "managed-lancedb")
            self.assertFalse(project["auto_watch"])
            self.assertNotIn("external-lance", project["sources"])
            self.assertNotIn("owner", project["sources"]["managed-lancedb"])
            backup = config_path.with_name("config.json.v1.bak")
            self.assertTrue(backup.exists())
            backup_data = json.loads(backup.read_text(encoding="utf-8"))
            self.assertEqual(
                backup_data["projects"][key]["sources"]["external-lance"]["location"]["directory"],
                str(external_directory),
            )
            self.assertFalse(external_directory.exists())

    def test_v1_creates_managed_source_when_only_external_source_existed(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); project_root = root / "repo"; project_root.mkdir()
            config_path = root / "config.json"
            legacy = default_registry(); legacy["schema_version"] = 1
            key = normalize_project_path(str(project_root))
            legacy["projects"][key] = {
                "path": str(project_root), "project_id": "fedcba9876543210", "auto_watch": True,
                "active_source_id": "external", "overrides": {},
                "sources": {"external": {"id": "external", "owner": "kilo", "mode": "read-only", "backend": "qdrant", "location": {"url": "http://example", "collection": "external"}}},
            }
            config_path.write_text(json.dumps(legacy), encoding="utf-8")
            project = Registry(config_path).load()["projects"][key]
            self.assertEqual(project["active_source_id"], "managed-lancedb")
            self.assertEqual(project["sources"]["managed-lancedb"]["backend"], "lancedb")
            self.assertFalse(project["auto_watch"])


class SettingsTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.project_root = self.root / "repo"; self.project_root.mkdir()
        self.registry = Registry(self.root / "config.json")
        self.registry.register_project(str(self.project_root))
        self.service = CodeIndexService(self.registry)

    def tearDown(self):
        self.temp.cleanup()

    def test_invalid_profile_dimension_does_not_write_secret(self):
        args = Namespace(
            profile_id="invalid", display_name=None, scope=None, project_id=None,
            provider="openai-compatible", model="remote", dimension=0,
            base_url="http://127.0.0.1:8080/v1", api_key_stdin=False,
            api_key_env=None,
        )
        with mock.patch("symbraid.cli.SecretUpdate") as transaction:
            with self.assertRaisesRegex(ValueError, "dimension must be positive"):
                profile_set(self.registry, args, {"api_key": "must-not-be-stored"})
        transaction.assert_not_called()

    def test_stale_apply_project_plan_does_not_invoke_secret_commit(self):
        payload = {
            "qdrant_secret_ref": "qdrant:project:0123456789abcdef",
            "_replace_qdrant_key": True,
            "plan_hash": "bogus-plan-hash",
        }
        secret_update = mock.MagicMock()
        with self.assertRaisesRegex(ValueError, "request a new plan"):
            self.service.apply_project_settings(
                str(self.project_root), payload, secret_update=secret_update
            )
        secret_update.__enter__.assert_not_called()

    def test_cli_stale_apply_project_does_not_write_keyring(self):
        args = Namespace(
            command="settings", settings_command="apply-project", project=str(self.project_root)
        )
        payload = {"qdrant_api_key": "must-not-be-stored", "plan_hash": "bogus-plan-hash"}
        with mock.patch("symbraid.cli.Registry", return_value=self.registry), mock.patch(
            "symbraid.cli.stdin_json", return_value=payload
        ), mock.patch("symbraid.cli.SecretUpdate") as transaction:
            with self.assertRaisesRegex(ValueError, "request a new plan"):
                run(args)
        transaction.return_value.__enter__.assert_not_called()

    def test_secret_update_restores_old_empty_and_missing_credentials(self):
        reference = "keyring:transaction-fixture"
        for old_value in (None, "", "old-secret"):
            with self.subTest(old_value=old_value):
                initial = {} if old_value is None else {(SERVICE, "transaction-fixture"): old_value}
                keyring = fake_keyring(initial)
                with mock.patch.dict(sys.modules, {"keyring": keyring}):
                    update = SecretUpdate(reference, "new-secret")
                    with self.assertRaisesRegex(RuntimeError, "after keyring write"):
                        with update:
                            self.assertEqual(keyring.credentials[(SERVICE, "transaction-fixture")], "new-secret")
                            raise RuntimeError("after keyring write")
                if old_value is None:
                    self.assertNotIn((SERVICE, "transaction-fixture"), keyring.credentials)
                else:
                    self.assertEqual(keyring.credentials[(SERVICE, "transaction-fixture")], old_value)


    def test_profile_save_failure_restores_previous_secret(self):
        args = Namespace(
            profile_id="remote", display_name=None, scope="global", project_id=None,
            provider="openai-compatible", model="remote", dimension=8,
            base_url="http://127.0.0.1:8080/v1", api_key_stdin=False,
            api_key_env=None,
        )
        reference = (SERVICE, "embedding:remote")
        keyring = fake_keyring({reference: "old-secret"})
        with mock.patch.dict(sys.modules, {"keyring": keyring}), mock.patch.object(
            self.registry, "save", side_effect=RuntimeError("registry save failed")
        ):
            with self.assertRaisesRegex(RuntimeError, "registry save failed"):
                profile_set(self.registry, args, {"api_key": "new-secret"})
        self.assertEqual(keyring.credentials[reference], "old-secret")
        self.assertEqual([event[3] for event in keyring.history if event[0] == "set"], ["new-secret", "old-secret"])

    def test_defaults_set_save_failure_restores_previous_secret(self):
        args = Namespace(
            command="defaults", defaults_command="set", backend=None, qdrant_url=None,
            lancedb_root=None, embedding_profile=None, debounce_ms=None,
            bulk_change_threshold=None, max_file_bytes=None, chunk_chars=None,
            chunk_overlap_chars=None, batch_size=None, rg_path=None,
            qdrant_api_key_stdin=True, qdrant_api_key_env=None,
        )
        key = (SERVICE, "qdrant:default")
        keyring = fake_keyring({key: "old-secret"})
        with mock.patch.dict(sys.modules, {"keyring": keyring}), mock.patch(
            "symbraid.cli.Registry", return_value=self.registry
        ), mock.patch(
            "symbraid.cli.sys.stdin", io.StringIO("new-secret")
        ), mock.patch.object(
            self.registry, "save", side_effect=RuntimeError("registry save failed")
        ):
            with self.assertRaisesRegex(RuntimeError, "registry save failed"):
                run(args)
        self.assertEqual(keyring.credentials[key], "old-secret")


    def test_apply_defaults_save_failure_restores_previous_secret(self):
        args = Namespace(command="settings", settings_command="apply-defaults", project=None)
        payload = {"qdrant_api_key": "new-secret"}
        key = (SERVICE, "qdrant:default")
        keyring = fake_keyring({key: "old-secret"})
        with mock.patch.dict(sys.modules, {"keyring": keyring}), mock.patch(
            "symbraid.cli.Registry", return_value=self.registry
        ), mock.patch(
            "symbraid.cli.stdin_json", return_value=payload
        ), mock.patch.object(
            self.registry, "save", side_effect=RuntimeError("registry save failed")
        ):
            with self.assertRaisesRegex(RuntimeError, "registry save failed"):
                run(args)
        self.assertEqual(keyring.credentials[key], "old-secret")

    def test_state_is_sanitized_and_contains_only_managed_contract(self):
        data = self.registry.load()
        data["defaults"]["qdrant_secret_ref"] = "secret-ref"
        data["profiles"]["default-code"]["secret_ref"] = "profile-secret"
        self.registry.save(data)
        state = self.service.settings_state(str(self.project_root))
        encoded = json.dumps(state)
        self.assertNotIn("secret-ref", encoded)
        self.assertNotIn("profile-secret", encoded)
        self.assertTrue(all("owner" not in source for source in state["project"]["sources"]))
        self.assertNotIn('"mode":', encoded)
        self.assertTrue(state["defaults"]["qdrant_api_key_configured"])

    def test_plan_classifies_configuration_transfer_and_reindex(self):
        config_only = self.service.plan_settings(str(self.project_root), {"debounce_ms": 2000})
        transfer = self.service.plan_settings(str(self.project_root), {"backend": "qdrant"})
        data = self.registry.load()
        data["profiles"]["remote"] = {
            "display_name": "Remote", "scope": "global", "provider": "openai-compatible",
            "model": "remote", "dimension": 1024, "base_url": "http://127.0.0.1:8080/v1", "secret_ref": "",
        }
        self.registry.save(data)
        reindex = self.service.plan_settings(str(self.project_root), {"embedding_profile": "remote"})
        self.assertEqual(config_only["impact"], "configuration-only")
        self.assertEqual(transfer["impact"], "transfer")
        self.assertEqual(reindex["impact"], "reindex")

    def test_configuration_only_apply_requires_matching_plan(self):
        payload = {"debounce_ms": 2200, "auto_watch": True}
        plan = self.service.plan_settings(str(self.project_root), payload)
        result = self.service.apply_project_settings(str(self.project_root), {**payload, "plan_hash": plan["plan_hash"]})
        project = self.registry.project(str(self.project_root))
        self.assertEqual(result["impact"], "configuration-only")
        self.assertEqual(project["overrides"]["debounce_ms"], 2200)
        self.assertTrue(project["auto_watch"])
        with self.assertRaises(ValueError):
            self.service.apply_project_settings(str(self.project_root), {"debounce_ms": 2300, "plan_hash": plan["plan_hash"]})

    def test_reindex_activates_new_source_only_after_verification(self):
        data = self.registry.load()
        data["profiles"]["remote"] = {
            "display_name": "Remote", "scope": "global", "provider": "openai-compatible",
            "model": "remote", "dimension": 1024, "base_url": "http://127.0.0.1:8080/v1", "secret_ref": "",
        }
        self.registry.save(data)
        payload = {"embedding_profile": "remote"}
        plan = self.service.plan_settings(str(self.project_root), payload)
        fake_store = mock.Mock()
        indexer = mock.Mock()
        indexer.index_project.return_value = {"chunks_total": 7}
        indexer.index_status.return_value = {"indexed": True, "metadata": {"indexing_complete": True}}
        with mock.patch.object(self.service, "_store", return_value=fake_store), mock.patch("symbraid.service.CodeIndexer", return_value=indexer):
            result = self.service.apply_project_settings(str(self.project_root), {**payload, "plan_hash": plan["plan_hash"]})
        project = self.registry.project(str(self.project_root))
        self.assertEqual(result["impact"], "reindex")
        self.assertEqual(result["chunks"], 7)
        self.assertEqual(project["active_source_id"], result["to"])
        self.assertIn("managed-lancedb", project["sources"])

    def test_reindex_failure_keeps_active_source(self):
        data = self.registry.load()
        data["profiles"]["remote"] = {
            "display_name": "Remote", "scope": "global", "provider": "openai-compatible",
            "model": "remote", "dimension": 1024, "base_url": "http://127.0.0.1:8080/v1", "secret_ref": "",
        }
        self.registry.save(data)
        raw_payload = {"embedding_profile": "remote", "qdrant_api_key": "new-secret"}
        payload = prepare_project_payload(self.registry, str(self.project_root), raw_payload)
        plan = self.service.plan_settings(str(self.project_root), payload)
        reference = payload["qdrant_secret_ref"]
        key = (SERVICE, reference)
        keyring = fake_keyring({key: "old-secret"})
        fake_store = mock.Mock()
        indexer = mock.Mock(); indexer.index_project.side_effect = RuntimeError("fixture failure")
        with mock.patch.dict(sys.modules, {"keyring": keyring}), mock.patch.object(
            self.service, "_store", return_value=fake_store
        ), mock.patch("symbraid.service.CodeIndexer", return_value=indexer):
            with self.assertRaises(RuntimeError):
                self.service.apply_project_settings(
                    str(self.project_root), {**payload, "plan_hash": plan["plan_hash"]},
                    secret_update=SecretUpdate(reference, "new-secret"),
                )
        self.assertEqual(keyring.credentials[key], "old-secret")
        self.assertEqual([event[3] for event in keyring.history if event[0] == "set"], ["new-secret", "old-secret"])
        project = self.registry.project(str(self.project_root))
        self.assertEqual(project["active_source_id"], "managed-lancedb")
        self.assertEqual(list(project["sources"]), ["managed-lancedb"])
        fake_store.delete_repo.assert_called_once()


if __name__ == "__main__":
    unittest.main()
