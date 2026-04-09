import os
import tempfile
import unittest

from core.auth import get_user
from core.db import Db
from core.runtime_bootstrap import ensure_admin_user, get_admin_bootstrap_summary


class RuntimeBootstrapTests(unittest.TestCase):
    def test_summary_is_disabled_without_credentials(self):
        summary = get_admin_bootstrap_summary({})
        self.assertFalse(summary["configured"])
        self.assertEqual(summary["username"], "admin")

    def test_bootstrap_creates_admin_user_from_plain_password(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            db_path = os.path.join(temp_dir, "bootstrap.db")
            db_instance = Db(tag="bootstrap-test", User_In_Thread=False)
            db_instance.init(f"sqlite:///{db_path}")
            db_instance.create_tables()

            result = ensure_admin_user(
                db_instance,
                {
                    "ADMIN_USERNAME": "maintainer",
                    "ADMIN_PASSWORD": "secret-123",
                    "ADMIN_NICKNAME": "Maintainer",
                },
            )

            self.assertEqual(result["status"], "created")

            session = db_instance.get_session()
            try:
                from core.models.user import User as DBUser

                user = session.query(DBUser).filter(DBUser.username == "maintainer").first()
                self.assertIsNotNone(user)
                self.assertEqual(user.role, "admin")
                self.assertEqual(user.permissions, "all")
                self.assertTrue(user.verify_password("secret-123"))
            finally:
                session.close()

    def test_bootstrap_updates_existing_admin_when_force_enabled(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            db_path = os.path.join(temp_dir, "bootstrap-update.db")
            db_instance = Db(tag="bootstrap-test-update", User_In_Thread=False)
            db_instance.init(f"sqlite:///{db_path}")
            db_instance.create_tables()

            ensure_admin_user(
                db_instance,
                {
                    "ADMIN_USERNAME": "admin",
                    "ADMIN_PASSWORD": "old-password",
                },
            )

            result = ensure_admin_user(
                db_instance,
                {
                    "ADMIN_USERNAME": "admin",
                    "ADMIN_PASSWORD": "new-password",
                    "ADMIN_FORCE_UPDATE_PASSWORD": "true",
                },
            )

            self.assertEqual(result["status"], "updated")

            session = db_instance.get_session()
            try:
                from core.models.user import User as DBUser

                user = session.query(DBUser).filter(DBUser.username == "admin").first()
                self.assertIsNotNone(user)
                self.assertTrue(user.verify_password("new-password"))
            finally:
                session.close()
