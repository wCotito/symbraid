from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from code_index.registry import Registry, default_registry, normalize_project_path
from code_index.service import CodeIndexService


class RegistryMigrationTests(unittest.TestCase):
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
                "path": str(project_root), "project_id": "0123456789abcdef", "watch_enabled": True,
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
            self.assertEqual(migrated["schema_version"], 2)
            self.assertNotIn("kilo_lancedb_roots", migrated["defaults"])
            self.assertEqual(project["active_source_id"], "managed-lancedb")
            self.assertFalse(project["watch_enabled"])
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
                "path": str(project_root), "project_id": "fedcba9876543210", "watch_enabled": True,
                "active_source_id": "external", "overrides": {},
                "sources": {"external": {"id": "external", "owner": "kilo", "mode": "read-only", "backend": "qdrant", "location": {"url": "http://example", "collection": "external"}}},
            }
            config_path.write_text(json.dumps(legacy), encoding="utf-8")
            project = Registry(config_path).load()["projects"][key]
            self.assertEqual(project["active_source_id"], "managed-lancedb")
            self.assertEqual(project["sources"]["managed-lancedb"]["backend"], "lancedb")
            self.assertFalse(project["watch_enabled"])


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

    def test_state_is_sanitized_and_contains_only_managed_contract(self):
        data = self.registry.load()
        data["defaults"]["qdrant_secret_ref"] = "secret-ref"
        data["profiles"]["default-code"]["secret_ref"] = "profile-secret"
        self.registry.save(data)
        state = self.service.settings_state(str(self.project_root))
        encoded = json.dumps(state)
        self.assertNotIn("secret-ref", encoded)
        self.assertNotIn("profile-secret", encoded)
        self.assertNotIn('"owner":', encoded)
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
        payload = {"debounce_ms": 2200, "watch_enabled": True}
        plan = self.service.plan_settings(str(self.project_root), payload)
        result = self.service.apply_project_settings(str(self.project_root), {**payload, "plan_hash": plan["plan_hash"]})
        project = self.registry.project(str(self.project_root))
        self.assertEqual(result["impact"], "configuration-only")
        self.assertEqual(project["overrides"]["debounce_ms"], 2200)
        self.assertTrue(project["watch_enabled"])
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
        with mock.patch.object(self.service, "_store", return_value=fake_store), mock.patch("code_index.service.CodeIndexer", return_value=indexer):
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
        payload = {"embedding_profile": "remote"}
        plan = self.service.plan_settings(str(self.project_root), payload)
        fake_store = mock.Mock()
        indexer = mock.Mock(); indexer.index_project.side_effect = RuntimeError("fixture failure")
        with mock.patch.object(self.service, "_store", return_value=fake_store), mock.patch("code_index.service.CodeIndexer", return_value=indexer):
            with self.assertRaises(RuntimeError):
                self.service.apply_project_settings(str(self.project_root), {**payload, "plan_hash": plan["plan_hash"]})
        project = self.registry.project(str(self.project_root))
        self.assertEqual(project["active_source_id"], "managed-lancedb")
        self.assertEqual(list(project["sources"]), ["managed-lancedb"])
        fake_store.delete_repo.assert_called_once()


if __name__ == "__main__":
    unittest.main()
