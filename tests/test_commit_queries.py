import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient
from git import Repo
from sqlalchemy.dialects import postgresql

from app.core.database import get_db
from app.main import create_app
from app.schemas.rag_schema import RAGAskResponse
from app.schemas.repository_schema import RepositoryCommitIngestRequest, RepositoryIngestRequest
from app.schemas.vector_schema import VectorSearchRequest
from app.services.embedding_service import EmbeddingService
from app.services.repository_service import RepositoryService
from app.services.vector_service import VectorService


class CommitTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.repo_path = Path(self.temp_dir.name) / "sample-repo"
        self.repo_path.mkdir()
        repo = Repo.init(self.repo_path, initial_branch="main")
        with repo.config_writer() as config:
            config.set_value("user", "name", "Test")
            config.set_value("user", "email", "test@example.com")
        readme = self.repo_path / "README.md"
        readme.write_text("Versión inicial\n", encoding="utf-8")
        repo.index.add(["README.md"])
        self.old_sha = repo.index.commit("Versión inicial").hexsha
        readme.write_text("Versión nueva\n", encoding="utf-8")
        repo.index.add(["README.md"])
        self.new_sha = repo.index.commit("Actualizar README").hexsha

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_lists_recent_commits_and_indexes_historical_snapshot(self):
        listed = RepositoryService.list_commits(str(self.repo_path), "main", 20)
        self.assertEqual([item.sha for item in listed.commits], [self.new_sha, self.old_sha])
        self.assertEqual(listed.commits[0].message, "Actualizar README")
        self.assertEqual(
            RepositoryService.list_commits(str(self.repo_path), None, 1).commits[0].sha,
            self.new_sha,
        )

        db = MagicMock()
        with patch.object(
            EmbeddingService,
            "embed_texts",
            side_effect=lambda texts: [[0.0] * 1536 for _ in texts],
        ), patch.object(EmbeddingService, "embed_text", return_value=[0.0] * 1536):
            result = RepositoryService.ingest_commits(
                RepositoryCommitIngestRequest(
                    project_id="project-a",
                    repository_url=str(self.repo_path),
                    commits=[self.old_sha[:10], self.new_sha[:10]],
                ),
                db,
            )

        self.assertEqual([item.sha for item in result.commits], [self.old_sha, self.new_sha])
        rows = db.add_all.call_args.args[0]
        kinds = {row.metadata_json["source_type"] for row in rows}
        self.assertIn("repository_commit", kinds)
        self.assertIn("commit_metadata", kinds)
        self.assertIn("commit_diff", kinds)
        snapshot = next(row for row in rows if row.metadata_json["source_type"] == "repository_commit")
        self.assertIn("Versión inicial", snapshot.content)
        self.assertNotIn("Versión nueva", snapshot.content)
        updated_diff = next(
            row for row in rows
            if row.metadata_json["source_type"] == "commit_diff"
            and row.metadata_json["commit"] == self.new_sha
        )
        self.assertEqual(updated_diff.metadata_json["parent_commit"], self.old_sha)
        self.assertIn("Versión nueva", updated_diff.content)
        self.assertEqual(
            {row.metadata_json["commit"] for row in rows},
            {self.old_sha, self.new_sha},
        )
        db.commit.assert_called_once()

    def test_commit_endpoints_accept_repository_and_project(self):
        app = create_app()
        db = MagicMock()
        app.dependency_overrides[get_db] = lambda: db
        client = TestClient(app)
        listed = client.post("/api/v1/repositories/commits", json={
            "repository_url": str(self.repo_path),
            "branch": "main",
            "limit": 2,
        })
        self.assertEqual(listed.status_code, 200)
        self.assertEqual(listed.json()["commits"][0]["sha"], self.new_sha)

        with patch.object(
            EmbeddingService,
            "embed_texts",
            side_effect=lambda texts: [[0.0] * 1536 for _ in texts],
        ), patch.object(EmbeddingService, "embed_text", return_value=[0.0] * 1536):
            ingested = client.post("/api/v1/repositories/commits/ingest", json={
                "project_id": "project-a",
                "repository_url": str(self.repo_path),
                "commits": [self.old_sha[:10]],
            })
        self.assertEqual(ingested.status_code, 200)
        self.assertEqual(ingested.json()["commits"][0]["sha"], self.old_sha)
        client.close()

    def test_branch_ingest_still_indexes_its_head(self):
        db = MagicMock()
        with patch.object(
            EmbeddingService,
            "embed_texts",
            side_effect=lambda texts: [[0.0] * 1536 for _ in texts],
        ), patch.object(EmbeddingService, "embed_text", return_value=[0.0] * 1536):
            result = RepositoryService.ingest(
                RepositoryIngestRequest(
                    project_id="project-a",
                    repository_url=str(self.repo_path),
                    branches=["main"],
                ),
                db,
            )
        self.assertEqual(result.branches[0].commit, self.new_sha)
        rows = db.add_all.call_args.args[0]
        self.assertTrue(any(
            row.metadata_json["source_type"] == "repository"
            and row.metadata_json["commit"] == self.new_sha
            for row in rows
        ))
        self.assertTrue(any(row.metadata_json["source_type"] == "repository_metadata" for row in rows))

    def test_query_resolves_short_sha_and_rejects_mixed_scope(self):
        app = create_app()
        db = MagicMock()
        project_query = MagicMock()
        project_query.filter.return_value = project_query
        project_query.first.return_value = (1,)
        commit_query = MagicMock()
        commit_query.filter.return_value = commit_query
        commit_query.distinct.return_value = commit_query
        commit_query.all.return_value = [("sample-repo", self.old_sha)]
        db.query.side_effect = [project_query, commit_query]
        app.dependency_overrides[get_db] = lambda: db
        client = TestClient(app)
        answer = RAGAskResponse(
            answer="Versión inicial",
            citations=[],
            context_chunks_used=0,
            retrieval_query="Pregunta",
            provider="test",
            model="test",
        )

        with patch("app.controllers.query_controller.RAGService.ask", return_value=answer) as ask:
            response = client.post("/api/v1/query", json={
                "project_id": "project-a",
                "question": "Pregunta",
                "commit": self.old_sha[:10],
            })
        self.assertEqual(response.status_code, 200)
        self.assertEqual(ask.call_args.args[1].commit, self.old_sha)
        self.assertEqual(ask.call_args.args[1].repository, "sample-repo")

        response = client.post("/api/v1/query", json={
            "project_id": "project-a",
            "question": "Pregunta",
            "commit": self.old_sha,
            "document": "requisitos.pdf",
        })
        self.assertEqual(response.status_code, 422)
        client.close()

    def test_ambiguous_commit_prefix_requires_disambiguation(self):
        app = create_app()
        db = MagicMock()
        project_query = MagicMock()
        project_query.filter.return_value = project_query
        project_query.first.return_value = (1,)
        commit_query = MagicMock()
        commit_query.filter.return_value = commit_query
        commit_query.distinct.return_value = commit_query
        commit_query.all.return_value = [
            ("repo-a", self.old_sha),
            ("repo-b", self.old_sha),
        ]
        db.query.side_effect = [project_query, commit_query]
        app.dependency_overrides[get_db] = lambda: db
        client = TestClient(app)
        response = client.post("/api/v1/query", json={
            "project_id": "project-a",
            "question": "Pregunta",
            "commit": self.old_sha[:10],
        })
        self.assertEqual(response.status_code, 409)
        client.close()

    def test_vector_search_uses_exact_commit_and_repository(self):
        db = MagicMock()
        query = db.query.return_value
        query.filter.return_value = query
        query.order_by.return_value = query
        query.limit.return_value = query
        query.all.return_value = []
        with patch.object(EmbeddingService, "embed_text", return_value=[0.0] * 1536):
            VectorService.semantic_search(db, VectorSearchRequest(
                query="Pregunta",
                project_id="project-a",
                commit=self.old_sha,
                repository="sample-repo",
            ))
        predicates = " ".join(
            str(expression.compile(
                dialect=postgresql.dialect(),
                compile_kwargs={"literal_binds": True},
            ))
            for call in query.filter.call_args_list
            for expression in call.args
        )
        self.assertIn(self.old_sha, predicates)
        self.assertIn("'sample-repo'", predicates)
        self.assertIn("'project-a'", predicates)
        self.assertIn("'commit_diff'", predicates)

    def test_unfiltered_search_excludes_historical_commit_chunks(self):
        db = MagicMock()
        query = db.query.return_value
        query.filter.return_value = query
        query.order_by.return_value = query
        query.limit.return_value = query
        query.all.return_value = []
        with patch.object(EmbeddingService, "embed_text", return_value=[0.0] * 1536):
            VectorService.semantic_search(db, VectorSearchRequest(
                query="Pregunta", project_id="project-a"
            ))
        predicates = " ".join(
            str(expression.compile(
                dialect=postgresql.dialect(),
                compile_kwargs={"literal_binds": True},
            ))
            for call in query.filter.call_args_list
            for expression in call.args
        )
        self.assertIn("NOT IN", predicates)
        self.assertIn("'repository_commit'", predicates)


if __name__ == "__main__":
    unittest.main()
