from __future__ import annotations

import io
import json
import os
import tempfile
import sys
import types
import unittest
import uuid
from argparse import Namespace
from pathlib import Path
from unittest import mock

from symbraid.cli import prepare_project_payload, profile_set, run
from symbraid.registry import Registry, default_registry, normalize_project_path, project_id
from symbraid.service import SymbraidService
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


class RegistryTests(unittest.TestCase):
    def test_lancedb_directory_is_bounded_and_keeps_the_full_source_uuid(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            project_root = root / ("p" * 180)
            project_root.mkdir()
            registry = Registry(root / "config.json")
            data = default_registry()
            data["defaults"]["lancedb_root"] = str(root / "indexes")
            registry.save(data)
            identities = [uuid.UUID("0" * 31 + end) for end in ("1", "2")]
            with mock.patch("symbraid.registry.uuid.uuid4", side_effect=identities):
                projects = [registry.prepare_project(str(project_root)) for _ in identities]
            directories = []
            for project in projects:
                source = project["sources"][project["active_source_id"]]
                location = Path(source["location"]["directory"])
                self.assertEqual(location.parent, root / "indexes")
                self.assertEqual(len(location.name), 32)
                self.assertEqual(location.name, source["id"].rsplit("-", 1)[-1])
                directories.append(str(location).casefold())
            self.assertNotEqual(directories[0], directories[1], "the final UUID nibble must stay distinct")
            self.assertFalse((root / "indexes").exists())

    def test_saved_legacy_lancedb_location_is_not_rewritten(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            registry = Registry(root / "config.json")
            project = registry.register_project(str(root))
            source = project["sources"][project["active_source_id"]]
            legacy_directory = root / f"repo-{project['project_id']}"
            source["location"]["directory"] = str(legacy_directory)
            registry.update_project(str(root), project)
            before = registry.path.read_bytes()
            self.assertEqual(registry.register_project(str(root)), project)
            self.assertEqual(registry.resolved_config(project, source).lancedb_path, legacy_directory)
            self.assertEqual(registry.path.read_bytes(), before)

    def test_registration_inherits_global_storage_and_embedding_defaults(self):
        for backend in ("lancedb", "qdrant"):
            with self.subTest(backend=backend), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                registry = Registry(root / "config.json")
                data = default_registry()
                data["profiles"]["remote"] = {
                    "scope": "global", "provider": "openai-compatible", "model": "custom",
                    "dimension": 8, "base_url": "http://localhost:8080/v1", "secret_ref": "embedding:remote",
                }
                data["defaults"].update({
                    "backend": backend, "embedding_profile": "remote", "debounce_ms": 8000,
                    "qdrant_url": "http://localhost:18133", "qdrant_secret_ref": "qdrant:default",
                    "lancedb_root": str(root / "indexes"), "chunk_chars": 2400,
                })
                registry.save(data)
                projects = []
                for parent in ("first", "second"):
                    project_root = root / parent / "repo"
                    project_root.mkdir(parents=True)
                    project = registry.register_project(str(project_root))
                    source = project["sources"][project["active_source_id"]]
                    self.assertEqual(source["backend"], backend)
                    self.assertEqual(source["embedding_profile"], "remote")
                    self.assertEqual(source["recipe"]["chunk_chars"], 2400)
                    self.assertEqual(project["overrides"], {})
                    self.assertFalse(project["auto_watch"])
                    config = registry.resolved_config(project, source)
                    self.assertEqual(config.embedding_provider, "openai-compatible")
                    self.assertEqual(config.embedding_model, "custom")
                    self.assertEqual(config.embedding_dimension, 8)
                    self.assertEqual(registry.resolved_settings(project)["debounce_ms"], 8000)
                    if backend == "qdrant":
                        self.assertEqual(source["location"]["url"], data["defaults"]["qdrant_url"])
                        self.assertEqual(source["location"]["secret_ref"], "qdrant:default")
                    else:
                        self.assertEqual(Path(source["location"]["directory"]).parent, root / "indexes")
                    projects.append(project)
                self.assertNotEqual(projects[0]["project_id"], projects[1]["project_id"])
                self.assertNotEqual(
                    projects[0]["sources"][projects[0]["active_source_id"]]["location"],
                    projects[1]["sources"][projects[1]["active_source_id"]]["location"],
                )

    def test_repeated_registration_preserves_existing_project(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            registry = Registry(root / "config.json")
            project = registry.register_project(str(root))
            project["auto_watch"] = True
            project["overrides"]["debounce_ms"] = 9000
            registry.update_project(str(root), project)
            data = registry.load()
            data["defaults"].update({"backend": "qdrant", "embedding_profile": "changed-default"})
            registry.save(data)
            with mock.patch.object(registry, "save") as save:
                self.assertEqual(registry.register_project(str(root)), project)
            save.assert_not_called()

    def test_reregistration_uses_a_new_location_for_both_backends(self):
        for backend in ("lancedb", "qdrant"):
            with self.subTest(backend=backend), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                registry = Registry(root / "config.json")
                data = default_registry()
                data["defaults"]["backend"] = backend
                registry.save(data)
                first = registry.register_project(str(root))
                data = registry.load()
                data["projects"].clear()
                registry.save(data)
                second = registry.register_project(str(root))
                first_source = first["sources"][first["active_source_id"]]
                second_source = second["sources"][second["active_source_id"]]
                self.assertNotEqual(first_source["id"], second_source["id"])
                self.assertNotEqual(first_source["location"], second_source["location"])
                self.assertEqual(registry.register_project(str(root)), second)

    def test_new_qdrant_source_uses_symbraid_collection_name(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            project_root = root / "repo"; project_root.mkdir()
            config_path = root / "config.json"
            data = default_registry()
            data["defaults"]["backend"] = "qdrant"
            config_path.write_text(json.dumps(data), encoding="utf-8")

            project = Registry(config_path).register_project(str(project_root))
            source = project["sources"][project["active_source_id"]]

            self.assertTrue(source["location"]["collection"].startswith("symbraid-"))

    def test_registration_rejects_foreign_profile_in_existing_global_defaults(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            registry = Registry(root / "config.json")
            data = default_registry()
            data["profiles"]["private"] = {
                **data["profiles"]["default-code"], "scope": "project", "project_id": "other-project",
            }
            data["defaults"]["embedding_profile"] = "private"
            registry.save(data)
            before = registry.path.read_bytes()
            with self.assertRaisesRegex(ValueError, "another project"):
                registry.register_project(str(root))
            self.assertEqual(registry.path.read_bytes(), before)
            self.assertEqual(registry.load()["projects"], {})

    def test_registration_accepts_explicit_profile_owned_by_new_project(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            registry = Registry(root / "config.json")
            data = default_registry()
            data["profiles"]["private"] = {
                **data["profiles"]["default-code"], "scope": "project", "project_id": project_id(str(root)),
            }
            registry.save(data)
            project = registry.register_project(str(root), {"embedding_profile": "private"})
            self.assertEqual(project["sources"][project["active_source_id"]]["embedding_profile"], "private")



    @unittest.skipUnless(os.name == "nt", "Windows case-fold contract")
    def test_windows_normalization_casefolds_project_paths(self):
        self.assertEqual(
            normalize_project_path("C:/Work/Repo"),
            normalize_project_path("c:/work/repo"),
        )




class ProjectRegistrationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.home = self.root / "home"
        environment = mock.patch.dict(os.environ, {"SYMBRAID_HOME": str(self.home)})
        environment.start()
        self.addCleanup(environment.stop)
        self.project_root = self.root / "new project"
        self.project_root.mkdir()
        self.registry = Registry(self.home / "config" / "config.json")
        self.service = SymbraidService(self.registry)

    @unittest.skipUnless(os.name == "nt", "Windows LanceDB path budget")
    def test_long_lancedb_root_is_rejected_before_registration_or_store_access(self):
        for unicode_part in ("", "\U0001f680" * 8):
            with self.subTest(unicode_part=bool(unicode_part)):
                prefix = self.root / ("indexes-" + unicode_part)
                units = len(str(prefix.resolve()).encode("utf-16-le")) // 2
                storage_root = Path(str(prefix) + "d" * (161 - units - 33))
                payload = {"lancedb_root": str(storage_root)}
                with mock.patch.object(self.service, "_store") as store, mock.patch(
                    "symbraid.service.get_secret"
                ) as secret:
                    with self.assertRaisesRegex(ValueError, "shorter lancedb_root"):
                        self.service.plan_settings(str(self.project_root), payload)
                    with self.assertRaisesRegex(ValueError, "shorter lancedb_root"):
                        self.registry.register_project(str(self.project_root), payload)
                store.assert_not_called()
                secret.assert_not_called()
                self.assertFalse(self.home.exists())
                self.assertFalse(storage_root.exists())

    @unittest.skipUnless(os.name == "nt", "Windows LanceDB path budget")
    def test_shorter_storage_root_can_override_an_overlong_global_lancedb_root(self):
        data = default_registry()
        data["defaults"]["lancedb_root"] = str(self.root / ("d" * 150))
        self.registry.save(data)
        payload = {"lancedb_root": str(self.root / "indexes")}
        plan = self.service.plan_settings(str(self.project_root), payload)
        result = self.service.apply_project_settings(
            str(self.project_root), {**payload, "plan_hash": plan["plan_hash"]}
        )
        project, source = self.registry.active_source(str(self.project_root))
        self.assertEqual(result["impact"], "register")
        self.assertEqual(Path(source["location"]["directory"]).parent, Path(payload["lancedb_root"]))
        self.assertEqual(len(project["sources"]), 1)
        self.assertFalse(Path(data["defaults"]["lancedb_root"]).exists())

    def test_preview_and_plan_do_not_register_or_open_a_store(self):
        with mock.patch.object(self.service, "_store") as store, mock.patch(
            "symbraid.service.get_secret"
        ) as secret, mock.patch("symbraid.service.watcher_status") as watcher:
            state = self.service.settings_state(str(self.project_root))
            plan = self.service.plan_settings(str(self.project_root), {"auto_watch": True})
        self.assertEqual(state["status"], "ok")
        self.assertFalse(state["project"]["registered"])
        self.assertFalse(state["project"]["auto_watch"])
        self.assertEqual(state["project"]["effective"], state["defaults"])
        self.assertEqual(state["project"]["sources"], [])
        self.assertIsNone(state["project"]["active_source"])
        self.assertEqual(state["project"]["index_status"]["status"], "not_registered")
        self.assertIn("default-code", state["profiles"])
        self.assertEqual(plan["impact"], "register")
        self.assertFalse(self.home.exists(), "browsing and planning must not create app data")
        store.assert_not_called()
        secret.assert_not_called()
        watcher.assert_not_called()

    def test_preview_does_not_prepare_or_validate_an_unusable_source(self):
        data = default_registry()
        data["defaults"].update({
            "lancedb_root": str(self.root / ("d" * 150)),
            "max_file_bytes": 2097152, "chunk_chars": 2400,
            "chunk_overlap_chars": 120, "batch_size": 7,
        })
        self.registry.save(data)
        before = self.registry.path.read_bytes()
        with mock.patch.object(
            self.registry, "_managed_source", side_effect=ValueError("unusable storage")
        ) as source, mock.patch.object(self.service, "_store") as store, mock.patch(
            "symbraid.service.get_secret"
        ) as secret, mock.patch("symbraid.service.watcher_status") as watcher:
            state = self.service.settings_state(str(self.project_root))
        self.assertEqual(state["status"], "ok")
        self.assertIs(state["project"]["registered"], False)
        self.assertEqual(state["project"]["effective"], state["defaults"])
        self.assertEqual(state["project"]["project_id"], project_id(str(self.project_root)))
        self.assertIsNone(state["project"]["active_source"])
        self.assertEqual(state["project"]["sources"], [])
        self.assertIn("default-code", state["profiles"])
        self.assertEqual(self.registry.path.read_bytes(), before)
        self.assertFalse(Path(data["defaults"]["lancedb_root"]).exists())
        for call in (source, store, secret, watcher):
            call.assert_not_called()

    def test_tilde_root_empty_and_autowatch_plans_do_not_transfer(self):
        with mock.patch.dict(os.environ, {"HOME": str(self.root), "USERPROFILE": str(self.root)}):
            data = default_registry()
            data["defaults"]["lancedb_root"] = "~/indexes"
            self.registry.save(data)
            project = self.registry.register_project(str(self.project_root))
            original_source = project["active_source_id"]
            for payload in ({}, {"auto_watch": True}, {"lancedb_root": "~/indexes/.", "auto_watch": False}):
                with self.subTest(payload=payload):
                    with mock.patch.object(self.service, "_transfer") as transfer, mock.patch.object(
                        self.service, "_store"
                    ) as store:
                        plan = self.service.plan_settings(str(self.project_root), payload)
                        self.assertEqual(plan["impact"], "configuration-only")
                        self.assertEqual(plan["connection_changes"], [])
                        result = self.service.apply_project_settings(
                            str(self.project_root), {**payload, "plan_hash": plan["plan_hash"]}
                        )
                    transfer.assert_not_called()
                    store.assert_not_called()
                    current = self.registry.project(str(self.project_root))
                    self.assertEqual(result["active_source_id"], original_source)
                    self.assertEqual(len(current["sources"]), 1)
                    self.assertEqual(current["auto_watch"], bool(payload.get("auto_watch", False)))
            self.assertFalse((self.root / "indexes").exists())
            moved = self.service.plan_settings(str(self.project_root), {"lancedb_root": "~/other-indexes"})
            self.assertEqual(moved["impact"], "transfer")
            self.assertEqual(moved["connection_changes"], ["lancedb_root"])

    def test_confirming_global_settings_registers_one_source(self):
        payload = {**self.service.settings_state()["defaults"], "auto_watch": True}
        plan = self.service.plan_settings(str(self.project_root), payload)
        with mock.patch.object(self.service, "_store") as store:
            result = self.service.apply_project_settings(
                str(self.project_root), {**payload, "plan_hash": plan["plan_hash"]}
            )
        store.assert_not_called()
        project, source = self.registry.active_source(str(self.project_root))
        self.assertEqual(result["impact"], "register")
        self.assertEqual(len(project["sources"]), 1)
        self.assertEqual(project["overrides"], {})
        self.assertTrue(project["auto_watch"])
        self.assertEqual(source["backend"], payload["backend"])
        self.assertEqual(source["embedding_profile"], payload["embedding_profile"])
        with self.assertRaisesRegex(ValueError, "request a new plan"):
            self.service.apply_project_settings(str(self.project_root), {**payload, "plan_hash": plan["plan_hash"]})

    def test_custom_registration_creates_selected_source_without_migration(self):
        for backend in ("lancedb", "qdrant"):
            with self.subTest(backend=backend):
                project_root = self.root / backend
                project_root.mkdir()
                data = default_registry()
                data["defaults"]["backend"] = "qdrant" if backend == "lancedb" else "lancedb"
                data["profiles"]["remote"] = {
                    "scope": "global", "provider": "openai-compatible", "model": "custom",
                    "dimension": 8, "base_url": "http://localhost:8080/v1", "secret_ref": "",
                }
                self.registry.save(data)
                payload = {
                    "backend": backend, "embedding_profile": "remote", "auto_watch": True,
                    "qdrant_url": "http://localhost:18134", "lancedb_root": str(self.root / "custom-indexes"),
                }
                before = self.registry.path.read_bytes()
                plan = self.service.plan_settings(str(project_root), payload)
                self.assertEqual(self.registry.path.read_bytes(), before)
                with mock.patch.object(self.service, "_store") as store, mock.patch.object(self.service, "_transfer") as transfer:
                    self.service.apply_project_settings(str(project_root), {**payload, "plan_hash": plan["plan_hash"]})
                store.assert_not_called()
                transfer.assert_not_called()
                project, source = self.registry.active_source(str(project_root))
                self.assertEqual(list(project["sources"]), [project["active_source_id"]])
                self.assertTrue(project["active_source_id"].startswith(f"managed-{backend}-"))
                self.assertEqual(source["embedding_profile"], "remote")
                config = self.registry.resolved_config(project, source)
                self.assertEqual(config.embedding_model, "custom")
                self.assertEqual(config.embedding_dimension, 8)
                if backend == "qdrant":
                    self.assertEqual(source["location"]["url"], payload["qdrant_url"])
                else:
                    self.assertEqual(Path(source["location"]["directory"]).parent, Path(payload["lancedb_root"]))
                self.assertFalse((self.root / "custom-indexes").exists())

    def test_changed_defaults_or_enable_preference_invalidates_registration_plan(self):
        plan = self.service.plan_settings(str(self.project_root), {"auto_watch": True})
        with self.assertRaisesRegex(ValueError, "request a new plan"):
            self.service.apply_project_settings(str(self.project_root), {"auto_watch": False, "plan_hash": plan["plan_hash"]})
        data = default_registry()
        data["defaults"]["chunk_chars"] += 100
        self.registry.save(data)
        with self.assertRaisesRegex(ValueError, "request a new plan"):
            self.service.apply_project_settings(str(self.project_root), {"auto_watch": True, "plan_hash": plan["plan_hash"]})
        self.assertEqual(self.registry.load()["projects"], {})

    def test_preview_hides_other_projects_profiles_and_plan_rejects_them(self):
        data = default_registry()
        data["profiles"]["private"] = {**data["profiles"]["default-code"], "scope": "project", "project_id": "other"}
        self.registry.save(data)
        state = self.service.settings_state(str(self.project_root))
        self.assertNotIn("private", state["profiles"])
        with self.assertRaisesRegex(ValueError, "another project"):
            self.service.plan_settings(str(self.project_root), {"embedding_profile": "private"})
        self.assertEqual(self.registry.load()["projects"], {})

    def test_cli_global_defaults_reject_project_profile_before_secret_write(self):
        data = default_registry()
        data["profiles"]["private"] = {
            **data["profiles"]["default-code"], "scope": "project", "project_id": project_id(str(self.project_root)),
        }
        self.registry.save(data)
        before = self.registry.path.read_bytes()
        args = Namespace(command="settings", settings_command="apply-defaults", project=None)
        with mock.patch("symbraid.cli.Registry", return_value=self.registry), mock.patch(
            "symbraid.cli.stdin_json", return_value={"embedding_profile": "private", "qdrant_api_key": "must-not-be-stored"}
        ), mock.patch("symbraid.cli.SecretUpdate") as secret:
            with self.assertRaisesRegex(ValueError, "global embedding profile"):
                run(args)
        secret.assert_not_called()
        self.assertEqual(self.registry.path.read_bytes(), before)

    def test_changed_profile_invalidates_registration_plan_without_resolving_secrets(self):
        changes = {
            "provider": "fastembed", "model": "changed-model", "dimension": 5,
            "base_url": "http://localhost:8081/v1", "secret_ref": "embedding:changed",
        }
        for key, value in changes.items():
            with self.subTest(key=key):
                data = default_registry()
                data["profiles"]["remote"] = {
                    "scope": "global", "provider": "openai-compatible", "model": "original-model",
                    "dimension": 3, "base_url": "http://localhost:8080/v1", "secret_ref": "embedding:original",
                }
                self.registry.save(data)
                payload = {"embedding_profile": "remote", "auto_watch": True}
                with mock.patch("symbraid.service.get_secret") as secret:
                    plan = self.service.plan_settings(str(self.project_root), payload)
                    self.assertEqual(plan["plan_hash"], self.service.plan_settings(str(self.project_root), payload)["plan_hash"])
                    self.assertNotIn("embedding:original", json.dumps(plan))
                    data["profiles"]["remote"][key] = value
                    self.registry.save(data)
                    transaction = mock.MagicMock()
                    with self.assertRaisesRegex(ValueError, "request a new plan"):
                        self.service.apply_project_settings(
                            str(self.project_root), {**payload, "plan_hash": plan["plan_hash"]}, secret_update=transaction
                        )
                secret.assert_not_called()
                transaction.__enter__.assert_not_called()
                self.assertEqual(self.registry.load()["projects"], {})

    def test_reregistration_reembeds_and_preserves_retained_index(self):
        (self.project_root / "demo.txt").write_text("unchanged fixture text", encoding="utf-8")
        data = default_registry()
        for name in ("old", "new"):
            data["profiles"][name] = {
                "scope": "global", "provider": "openai-compatible", "model": name + "-model",
                "dimension": 3, "base_url": "http://localhost:8080/v1", "secret_ref": "",
            }
        self.registry.save(data)
        payload = {"embedding_profile": "old"}
        plan = self.service.plan_settings(str(self.project_root), payload)
        self.service.apply_project_settings(str(self.project_root), {**payload, "plan_hash": plan["plan_hash"]})
        old_project, old_source = self.registry.active_source(str(self.project_root))
        old_store = self.service._store(self.registry.resolved_config(old_project, old_source))
        with mock.patch("symbraid.service.Embedder") as embedder:
            embedder.return_value.embed_documents.side_effect = lambda texts: [[1.0, 0.0, 0.0] for _ in texts]
            first = self.service.index(str(self.project_root))
        self.assertGreater(first["chunks_written"], 0)
        repo_id = first["repo_id"]
        retained = old_store.export_points(repo_id)
        with mock.patch("symbraid.cli.Registry", return_value=self.registry):
            run(Namespace(command="project", project_command="remove", path=str(self.project_root)))
        payload = {"embedding_profile": "new"}
        plan = self.service.plan_settings(str(self.project_root), payload)
        result = self.service.apply_project_settings(str(self.project_root), {**payload, "plan_hash": plan["plan_hash"]})
        new_project, new_source = self.registry.active_source(str(self.project_root))
        self.assertEqual(result["active_source_id"], new_project["active_source_id"])
        with mock.patch("symbraid.service.Embedder") as embedder:
            embedder.return_value.embed_documents.side_effect = lambda texts: [[0.0, 1.0, 0.0] for _ in texts]
            second = self.service.index(str(self.project_root))
            self.assertTrue(embedder.return_value.embed_documents.called, "new model must embed unchanged files")
        self.assertGreater(second["chunks_written"], 0)
        self.assertNotEqual(new_source["location"], old_source["location"])
        self.assertEqual(old_store.export_points(repo_id), retained, "the retained old index must remain unchanged")
        new_store = self.service._store(self.registry.resolved_config(new_project, new_source))
        new_points = new_store.export_points(repo_id)
        self.assertTrue(all(point["vector"] == [0.0, 1.0, 0.0] for point in new_points if point["payload"]["type"] == "chunk"))
        self.assertEqual(self.service.status(str(self.project_root))["metadata"]["embedding_model"], "new-model")

    def test_registration_save_failure_rolls_back_secret(self):
        raw = {"qdrant_api_key": "new-secret", "backend": "qdrant"}
        payload = prepare_project_payload(self.registry, str(self.project_root), raw)
        plan = self.service.plan_settings(str(self.project_root), payload)
        reference = payload["qdrant_secret_ref"]
        keyring = fake_keyring({(SERVICE, reference): "old-secret"})
        with mock.patch.dict(sys.modules, {"keyring": keyring}), mock.patch.object(
            self.registry, "save", side_effect=RuntimeError("save failed")
        ):
            with self.assertRaisesRegex(RuntimeError, "save failed"):
                self.service.apply_project_settings(
                    str(self.project_root), {**payload, "plan_hash": plan["plan_hash"]},
                    secret_update=SecretUpdate(reference, "new-secret"),
                )
        self.assertEqual(keyring.credentials[(SERVICE, reference)], "old-secret")
        self.assertFalse(self.registry.path.exists())


class SettingsTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        environment = mock.patch.dict(os.environ, {"SYMBRAID_HOME": str(self.root / "home")})
        environment.start()
        self.addCleanup(environment.stop)
        self.project_root = self.root / "repo"; self.project_root.mkdir()
        self.registry = Registry(self.root / "config.json")
        registered = self.registry.register_project(str(self.project_root))
        self.original_source_id = registered["active_source_id"]
        self.service = SymbraidService(self.registry)

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
        with mock.patch.object(self.service, "status", return_value={"status": "ok", "indexed": False}):
            state = self.service.settings_state(str(self.project_root))
        encoded = json.dumps(state)
        self.assertNotIn("secret-ref", encoded)
        self.assertNotIn("profile-secret", encoded)
        self.assertTrue(all("owner" not in source for source in state["project"]["sources"]))
        self.assertNotIn('"mode":', encoded)
        self.assertTrue(state["defaults"]["qdrant_api_key_configured"])

    def test_settings_remain_available_when_index_status_fails(self):
        with mock.patch.object(self.service, "status", side_effect=RuntimeError("backend unavailable")):
            state = self.service.settings_state(str(self.project_root))
        self.assertEqual(state["status"], "ok")
        self.assertEqual(state["defaults"], state["project"]["effective"])
        self.assertIn("default-code", state["profiles"])
        self.assertEqual(state["project"]["active_source"]["embedding_profile"], "default-code")
        self.assertEqual(state["project"]["index_status"], {"status": "error", "error": "backend unavailable"})

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
        with mock.patch.object(self.service, "_store", return_value=fake_store), mock.patch("symbraid.service.SymbraidIndexer", return_value=indexer):
            result = self.service.apply_project_settings(str(self.project_root), {**payload, "plan_hash": plan["plan_hash"]})
        project = self.registry.project(str(self.project_root))
        self.assertEqual(result["impact"], "reindex")
        self.assertEqual(result["chunks"], 7)
        self.assertEqual(project["active_source_id"], result["to"])
        self.assertIn(self.original_source_id, project["sources"])

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
        ), mock.patch("symbraid.service.SymbraidIndexer", return_value=indexer):
            with self.assertRaises(RuntimeError):
                self.service.apply_project_settings(
                    str(self.project_root), {**payload, "plan_hash": plan["plan_hash"]},
                    secret_update=SecretUpdate(reference, "new-secret"),
                )
        self.assertEqual(keyring.credentials[key], "old-secret")
        self.assertEqual([event[3] for event in keyring.history if event[0] == "set"], ["new-secret", "old-secret"])
        project = self.registry.project(str(self.project_root))
        self.assertEqual(project["active_source_id"], self.original_source_id)
        self.assertEqual(list(project["sources"]), [self.original_source_id])
        fake_store.delete_repo.assert_called_once()


if __name__ == "__main__":
    unittest.main()
