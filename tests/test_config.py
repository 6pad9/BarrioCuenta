import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from backend.config import load_local_env, database_url, migration_url

class ConfigTests(unittest.TestCase):
    def test_load_without_overriding_environment(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'.env'
            path.write_text('# prueba\nDATABASE_NAME=barriofinanzas\nAPP_MODE=development\n',encoding='utf-8')
            with patch.dict(os.environ,{'APP_MODE':'production'},clear=True):
                load_local_env(path)
                self.assertEqual(os.environ['DATABASE_NAME'],'barriofinanzas')
                self.assertEqual(os.environ['APP_MODE'],'production')
    def test_postgres_and_password_encoding(self):
        with patch.dict(os.environ,dict(DATABASE_NAME='barriofinanzas',DATABASE_USER='postgres',DATABASE_PASSWORD='a@b:c'),clear=True):
            self.assertEqual(database_url(),'postgresql+psycopg://postgres:a%40b%3Ac@127.0.0.1:5432/barriofinanzas')
    def test_explicit_url_has_priority(self):
        with patch.dict(os.environ,dict(DATABASE_NAME='barriofinanzas',DATABASE_URL='sqlite:///:memory:'),clear=True):
            self.assertEqual(database_url(),'sqlite:///:memory:')

    def test_local_env_precedes_env_without_overriding_process(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder)
            (root/'.env.local').write_text('DATABASE_URL=sqlite:///neon-test.db\nLOCAL_ONLY=present\n',encoding='utf-8')
            (root/'.env').write_text('DATABASE_URL=sqlite:///old.db\nFROM_ENV=present\n',encoding='utf-8')
            with patch.dict(os.environ,{'LOCAL_ONLY':'process-wins'},clear=True),patch('backend.config.ROOT',root):
                load_local_env()
                self.assertEqual(os.environ['DATABASE_URL'],'sqlite:///neon-test.db')
                self.assertEqual(os.environ['LOCAL_ONLY'],'process-wins')
                self.assertEqual(os.environ['FROM_ENV'],'present')
    def test_direct_migration_connection_preserves_tls(self):
        with patch.dict(os.environ,dict(DATABASE_URL='postgresql://u:p@ep-demo-pooler.us-east-1.aws.neon.tech/db?sslmode=require'),clear=True):
            self.assertEqual(migration_url(),'postgresql+psycopg://u:p@ep-demo.us-east-1.aws.neon.tech/db?sslmode=require')
        with patch.dict(os.environ,dict(DATABASE_URL_UNPOOLED='postgresql://u:p@ep-direct.neon.tech/db?sslmode=require'),clear=True):
            self.assertEqual(migration_url(),'postgresql+psycopg://u:p@ep-direct.neon.tech/db?sslmode=require')
